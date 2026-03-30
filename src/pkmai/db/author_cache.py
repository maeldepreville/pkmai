import sqlite3
from datetime import datetime


def get_cached_hash(conn: sqlite3.Connection, rel_path: str) -> str | None:
    """Retrieves the last known hash for a note, or None if it's new."""
    cur = conn.execute(
        "SELECT content_hash FROM author_mirror_cache WHERE rel_path = ?",
        (rel_path,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def upsert_author_cache(
    conn: sqlite3.Connection,
    rel_path: str,
    source_title: str,
    content_hash: str,
    mirror_rel_path: str,
) -> None:
    """Inserts or updates the cache record for a note."""
    conn.execute(
        """
        INSERT INTO author_mirror_cache (rel_path, source_title, content_hash, mirror_rel_path, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(rel_path) DO UPDATE SET
            source_title = excluded.source_title,
            content_hash = excluded.content_hash,
            mirror_rel_path = excluded.mirror_rel_path,
            updated_at = excluded.updated_at
        """,
        (
            rel_path,
            source_title,
            content_hash,
            mirror_rel_path,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()


def delete_missing_author_entries(
    conn: sqlite3.Connection, existing_rel_paths: set[str]
) -> None:
    """Cleans up the database by removing entries for notes that were deleted from the vault."""
    cur = conn.execute("SELECT rel_path FROM author_mirror_cache")
    cached_paths = {row[0] for row in cur.fetchall()}

    to_delete = cached_paths - existing_rel_paths
    if to_delete:
        conn.executemany(
            "DELETE FROM author_mirror_cache WHERE rel_path = ?",
            [(p,) for p in to_delete],
        )
        conn.commit()
