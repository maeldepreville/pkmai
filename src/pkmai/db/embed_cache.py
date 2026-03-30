import sqlite3
from datetime import datetime
import numpy as np


def _np_to_blob(arr: np.ndarray) -> bytes:
    """Internal helper: Converts a numpy array to a raw byte string for SQLite."""
    arr = np.asarray(arr, dtype=np.float32)
    return arr.tobytes()


def _blob_to_np(blob: bytes, dim: int) -> np.ndarray:
    """Internal helper: Converts a SQLite byte string back into a numpy array."""
    arr = np.frombuffer(blob, dtype=np.float32)
    if arr.shape[0] != dim:
        raise ValueError(
            f"Embedding dimension mismatch: expected {dim}, got {arr.shape[0]}"
        )
    return arr


def load_cached_embedding(
    conn: sqlite3.Connection, rel_path: str
) -> tuple[str, int, np.ndarray] | None:
    """Loads an embedding from the DB. Returns (text_hash, mtime_ns, numpy_array)."""
    cur = conn.execute(
        """
        SELECT text_hash, mtime_ns, dim, embedding
        FROM note_embeddings
        WHERE rel_path = ?
    """,
        (rel_path,),
    )

    row = cur.fetchone()
    if row is None:
        return None

    text_hash, mtime_ns, dim, blob = row
    return text_hash, mtime_ns, _blob_to_np(blob, dim)


def save_cached_embedding(
    conn: sqlite3.Connection,
    rel_path: str,
    title: str,
    text_hash: str,
    mtime_ns: int,
    embedding: np.ndarray,
) -> None:
    """Saves a computed numpy embedding array into the SQLite database."""
    embedding = np.asarray(embedding, dtype=np.float32)
    conn.execute(
        """
        INSERT INTO note_embeddings (rel_path, title, text_hash, mtime_ns, dim, embedding, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(rel_path) DO UPDATE SET
            title = excluded.title,
            text_hash = excluded.text_hash,
            mtime_ns = excluded.mtime_ns,
            dim = excluded.dim,
            embedding = excluded.embedding,
            updated_at = excluded.updated_at
    """,
        (
            rel_path,
            title,
            text_hash,
            mtime_ns,
            int(embedding.shape[0]),
            _np_to_blob(embedding),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()


def delete_missing_embed_entries(
    conn: sqlite3.Connection, existing_rel_paths: set[str]
) -> None:
    """Cleans up the database by removing embeddings for notes that were deleted from the vault."""
    cur = conn.execute("SELECT rel_path FROM note_embeddings")
    cached = {row[0] for row in cur.fetchall()}

    to_delete = cached - existing_rel_paths
    if to_delete:
        conn.executemany(
            "DELETE FROM note_embeddings WHERE rel_path = ?", [(p,) for p in to_delete]
        )
        conn.commit()
