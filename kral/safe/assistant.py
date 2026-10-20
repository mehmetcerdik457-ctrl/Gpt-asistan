# -*- coding: utf-8 -*-
import datetime
import sqlite3
import subprocess

DB = "mem.db"


def init_db():
    con = sqlite3.connect(DB)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS mem(id INTEGER PRIMARY KEY, ts TEXT, text TEXT)")
        con.commit()
    finally:
        con.close()


def save(text):
    con = sqlite3.connect(DB)
    try:
        con.execute(
            "INSERT INTO mem(ts,text) VALUES(?,?)",
            (datetime.datetime.now().isoformat(timespec="seconds"), text),
        )
        con.commit()
    finally:
        con.close()


def list_last(n=20):
    con = sqlite3.connect(DB)
    try:
        cur = con.cursor()
        cur.execute("SELECT ts,text FROM mem ORDER BY id DESC LIMIT ?", (n,))
        return cur.fetchall()
    finally:
        con.close()


def speak(text):
    """Speak through Termux TTS and return False if the engine is unavailable or fails."""
    text = text.strip()
    if not text:
        return False
    try:
        result = subprocess.run(["termux-tts-speak", text], check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def main():
    init_db()
    print("Kral Asistan (güvenli/yerel). Komutlar: /kaydet <yazi> | /liste | /soyle <yazi> | /cik")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line:
            continue
        if line.startswith("/kaydet "):
            text = line[len("/kaydet "):].strip()
            if text:
                save(text)
                print("kaydedildi")
            else:
                print("Kaydedilecek metin boş olamaz.")
        elif line == "/liste":
            rows = list_last()
            if not rows:
                print("(kayıt yok)")
            for ts, text in rows[::-1]:
                print(f"[{ts}] {text}")
        elif line.startswith("/soyle "):
            text = line[len("/soyle "):].strip()
            if speak(text):
                print("Sesli yanıt tamamlandı.")
            else:
                print("Sesli yanıt başarısız: Termux TTS kullanılamıyor veya metin boş.")
        elif line == "/cik":
            print("görüşürüz kral")
            break
        else:
            save(line)
            print(f"anladım: {line}")


if __name__ == "__main__":
    main()
