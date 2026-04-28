import logging
import re
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from typing import Callable

from pkmai.core.config import Config, load_config
from pkmai.core.logger import setup_logging
from pkmai.core.utils import (
    clean_note_text,
    is_ignored,
    sha256_text,
    strip_section,
    replace_or_append_section,
    report_status
)
from pkmai.db.connection import init_embed_db
from pkmai.db.embed_cache import (
    delete_missing_embed_entries,
    load_cached_embedding,
    save_cached_embedding,
)
from pkmai.embeddings.embedder import LocalEmbedder


@dataclass
class NoteRecord:
    path: Path
    rel_path: str
    title: str
    raw_text: str
    clean_text: str
    text_hash: str
    mtime_ns: int


# =========================
# Link-Specific Utilities
# =========================


def has_wikilink_to(text: str, target_title: str) -> bool:
    pattern = re.compile(
        rf"\[\[{re.escape(target_title)}(?:\|[^\]]+)?\]\]", flags=re.IGNORECASE
    )
    return bool(pattern.search(text))


def related_section_pattern(section_title: str) -> re.Pattern[str]:
    return re.compile(
        rf"\n## {re.escape(section_title)}\n(?:- \[\[[^\]]+\]\]\n?)*",
        flags=re.MULTILINE | re.IGNORECASE,
    )


def strip_existing_related_section(text: str, section_title: str) -> str:
    return re.sub(related_section_pattern(section_title), "", text.rstrip())


# =========================
# Vault loading
# =========================


def find_note_files(cfg: Config) -> list[Path]:
    files: list[Path] = []
    for path in cfg.vault_path.rglob("*.md"):
        if is_ignored(path, cfg.vault_path, cfg.ignored_dirs):
            continue
        files.append(path)
    return sorted(files)


def load_note_record(path: Path, vault_path: Path, cfg: Config) -> NoteRecord | None:
    raw = path.read_text(encoding="utf-8")
    clean = clean_note_text(
        raw, cfg.author_mirror_section_title, cfg.link_section_title
    )

    if len(clean) < cfg.link_min_note_chars:
        return None

    return NoteRecord(
        path=path,
        rel_path=path.relative_to(vault_path).as_posix(),
        title=path.stem,
        raw_text=raw,
        clean_text=clean,
        text_hash=sha256_text(clean),
        mtime_ns=path.stat().st_mtime_ns,
    )


# =========================
# Embeddings & Similarity
# =========================


def get_or_compute_embeddings(
    conn, embedder: LocalEmbedder, notes: list[NoteRecord]
) -> dict[str, np.ndarray]:
    result: dict[str, np.ndarray] = {}
    to_compute: list[NoteRecord] = []

    for note in notes:
        cached = load_cached_embedding(conn, note.rel_path)
        if cached is None:
            to_compute.append(note)
            continue

        cached_hash, _, embedding = cached
        if cached_hash == note.text_hash:
            result[note.rel_path] = embedding
        else:
            to_compute.append(note)

    logging.info("Embeddings from cache: %d", len(result))
    logging.info("Embeddings to compute: %d", len(to_compute))

    if to_compute:
        texts = [n.clean_text for n in to_compute]
        new_embeddings = embedder.encode_texts(texts)

        for note, emb in zip(to_compute, new_embeddings):
            save_cached_embedding(
                conn=conn,
                rel_path=note.rel_path,
                title=note.title,
                text_hash=note.text_hash,
                mtime_ns=note.mtime_ns,
                embedding=emb,
            )
            result[note.rel_path] = emb

    return result


def compute_related_notes(
    notes: list[NoteRecord],
    embeddings_by_path: dict[str, np.ndarray],
    similarity_threshold: float,
    max_links_per_note: int,
) -> dict[str, list[tuple[str, float]]]:
    ordered_embeddings = np.stack(
        [embeddings_by_path[n.rel_path] for n in notes], axis=0
    )
    sim = LocalEmbedder.cosine_sim_matrix(ordered_embeddings)

    related: dict[str, list[tuple[str, float]]] = {}

    for i, note in enumerate(notes):
        candidates: list[tuple[str, float]] = []
        for j, other in enumerate(notes):
            if i == j:
                continue
            score = float(sim[i, j])
            if score >= similarity_threshold:
                candidates.append((other.rel_path, score))

        candidates.sort(key=lambda x: x[1], reverse=True)
        related[note.rel_path] = candidates[:max_links_per_note]

    return related


# =========================
# Link insertion logic
# =========================


def build_title_index(notes: list[NoteRecord]) -> dict[str, str]:
    return {n.rel_path: n.title for n in notes}


def insert_related_section(
    note: NoteRecord, related_paths: list[str], title_index: dict[str, str], cfg: Config
) -> str:
    core_text = strip_section(note.raw_text, cfg.link_section_title)
    links = []
    for rel_path in related_paths:
        target_title = title_index[rel_path]
        if cfg.link_insert_only_if_missing and has_wikilink_to(core_text, target_title):
            continue
        links.append(f"- [[{target_title}]]")

    if not links:
        return note.raw_text.strip()

    return replace_or_append_section(
        text=note.raw_text.replace("\r\n", "\n"),
        title=cfg.link_section_title,
        links=links,
    )


def update_note_file(path: Path, new_text: str) -> bool:
    new_text = new_text.strip() + "\n"
    current = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if current == new_text:
        return False
    path.write_text(new_text, encoding="utf-8", newline="\n")
    return True


# =========================
# Main Orchestrator
# =========================


def main(override_config: dict | None = None, status_callback: Callable[[str], None] | None = None) -> None:
    cfg = load_config(override_dict=override_config)
    setup_logging(prefix="auto_links")
    if not cfg.link_enabled:
        logging.info("Auto-links are disabled in settings. Skipping.")
        return

    conn = init_embed_db(cfg.link_cache_db_path)

    report_status("Scanning vault for notes...", status_callback)
    note_files = find_note_files(cfg)
    logging.info("Markdown files found: %d", len(note_files))

    notes: list[NoteRecord] = []
    for path in note_files:
        try:
            note = load_note_record(path, cfg.vault_path, cfg)
            if note is not None:
                notes.append(note)
        except Exception as e:
            logging.exception("Failed to load note %s: %s", path, e)

    logging.info("Notes retained after filtering: %d", len(notes))

    existing_rel_paths = {n.rel_path for n in notes}
    delete_missing_embed_entries(conn, existing_rel_paths)

    if not notes:
        logging.warning("No valid notes found.")
        return

    report_status("Loading embedder...", status_callback)
    embedder = LocalEmbedder(cfg.link_model_name)

    report_status("Computing related notes...", status_callback)
    embeddings_by_path = get_or_compute_embeddings(conn, embedder, notes)
    related = compute_related_notes(
        notes=notes,
        embeddings_by_path=embeddings_by_path,
        similarity_threshold=cfg.link_similarity_threshold,
        max_links_per_note=cfg.max_links_per_note,
    )
    title_index = build_title_index(notes)

    updated_count = 0

    report_status("Generating links...", status_callback)
    for note in notes:
        rel_candidates = related.get(note.rel_path, [])
        related_paths = [rel_path for rel_path, _score in rel_candidates]

        try:
            new_text = insert_related_section(
                note=note, related_paths=related_paths, title_index=title_index, cfg=cfg
            )

            changed = update_note_file(note.path, new_text)
            if changed:
                updated_count += 1
                logging.info("Updated: %s", note.rel_path)

        except Exception as e:
            report_status("failed", status_callback)
            logging.exception("Failed to update note %s: %s", note.rel_path, e)
    
    report_status("completed", status_callback)
    logging.info(
        "Done. Notes updated: %d / %d", 
        updated_count, 
        len(notes)
    )


if __name__ == "__main__":
    main()
