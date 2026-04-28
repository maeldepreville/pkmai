import logging
from pathlib import Path
from typing import Any, Callable

from pkmai.core.config import Config, load_config
from pkmai.core.logger import setup_logging
from pkmai.core.utils import (
    clean_note_text,
    is_ignored,
    sha256_text,
    replace_or_append_section,
    report_status
)
from pkmai.db.connection import init_author_db
from pkmai.db.author_cache import (
    delete_missing_author_entries,
    get_cached_hash,
    upsert_author_cache,
)
from pkmai.llm.llama_cpp_provider import LlamaCppProvider
from pkmai.llm.manager import get_or_download_model


# =========================
# File Paths & Linking
# =========================


def get_notes_root_path(cfg: Config) -> Path:
    return (cfg.vault_path / cfg.notes_root_dir).resolve()


def get_note_files(cfg: Config) -> list[Path]:
    files: list[Path] = []
    notes_root = get_notes_root_path(cfg)
    mirror_dir = (notes_root / cfg.author_mirror_dir).resolve()

    for path in notes_root.rglob("*.md"):
        if is_ignored(path, cfg.vault_path, cfg.ignored_dirs):
            continue

        try:
            if mirror_dir in path.resolve().parents:
                continue
        except Exception:
            pass

        if path.stem.startswith(cfg.author_mirror_prefix):
            continue

        files.append(path)

    return sorted(files)


def get_mirror_path(cfg: Config, source_title: str) -> Path:
    notes_root = get_notes_root_path(cfg)
    mirror_dir = notes_root / cfg.author_mirror_dir
    mirror_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{cfg.author_mirror_prefix} Sur {source_title}.md"
    return mirror_dir / filename


def add_mirror_link_to_source(
    source_path: Path, mirror_rel_path: str, cfg: Config
) -> None:
    original = source_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    mirror_filename = (
        mirror_rel_path.replace("\\", "/").replace(".md", "").rsplit("/", 1)[-1]
    )
    link = f"- [[{mirror_filename}]]"

    updated = replace_or_append_section(
        text=original, title=cfg.author_mirror_section_title, links=[link]
    )

    updated = updated.strip() + "\n"

    if updated != original:
        source_path.write_text(updated, encoding="utf-8", newline="\n")


# =========================
# AI Prompt & Output Formatting
# =========================


def get_messages(source_title: str, source_text: str) -> list[dict[str, str]]:
    system_instruction = """Tu dois analyser une note personnelle et proposer DEUX auteurs, philosophes, penseurs ou essayistes réels pour former une dynamique de THÈSE et d'ANTITHÈSE autour du contenu de cette note.

Objectifs :
1. THÈSE : Proposer un auteur dont la pensée est la plus proche du contenu de la note, pour en approfondir l'idée.
2. ANTITHÈSE : Proposer un deuxième auteur qui s'oppose radicalement, critique, ou offre une perspective inversée sur cette même idée.

Contraintes impératives :
- Choisis des auteurs réels et distincts. N'invente ni auteur, ni œuvre.
- Si tu n'es pas sûr des œuvres exactes, indique seulement celles dont tu es confiant.
- Réponds uniquement en JSON strict, avec une structure parfaitement PLATE (aucun sous-dictionnaire).
- Pas de markdown dans les champs. Pas de texte hors JSON.

Consignes pour les "warnings" :
- Si tu as des réserves (ex: rapprochement lointain), sois très bref. 
- Si tu n'as absolument aucune réserve, tu DOIS écrire : "Aucune réserve quant à la proposition".

Format attendu (JSON STRICT ET PLAT) :
{
  "these_auteur": "Nom de l'auteur (Thèse)",
  "these_oeuvres": ["Ouvrage 1", "Ouvrage 2"],
  "these_confiance": "faible|moyen|élevé",
  "these_pourquoi": "2 à 4 phrases expliquant en quoi cet auteur valide la note",
  "these_synthese": "5 à 10 phrases synthétisant sa pensée sur le sujet",
  "these_warnings": "Brève réserve, ou 'Aucune réserve quant à la proposition'",
  "antithese_auteur": "Nom de l'auteur (Antithèse)",
  "antithese_oeuvres": ["Ouvrage 1", "Ouvrage 2"],
  "antithese_confiance": "faible|moyen|élevé",
  "antithese_pourquoi": "2 à 4 phrases expliquant en quoi cet auteur s'oppose à la note",
  "antithese_synthese": "5 à 10 phrases synthétisant sa pensée critique sur le sujet",
  "antithese_warnings": "Brève réserve, ou 'Aucune réserve quant à la proposition'",
  "mots_cles": ["mot-clé 1", "mot-clé 2"]
}"""

    user_content = (
        f"Titre de la note :\n{source_title}\n\nContenu de la note :\n{source_text}"
    )

    return [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_content},
    ]


def sanitize_field(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def sanitize_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        s = sanitize_field(item)
        if s:
            result.append(s)
    return result


def normalize_result(data: dict[str, Any]) -> dict[str, Any]:
    these_auteur = sanitize_field(data.get("these_auteur") or data.get("These_auteur"))
    anti_auteur = sanitize_field(
        data.get("antithese_auteur") or data.get("Antithese_auteur")
    )

    if not these_auteur or not anti_auteur:
        raise ValueError(
            f"Auteurs manquants. Le modèle a généré ces clés : {list(data.keys())}"
        )

    def clean_confidence(val: Any) -> str:
        c = sanitize_field(val).lower()
        return c if c in {"faible", "moyen", "élevé"} else "faible"

    these_data = {
        "auteur": these_auteur,
        "œuvres": sanitize_list(data.get("these_oeuvres") or data.get("these_œuvres")),
        "confiance": clean_confidence(data.get("these_confiance")),
        "pourquoi_cet_auteur": sanitize_field(data.get("these_pourquoi")),
        "synthèse": sanitize_field(
            data.get("these_synthese") or data.get("these_synthèse")
        ),
        "warnings": sanitize_field(data.get("these_warnings")),
    }
    antithese_data = {
        "auteur": anti_auteur,
        "œuvres": sanitize_list(
            data.get("antithese_oeuvres") or data.get("antithese_œuvres")
        ),
        "confiance": clean_confidence(data.get("antithese_confiance")),
        "pourquoi_cet_auteur": sanitize_field(data.get("antithese_pourquoi")),
        "synthèse": sanitize_field(
            data.get("antithese_synthese") or data.get("antithese_synthèse")
        ),
        "warnings": sanitize_field(data.get("antithese_warnings")),
    }

    return {
        "these": these_data,
        "antithese": antithese_data,
        "mots_clés": sanitize_list(data.get("mots_cles") or data.get("mots_clés")),
    }


def render_markdown(source_title: str, data: dict[str, Any]) -> str:
    keywords = ", ".join(data["mots_clés"]) if data["mots_clés"] else "Non spécifié"

    def format_author_section(title: str, block: dict[str, Any]) -> list[str]:
        works = " ; ".join(block["œuvres"]) if block["œuvres"] else "Non spécifié"
        return [
            f"## {title} : {block['auteur']}",
            f"**Ouvrages associés :** {works}",
            f"**Niveau de confiance :** {block['confiance']}",
            "",
            "### Pourquoi cet auteur ?",
            block["pourquoi_cet_auteur"] or "Non précisé.",
            "",
            "### Synthèse",
            block["synthèse"],
            "",
            "### Réserves",
            block["warnings"] or "Aucune réserve quant à la proposition.",
            "",
        ]

    parts = [
        "",
        f"Note source : [[{source_title}]]",
        f"Mots-clés : {keywords}",
        "",
        "---",
        "",
    ]

    parts.extend(format_author_section("Thèse", data["these"]))
    parts.extend(["---", ""])
    parts.extend(format_author_section("Antithèse", data["antithese"]))

    return "\n".join(parts)


# =========================
# Main Orchestrator
# =========================


def main(override_config: dict | None = None, status_callback: Callable[[str], None] | None = None) -> None:
    cfg = load_config(override_dict=override_config)
    setup_logging(prefix="author_mirror")
    if not cfg.author_mirror_enabled:
        logging.info("Author Mirror is disabled in settings. Skipping.")
        return
    
    conn = init_author_db(cfg.author_cache_db_path)
    
    if cfg.author_use_custom_path:
        report_status("Loading custom local model...", status_callback)
        model_path = Path(cfg.author_custom_path)
        if not model_path.exists():
            logging.error("Custom model path does not exist: %s", model_path)
            return
        logging.info("Using custom local model from: %s", model_path)
    else:
        logging.info("Ensuring recommended model %s is available...", cfg.author_filename)
        report_status("Downloading AI model (this may take a few minutes)...", status_callback)
        model_path = get_or_download_model(
            repo_id=cfg.author_repo_id, 
            filename=cfg.author_filename
        )

    report_status("Loading model into memory...", status_callback)
    llm_provider = LlamaCppProvider(
        model_path=model_path,
        n_ctx=cfg.author_n_ctx,
        n_threads=cfg.author_n_threads,
    )

    report_status("Scanning vault for notes...", status_callback)
    files = get_note_files(cfg)
    logging.info("Notes source trouvées: %d", len(files))

    existing_rel_paths = {path.relative_to(cfg.vault_path).as_posix() for path in files}
    delete_missing_author_entries(conn, existing_rel_paths)

    created = 0
    overwritten = 0
    skipped = 0
    skipped_unchanged = 0
    failed = 0

    report_status("Generating Author Mirrors...", status_callback)
    for path in files:
        source_title = path.stem
        rel_path = path.relative_to(cfg.vault_path).as_posix()

        try:
            raw = path.read_text(encoding="utf-8")
            source_text = clean_note_text(
                raw, cfg.author_mirror_section_title, cfg.link_section_title
            )
            if len(source_text) < cfg.author_min_chars:
                skipped += 1
                logging.info("Skipped (too short): %s", source_title)
                continue

            content_hash = sha256_text(source_text)
            cached_hash = get_cached_hash(conn, rel_path)

            target_path = get_mirror_path(cfg, source_title)
            mirror_rel_path = target_path.relative_to(cfg.vault_path).as_posix()

            if cached_hash == content_hash and target_path.exists():
                skipped_unchanged += 1
                logging.info("Skipped (unchanged): %s", source_title)
                continue

            if (
                target_path.exists()
                and not cfg.author_overwrite_existing
                and cached_hash is None
            ):
                skipped += 1
                logging.info(
                    "Skipped (mirror exists, no cache history): %s", source_title
                )
                continue

            # Generate JSON using our provider and the specific config settings
            messages = get_messages(source_title, source_text)
            raw_result = llm_provider.generate_json(
                messages=messages,
                max_tokens=cfg.author_max_tokens,
                temperature=cfg.author_temperature,
                repeat_penalty=cfg.author_repeat_penalty,
            )

            result = normalize_result(raw_result)
            md = render_markdown(source_title, result)

            existed_before = target_path.exists()
            target_path.write_text(md, encoding="utf-8", newline="\n")

            mirror_rel_path = target_path.relative_to(cfg.vault_path).as_posix()
            add_mirror_link_to_source(path, mirror_rel_path, cfg)

            upsert_author_cache(
                conn=conn,
                rel_path=rel_path,
                source_title=source_title,
                content_hash=content_hash,
                mirror_rel_path=mirror_rel_path,
            )

            if existed_before:
                overwritten += 1
                logging.info("Updated mirror note: %s", target_path.name)
            else:
                created += 1
                logging.info("Created mirror note: %s", target_path.name)

        except Exception as e:
            failed += 1
            report_status("failed", status_callback)
            logging.exception("Erreur sur %s: %s", source_title, e)

    report_status("completed", status_callback)
    logging.info(
        "Done | created=%d overwritten=%d skipped=%d skipped_unchanged=%d failed=%d",
        created,
        overwritten,
        skipped,
        skipped_unchanged,
        failed,
    )


if __name__ == "__main__":
    main()
