"""Offline FTS5 + sqlite-vec memory index with reciprocal-rank fusion."""
from __future__ import annotations
import math, os, re, sqlite3

DEFAULT_DIMENSION = 384
RRF_K = 60
CANDIDATE_LIMIT = 50

def embedding_dimension() -> int:
    raw = os.getenv("KRAL_EMBEDDING_DIM", str(DEFAULT_DIMENSION))
    if not raw.isdigit() or not 8 <= int(raw) <= 4096:
        raise RuntimeError("KRAL_EMBEDDING_DIM must be between 8 and 4096")
    return int(raw)

def load_vector_extension(db: sqlite3.Connection) -> None:
    try:
        import sqlite_vec
    except ImportError as exc:
        raise RuntimeError("sqlite-vec is required; install server/requirements.txt") from exc
    db.enable_load_extension(True)
    try:
        sqlite_vec.load(db)
    finally:
        db.enable_load_extension(False)

def initialize(db: sqlite3.Connection) -> None:
    dimension = embedding_dimension()
    db.executescript("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
            text, content='memory', content_rowid='id', tokenize='unicode61'
        );
        CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory BEGIN
            INSERT INTO memory_fts(rowid,text) VALUES(new.id,new.text);
        END;
        CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory BEGIN
            INSERT INTO memory_fts(memory_fts,rowid,text) VALUES('delete',old.id,old.text);
        END;
        CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE ON memory BEGIN
            INSERT INTO memory_fts(memory_fts,rowid,text) VALUES('delete',old.id,old.text);
            INSERT INTO memory_fts(rowid,text) VALUES(new.id,new.text);
        END;
    """)
    db.execute("INSERT INTO memory_fts(memory_fts) VALUES('rebuild')")
    db.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec USING vec0(embedding float[{dimension}])")

def validate_embedding(value: object) -> list[float]:
    if not isinstance(value, list) or len(value) != embedding_dimension():
        raise ValueError("embedding dimension mismatch")
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("embedding values must be finite numbers")
        number = float(item)
        if not math.isfinite(number):
            raise ValueError("embedding values must be finite numbers")
        result.append(number)
    return result

def serialize_embedding(value: object) -> bytes:
    import sqlite_vec
    return sqlite_vec.serialize_float32(validate_embedding(value))

def remember(db: sqlite3.Connection, text: str, embedding: object | None = None) -> int:
    cursor = db.execute("INSERT INTO memory(ts,text) VALUES(strftime('%s','now'),?)", (text,))
    row_id = int(cursor.lastrowid)
    if embedding is not None:
        db.execute("INSERT INTO memory_vec(rowid,embedding) VALUES(?,?)",
                   (row_id, serialize_embedding(embedding)))
    return row_id

def _fts_query(query: str) -> str:
    tokens = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
    return " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens[:32])

def recall(db: sqlite3.Connection, query: str = "", limit: int = 20,
           embedding: object | None = None) -> list[dict]:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    db.row_factory = sqlite3.Row
    sparse_ids = []
    fts_query = _fts_query(query)
    if fts_query:
        sparse_ids = [int(row[0]) for row in db.execute(
            "SELECT rowid FROM memory_fts WHERE memory_fts MATCH ? ORDER BY bm25(memory_fts) LIMIT ?",
            (fts_query, CANDIDATE_LIMIT))]
    dense_ids = []
    if embedding is not None:
        dense_ids = [int(row[0]) for row in db.execute(
            "SELECT rowid,distance FROM memory_vec WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (serialize_embedding(embedding), CANDIDATE_LIMIT))]
    if not sparse_ids and not dense_ids:
        if query.strip() or embedding is not None:
            return []
        rows = db.execute("SELECT id,ts,text FROM memory ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in reversed(rows)]
    scores = {}
    for ranked in (sparse_ids, dense_ids):
        for rank, row_id in enumerate(ranked, 1):
            scores[row_id] = scores.get(row_id, 0.0) + 1.0 / (RRF_K + rank)
    selected = sorted(scores, key=lambda row_id: (-scores[row_id], row_id))[:limit]
    if not selected:
        return []
    placeholders = ",".join("?" for _ in selected)
    rows = db.execute(f"SELECT id,ts,text FROM memory WHERE id IN ({placeholders})", selected).fetchall()
    by_id = {int(row["id"]): dict(row) for row in rows}
    return [by_id[row_id] for row_id in selected if row_id in by_id]
