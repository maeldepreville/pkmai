from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Callable


# =========================
# Utilities
# =========================


def sha256_text(text: str) -> str:
    """Returns the SHA-256 hash of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_rel_path(path: Path) -> str:
    """Normalizes a path to a lowercase posix string without leading slashes."""
    return path.as_posix().strip("/").lower()


def is_ignored(file_path: Path, vault_path: Path, ignored_dirs: list[str]) -> bool:
    """Checks if a file resides within any of the ignored directories."""
    try:
        rel_path = file_path.relative_to(vault_path)
    except ValueError:
        return False
    parts = rel_path.parts
    for ignored_dir in ignored_dirs:
        if ignored_dir in parts:
            return True
        ignored_path = Path(ignored_dir)
        if ignored_path == rel_path or ignored_path in rel_path.parents:
            return True
    return False


def strip_frontmatter(text: str) -> str:
    return re.sub(r"(?s)\A---\n.*?\n---\n?", "", text, count=1)


def strip_section(text: str, title: str) -> str:
    """Removes a specific section and its bullet point links safely."""
    pattern = rf"^## {re.escape(title)}[ \t]*\n(?:-[ \t]*\[\[.*?\]\][ \t]*(?:\n|$))*"
    cleaned = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def replace_or_append_section(text: str, title: str, links: list[str]) -> str:
    """Replaces a section in-place, or appends it to the end if not found."""
    if not links:
        return strip_section(text, title)
    new_section = f"## {title}\n" + "\n".join(links)
    pattern = rf"^## {re.escape(title)}[ \t]*\n(?:-[ \t]*\[\[.*?\]\][ \t]*(?:\n|$))*"
    if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
        updated = re.sub(
            pattern,
            lambda _: new_section + "\n",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
    else:
        updated = text.strip() + "\n\n" + new_section
    updated = re.sub(r"\n{3,}", "\n\n", updated)
    return updated.strip()


def clean_note_text(raw: str, author_title: str, link_title: str) -> str:
    text = strip_frontmatter(raw)
    text = strip_section(text, author_title)
    text = strip_section(text, link_title)
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"(?m)^\s*#+\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def report_status(msg: str, status_callback: Callable[[str], None] | None):
    if status_callback:
        status_callback(msg)
