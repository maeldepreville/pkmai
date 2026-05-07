import logging
from pathlib import Path
from typing import Any

from pkmai.core.logger import setup_logging
from pkmai.core.utils import is_ignored, strip_section


def resolve_path(path_value: str | Path, base_dir: Path | None = None) -> Path:
    path = Path(path_value).expanduser()

    if path.is_absolute():
        return path

    if base_dir is not None:
        return base_dir / path

    return Path.cwd() / path


def notes_root_from_payload(payload: dict[str, Any]) -> Path:
    vault = payload["vault"]
    vault_path = Path(vault["path"]).expanduser()

    notes_root_dir = vault.get("notes_root_dir", "").strip()

    if notes_root_dir:
        return vault_path / notes_root_dir

    return vault_path


def ignored_dirs_from_payload(payload: dict[str, Any]) -> list[str]:
    ignored_dirs = payload["vault"].get("ignored_dirs", [])

    if isinstance(ignored_dirs, str):
        return [item.strip() for item in ignored_dirs.split(",") if item.strip()]

    return ignored_dirs


def iter_markdown_notes(payload: dict[str, Any]) -> list[Path]:
    vault_path = Path(payload["vault"]["path"]).expanduser()
    notes_root = notes_root_from_payload(payload)
    ignored_dirs = ignored_dirs_from_payload(payload)

    if not notes_root.exists():
        logging.warning("Notes root does not exist: %s", notes_root)
        return []

    files: list[Path] = []

    for path in notes_root.rglob("*.md"):
        if is_ignored(path, vault_path, ignored_dirs):
            continue

        files.append(path)

    return sorted(files)


def remove_section_from_notes(
    payload: dict[str, Any],
    section_title: str,
) -> int:
    updated_count = 0

    for note_path in iter_markdown_notes(payload):
        try:
            original = note_path.read_text(encoding="utf-8").replace("\r\n", "\n")
            cleaned = strip_section(original, section_title).strip() + "\n"

            if cleaned != original:
                note_path.write_text(cleaned, encoding="utf-8", newline="\n")
                updated_count += 1
                logging.info("Removed section '%s' from %s", section_title, note_path)

        except Exception:
            logging.exception("Failed to clean note: %s", note_path)

    return updated_count


def delete_file_if_exists(path: Path) -> bool:
    try:
        if path.exists() and path.is_file():
            path.unlink()
            logging.info("Deleted file: %s", path)
            return True

        logging.info("File did not exist, skipping: %s", path)
        return False

    except Exception:
        logging.exception("Failed to delete file: %s", path)
        return False


def delete_sqlite_cache(cache_path: Path) -> list[str]:
    """
    Deletes a SQLite cache and common sidecar files.
    SQLite can create -wal and -shm files when WAL mode is used.
    """
    deleted: list[str] = []

    candidates = [
        cache_path,
        Path(f"{cache_path}-wal"),
        Path(f"{cache_path}-shm"),
    ]

    for candidate in candidates:
        if delete_file_if_exists(candidate):
            deleted.append(str(candidate))

    return deleted


def undo_auto_links(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Removes the Auto-Links generated section from markdown notes and deletes
    the Auto-Links embedding cache DB.
    """
    setup_logging(prefix="cleanup_auto_links")

    section_title = payload["auto_links"]["section_title"]
    cache_path = resolve_path(payload["auto_links"]["cache"]["db_path"])

    logging.info("Starting Auto-Links cleanup")
    logging.info("Section title: %s", section_title)
    logging.info("Cache path: %s", cache_path)

    updated_notes = remove_section_from_notes(payload, section_title)
    deleted_cache_files = delete_sqlite_cache(cache_path)

    logging.info(
        "Auto-Links cleanup completed. Updated notes=%d, deleted cache files=%d",
        updated_notes,
        len(deleted_cache_files),
    )

    return {
        "status": "completed",
        "updated_notes": updated_notes,
        "deleted_cache_files": deleted_cache_files,
    }


def delete_generated_author_notes(payload: dict[str, Any]) -> int:
    notes_root = notes_root_from_payload(payload)
    author_cfg = payload["author_mirror"]

    output_dir_raw = author_cfg["output_dir"]
    prefix = author_cfg.get("prefix", "").strip()

    output_dir = resolve_path(output_dir_raw, base_dir=notes_root)

    if not output_dir.exists():
        logging.info("Author Mirror output directory does not exist: %s", output_dir)
        return 0

    if not output_dir.is_dir():
        logging.warning("Author Mirror output path is not a directory: %s", output_dir)
        return 0

    deleted_count = 0

    for path in output_dir.rglob("*.md"):
        if prefix and not path.name.startswith(prefix):
            logging.info("Skipping generated note without expected prefix: %s", path)
            continue

        try:
            path.unlink()
            deleted_count += 1
            logging.info("Deleted generated Author Mirror note: %s", path)

        except Exception:
            logging.exception("Failed to delete generated Author Mirror note: %s", path)

    return deleted_count


def undo_author_mirror(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Removes Author Mirror generated sections from source notes, deletes generated
    mirror notes, and deletes the Author Mirror cache DB.
    """
    setup_logging(prefix="cleanup_author_mirror")

    section_title = payload["author_mirror"]["section_title"]
    cache_path = resolve_path(payload["author_mirror"]["cache"]["db_path"])

    logging.info("Starting Author Mirror cleanup")
    logging.info("Section title: %s", section_title)
    logging.info("Cache path: %s", cache_path)

    updated_notes = remove_section_from_notes(payload, section_title)
    deleted_generated_notes = delete_generated_author_notes(payload)
    deleted_cache_files = delete_sqlite_cache(cache_path)

    logging.info(
        "Author Mirror cleanup completed. Updated notes=%d, deleted generated notes=%d, deleted cache files=%d",
        updated_notes,
        deleted_generated_notes,
        len(deleted_cache_files),
    )

    return {
        "status": "completed",
        "updated_notes": updated_notes,
        "deleted_generated_notes": deleted_generated_notes,
        "deleted_cache_files": deleted_cache_files,
    }
