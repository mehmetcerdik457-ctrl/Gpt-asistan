# -*- coding: utf-8 -*-
import sqlite3, os, subprocess, datetime, sys

DB="mem.db"

def init_db():
    con=sqlite3.connect(DB)
    cur=con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS mem(id INTEGER PRIMARY KEY, ts TEXT, text TEXT)")
    con.commit(); con.close()

def save(text):
    con=sqlite3.connect(DB); cur=con.cursor()
    cur.execute("INSERT INTO mem(ts,text) VALUES(?,?)",(datetime.datetime.now().isoformat(timespec="seconds"), text))
    con.commit(); con.close()

def list_last(n=20):
    con=sqlite3.connect(DB); cur=con.cursor()
    cur.execute("SELECT ts,text FROM mem ORDER BY id DESC LIMIT ?",(n,))
    rows=cur.fetchall(); con.close(); return rows

def speak(text):
    try:
        subprocess.run(["termux-tts-speak", text], check=False)
    except Exception:
        pass

def main():
    init_db()
    print("Kral Asistan (güvenli/yerel). Komutlar: /kaydet <yazi> | /liste | /soyle <yazi> | /cik")
    while True:
        try:
            line=input("> ").strip()
        except EOFError:
            break
        if not line: 
            continue
        if line.startswith("/kaydet "):
            save(line[len("/kaydet "):].strip()); print("✓ kaydedildi")
        elif line == "/liste":
            rows=list_last(); 
            if not rows: print("(kayıt yok)")
            for ts,txt in rows[::-1]: print(f"[{ts}] {txt}")
        elif line.startswith("/soyle "):
            txt=line[len("/soyle "):].strip(); speak(txt); print("🗣️ söyledim")
        elif line == "/cik":
            print("görüşürüz kral"); break
        else:
            # basit cevap: hafızaya yaz ve tekrar et
            save(line); print(f"anladım: {line}")
if __name__=="__main__": main()
