import sqlite3
from pathlib import Path


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Creates the directory if needed and returns a SQLite connection."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(db_path))


def init_author_db(db_path: Path) -> sqlite3.Connection:
    """Initializes the connection and ensures the author cache table exists."""
    conn = get_connection(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS author_mirror_cache (
            rel_path TEXT PRIMARY KEY,
            source_title TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            mirror_rel_path TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def init_embed_db(db_path: Path) -> sqlite3.Connection:
    """Initializes the connection and ensures the embeddings table exists."""
    conn = get_connection(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS note_embeddings (
            rel_path TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            text_hash TEXT NOT NULL,
            mtime_ns INTEGER NOT NULL,
            dim INTEGER NOT NULL,
            embedding BLOB NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn