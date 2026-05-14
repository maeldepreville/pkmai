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
    report_status,
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
    filename = f"{cfg.author_mirror_prefix} - {source_title}.md"
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


def resolve_output_language(
    output_language: str,
    custom_output_language: str = "",
) -> str:
    output_language = sanitize_field(output_language).lower()
    custom_output_language = sanitize_field(custom_output_language)

    if output_language == "french":
        return "French"

    if output_language == "custom" and custom_output_language:
        return custom_output_language

    return "English"


def get_language_instruction(resolved_language: str) -> str:
    if resolved_language.lower() == "english":
        return """LANGUAGE REQUIREMENT:
- Write every human-readable JSON value in English.
- JSON keys must stay in English.
- Confidence values must stay exactly one of: low, medium, high.
- Author names and work titles may stay in their original language."""

    return f"""LANGUAGE REQUIREMENT:
- Write every human-readable JSON value in {resolved_language}.
- The following fields MUST be in {resolved_language}:
  thesis_why, thesis_synthesis, thesis_warnings,
  antithesis_why, antithesis_synthesis, antithesis_warnings,
  keywords.
- Do NOT write explanations in English.
- JSON keys must stay in English.
- Confidence values must stay exactly one of: low, medium, high.
- Author names and work titles may stay in their original language."""


def get_messages(
    source_title: str,
    source_text: str,
    output_language: str,
    custom_output_language: str = "",
) -> list[dict[str, str]]:
    resolved_language = resolve_output_language(
        output_language=output_language,
        custom_output_language=custom_output_language,
    )

    language_instruction = get_language_instruction(resolved_language)

    system_instruction = f"""You analyze a personal markdown note and propose TWO real authors, philosophers, thinkers, or essayists in a THESIS / ANTITHESIS dynamic.

{language_instruction}

Goal:
1. THESIS: Propose one author whose thought is closest to the note and can deepen its main idea.
2. ANTITHESIS: Propose another author who strongly disagrees, criticizes, or offers an opposite perspective.

Strict constraints:
- Choose real and distinct authors.
- Do not invent authors or works.
- If you are not confident about exact works, only mention works you are confident about.
- Respond only with strict JSON.
- Use a flat JSON object. Do not use nested dictionaries.
- Do not include markdown inside fields.
- Do not include any text outside the JSON object.

Expected strict flat JSON format:
{{
  "thesis_author": "Author name",
  "thesis_works": ["Work 1", "Work 2"],
  "thesis_confidence": "low|medium|high",
  "thesis_why": "2 to 4 sentences in the requested language",
  "thesis_synthesis": "5 to 10 sentences in the requested language",
  "thesis_warnings": "Brief reservation in the requested language, or no particular reservation",
  "antithesis_author": "Author name",
  "antithesis_works": ["Work 1", "Work 2"],
  "antithesis_confidence": "low|medium|high",
  "antithesis_why": "2 to 4 sentences in the requested language",
  "antithesis_synthesis": "5 to 10 sentences in the requested language",
  "antithesis_warnings": "Brief reservation in the requested language, or no particular reservation",
  "keywords": ["keyword 1", "keyword 2"]
}}"""

    user_content = (
        f"Note title:\n{source_title}\n\n"
        f"Note content:\n{source_text}"
    )

    return [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_content},
    ]


# To update with future multi-lingual feature.
def migrate_legacy_french_keys(data: dict[str, Any]) -> dict[str, Any]:
    legacy_map = {
        "these_auteur": "thesis_author",
        "These_auteur": "thesis_author",
        "these_oeuvres": "thesis_works",
        "these_œuvres": "thesis_works",
        "these_confiance": "thesis_confidence",
        "these_pourquoi": "thesis_why",
        "these_synthese": "thesis_synthesis",
        "these_synthèse": "thesis_synthesis",
        "these_warnings": "thesis_warnings",

        "antithese_auteur": "antithesis_author",
        "Antithese_auteur": "antithesis_author",
        "antithese_oeuvres": "antithesis_works",
        "antithese_œuvres": "antithesis_works",
        "antithese_confiance": "antithesis_confidence",
        "antithese_pourquoi": "antithesis_why",
        "antithese_synthese": "antithesis_synthesis",
        "antithese_synthèse": "antithesis_synthesis",
        "antithese_warnings": "antithesis_warnings",

        "mots_cles": "keywords",
        "mots_clés": "keywords",
    }

    migrated = dict(data)

    for legacy_key, canonical_key in legacy_map.items():
        if legacy_key in migrated and canonical_key not in migrated:
            migrated[canonical_key] = migrated[legacy_key]

    return migrated


def normalize_confidence(value: Any) -> str:
    raw = sanitize_field(value).lower()

    confidence_map = {
        "low": "low",
        "medium": "medium",
        "high": "high",

        # Legacy / French tolerance.
        "faible": "low",
        "moyen": "medium",
        "élevé": "high",
        "eleve": "high",
        "haut": "high",
        "haute": "high",
    }

    return confidence_map.get(raw, "low")


def normalize_result(data: dict[str, Any]) -> dict[str, Any]:
    data = migrate_legacy_french_keys(data)

    thesis_author = sanitize_field(data.get("thesis_author"))
    antithesis_author = sanitize_field(data.get("antithesis_author"))

    if not thesis_author or not antithesis_author:
        raise ValueError(
            f"Missing authors. Generated keys: {list(data.keys())}"
        )

    thesis_data = {
        "author": thesis_author,
        "works": sanitize_list(data.get("thesis_works")),
        "confidence": normalize_confidence(data.get("thesis_confidence")),
        "why": sanitize_field(data.get("thesis_why")),
        "synthesis": sanitize_field(data.get("thesis_synthesis")),
        "warnings": sanitize_field(data.get("thesis_warnings")),
    }

    antithesis_data = {
        "author": antithesis_author,
        "works": sanitize_list(data.get("antithesis_works")),
        "confidence": normalize_confidence(data.get("antithesis_confidence")),
        "why": sanitize_field(data.get("antithesis_why")),
        "synthesis": sanitize_field(data.get("antithesis_synthesis")),
        "warnings": sanitize_field(data.get("antithesis_warnings")),
    }

    return {
        "thesis": thesis_data,
        "antithesis": antithesis_data,
        "keywords": sanitize_list(data.get("keywords")),
    }


AUTHOR_MIRROR_LABELS = {
    "english": {
        "source_note": "Source note",
        "keywords": "Keywords",
        "not_specified": "Not specified",
        "associated_works": "Associated works",
        "confidence": "Confidence level",
        "why": "Why this author?",
        "synthesis": "Synthesis",
        "warnings": "Reservations",
        "thesis": "Thesis",
        "antithesis": "Antithesis",
        "no_warning": "No particular reservation about this suggestion.",
        "low": "low",
        "medium": "medium",
        "high": "high",
    },
    "french": {
        "source_note": "Note source",
        "keywords": "Mots-clés",
        "not_specified": "Non spécifié",
        "associated_works": "Ouvrages associés",
        "confidence": "Niveau de confiance",
        "why": "Pourquoi cet auteur ?",
        "synthesis": "Synthèse",
        "warnings": "Réserves",
        "thesis": "Thèse",
        "antithesis": "Antithèse",
        "no_warning": "Aucune réserve particulière quant à la proposition.",
        "low": "faible",
        "medium": "moyen",
        "high": "élevé",
    },
}


def get_author_mirror_labels(output_language: str) -> dict[str, str]:
    output_language = sanitize_field(output_language).lower()

    if output_language == "french":
        return AUTHOR_MIRROR_LABELS["french"]

    return AUTHOR_MIRROR_LABELS["english"]


def render_markdown(
    source_title: str,
    data: dict[str, Any],
    output_language: str,
) -> str:
    labels = get_author_mirror_labels(output_language)

    keywords = (
        ", ".join(data["keywords"])
        if data["keywords"]
        else labels["not_specified"]
    )

    def confidence_label(value: str) -> str:
        return labels.get(value, value)

    def format_author_section(title: str, block: dict[str, Any]) -> list[str]:
        works = (
            " ; ".join(block["works"])
            if block["works"]
            else labels["not_specified"]
        )

        return [
            f"## {title} : {block['author']}",
            f"**{labels['associated_works']} :** {works}",
            f"**{labels['confidence']} :** {confidence_label(block['confidence'])}",
            "",
            f"### {labels['why']}",
            block["why"] or labels["not_specified"],
            "",
            f"### {labels['synthesis']}",
            block["synthesis"] or labels["not_specified"],
            "",
            f"### {labels['warnings']}",
            block["warnings"] or labels["no_warning"],
            "",
        ]

    parts = [
        "",
        f"{labels['source_note']} : [[{source_title}]]",
        f"{labels['keywords']} : {keywords}",
        "",
        "---",
        "",
    ]

    parts.extend(format_author_section(labels["thesis"], data["thesis"]))
    parts.extend(["---", ""])
    parts.extend(format_author_section(labels["antithesis"], data["antithesis"]))

    return "\n".join(parts)


# =========================
# Main Orchestrator
# =========================


def main(
    override_config: dict | None = None,
    status_callback: Callable[[str], None] | None = None,
) -> None:
    cfg = load_config(override_dict=override_config)
    setup_logging(prefix="author_mirror")
    if not cfg.author_mirror_enabled:
        logging.info("Author Mirror is disabled in settings. Skipping.")
        return

    conn = None

    try:
        conn = init_author_db(cfg.author_cache_db_path)

        if cfg.author_use_custom_path:
            report_status("Loading custom local model...", status_callback)
            model_path = Path(cfg.author_custom_path)
            if not model_path.exists():
                logging.error("Custom model path does not exist: %s", model_path)
                return
            logging.info("Using custom local model from: %s", model_path)
        else:
            logging.info(
                "Ensuring recommended model %s is available...", cfg.author_filename
            )
            report_status(
                "Downloading AI model (this may take a few minutes)...", status_callback
            )
            model_path = get_or_download_model(
                repo_id=cfg.author_repo_id, filename=cfg.author_filename
            )

        report_status("Loading model into memory...", status_callback)
        llm_provider = LlamaCppProvider(
            model_path=model_path,
            n_ctx=cfg.author_n_ctx,
            n_threads=cfg.author_n_threads,
        )

        report_status("Scanning vault for notes...", status_callback)
        files = get_note_files(cfg)
        logging.info("Source Notes found: %d", len(files))

        existing_rel_paths = {
            path.relative_to(cfg.vault_path).as_posix() for path in files
        }
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
                messages = get_messages(
                    source_title=source_title,
                    source_text=source_text,
                    output_language=cfg.author_output_language,
                    custom_output_language=cfg.author_custom_output_language,
                )

                raw_result = llm_provider.generate_json(
                    messages=messages,
                    max_tokens=cfg.author_max_tokens,
                    temperature=cfg.author_temperature,
                    repeat_penalty=cfg.author_repeat_penalty,
                )

                result = normalize_result(raw_result)

                md = render_markdown(
                    source_title=source_title,
                    data=result,
                    output_language=cfg.author_output_language,
                )

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
                logging.exception("Error on %s: %s", source_title, e)

        report_status("completed", status_callback)
        logging.info(
            "Done | created=%d overwritten=%d skipped=%d skipped_unchanged=%d failed=%d",
            created,
            overwritten,
            skipped,
            skipped_unchanged,
            failed,
        )

    finally:
        if conn is not None:
            conn.close()
            logging.info("Author Mirror cache database connection closed.")


if __name__ == "__main__":
    main()
