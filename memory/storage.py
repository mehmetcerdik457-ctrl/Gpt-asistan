import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path


MAX_TEXT_LENGTH = 4096


class MemoryStorage:
    def __init__(self, db_path):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path, timeout=10.0)

    def init_db(self):
        with closing(self._connect()) as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS mem "
                "(id INTEGER PRIMARY KEY, ts TEXT, text TEXT)"
            )
            columns = {row[1] for row in con.execute("PRAGMA table_info(mem)")}
            for name in ("ts", "text"):
                if name not in columns:
                    con.execute(f"ALTER TABLE mem ADD COLUMN {name} TEXT")
            con.commit()

    def store(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
            return False
        with closing(self._connect()) as con:
            cursor = con.execute(
                "INSERT INTO mem(ts, text) VALUES (?, ?)",
                (datetime.now().isoformat(timespec="seconds"), text.strip()),
            )
            con.commit()
            return cursor.lastrowid

    def retrieve(self, limit=20):
        with closing(self._connect()) as con:
            rows = con.execute(
                "SELECT id, ts, text FROM mem ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"id": row[0], "ts": row[1], "text": row[2]} for row in reversed(rows)]

    def search(self, query, limit=20):
        if not isinstance(query, str) or not query:
            return []
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with closing(self._connect()) as con:
            rows = con.execute(
                "SELECT id, ts, text FROM mem WHERE text LIKE ? ESCAPE '\\' "
                "ORDER BY id DESC LIMIT ?",
                (f"%{escaped}%", limit),
            ).fetchall()
        return [{"id": row[0], "ts": row[1], "text": row[2]} for row in reversed(rows)]

    def export_json(self, path):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {"memories": self.retrieve(limit=-1)}
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def import_json(self, path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        records = payload.get("memories") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise ValueError("Backup must contain a list of memories.")
        imported = 0
        with closing(self._connect()) as con:
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError("Each memory must be an object.")
                text = record.get("text")
                if (
                    not isinstance(text, str)
                    or not text.strip()
                    or len(text) > MAX_TEXT_LENGTH
                ):
                    raise ValueError("Memory text must be non-empty and at most 4096 characters.")
                ts = record.get("ts") or datetime.now().isoformat(timespec="seconds")
                con.execute("INSERT INTO mem(ts, text) VALUES (?, ?)", (ts, text.strip()))
                imported += 1
            con.commit()
        return imported

    def clear(self):
        with closing(self._connect()) as con:
            con.execute("DELETE FROM mem")
            con.commit()
