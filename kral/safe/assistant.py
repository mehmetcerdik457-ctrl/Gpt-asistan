# -*- coding: utf-8 -*-
import logging
import os
import sqlite3
import subprocess
from contextlib import closing
from datetime import datetime
from pathlib import Path

DB="mem.db"
MAX_TEXT_LENGTH = 4096


def get_db_path():
    return Path(
        os.environ.get("KRAL_DB_PATH", Path(__file__).resolve().with_name(DB))
    ).expanduser()


def get_connection():
    """Return a SQLite connection for the configured local database."""
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path, timeout=10.0)


def init_db():
    """Create the memory table when it does not already exist."""
    try:
        with closing(get_connection()) as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS mem "
                "(id INTEGER PRIMARY KEY, ts TEXT, text TEXT)"
            )
            con.commit()
        logging.info("Veritabanı başarıyla başlatıldı.")
    except sqlite3.Error as exc:
        logging.error("Veritabanı başlatma hatası: %s", exc)
        print(f"❌ Veritabanı hatası: {exc}")


def save(text):
    """Store non-empty text up to the configured safety limit."""
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
        return False

    try:
        with closing(get_connection()) as con:
            con.execute(
                "INSERT INTO mem(ts, text) VALUES (?, ?)",
                (datetime.now().isoformat(timespec="seconds"), text.strip()),
            )
            con.commit()
        logging.info("Kayıt eklendi.")
        return True
    except sqlite3.Error as exc:
        logging.error("Kayıt ekleme hatası: %s", exc)
        return False


def list_last(n=20):
    """Return the most recent memory records."""
    try:
        with closing(get_connection()) as con:
            rows = con.execute(
                "SELECT ts, text FROM mem ORDER BY id DESC LIMIT ?", (n,)
            ).fetchall()
        return rows
    except sqlite3.Error as exc:
        logging.error("Listeleme hatası: %s", exc)
        return []


def speak(text):
    """Use Termux TTS when available, reporting failures through logging."""
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
        return False
    try:
        result = subprocess.run(
            ["termux-tts-speak", text],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode:
            logging.warning("Termux TTS exited with status %s.", result.returncode)
            return False
        return True
    except FileNotFoundError:
        logging.warning("termux-tts-speak command was not found.")
    except subprocess.TimeoutExpired:
        logging.warning("Termux TTS timed out.")
    except OSError as exc:
        logging.error("Termux TTS failed: %s", exc)
    return False


def configure_logging():
    log_dir = Path(os.environ.get("KRAL_LOG_DIR", Path(__file__).parent)).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_dir / "kral_assistant.log",
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def main():
    configure_logging()
    init_db()
    print("Kral Asistan (güvenli/yerel). Komutlar: /kaydet <yazi> | /liste | /soyle <yazi> | /cik")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.startswith("/kaydet "):
            if save(line[len("/kaydet "):].strip()):
                print("✓ kaydedildi")
            else:
                print("⚠️ Metin boş olamaz veya 4096 karakterden uzun olamaz.")
        elif line == "/liste":
            rows = list_last()
            if not rows:
                print("(kayıt yok)")
            for ts, txt in rows[::-1]:
                print(f"[{ts}] {txt}")
        elif line.startswith("/soyle "):
            txt = line[len("/soyle "):].strip()
            if speak(txt):
                print("🗣️ söyledim")
            else:
                print("⚠️ Sesli okuma başarısız.")
        elif line == "/cik":
            print("görüşürüz kral")
            break
        else:
            if save(line):
                print(f"anladım: {line}")
            else:
                print("⚠️ Metin boş olamaz veya 4096 karakterden uzun olamaz.")


if __name__ == "__main__":
    main()
