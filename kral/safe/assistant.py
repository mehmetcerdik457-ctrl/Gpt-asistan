#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request

DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"
DEFAULT_HF_MODEL = "openai/gpt-oss-20b:cheapest"
DEFAULT_SYSTEM_PROMPT = (
    "Sen Kral Asistan'sın. Kullanıcının özel mühendislik ve genel amaçlı AI asistanı olarak "
    "Türkçe, doğru, kısa ve kanıta dayalı yanıt ver. Gizli değerleri tekrar etme veya isteme."
)


def db_path() -> Path:
    explicit = os.getenv("KRAL_DB_PATH")
    if explicit:
        return Path(explicit).expanduser()
    root = Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return root / "kral-asistan" / "mem.db"


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE IF NOT EXISTS notes("
        "id INTEGER PRIMARY KEY, ts TEXT NOT NULL, text TEXT NOT NULL)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS chat("
        "id INTEGER PRIMARY KEY, ts TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL)"
    )
    con.commit()
    return con


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def save_note(text: str) -> None:
    with connect() as con:
        con.execute("INSERT INTO notes(ts,text) VALUES(?,?)", (now(), text))


def list_notes(limit: int = 20) -> list[tuple[str, str]]:
    with connect() as con:
        rows = con.execute(
            "SELECT ts,text FROM notes ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return list(reversed(rows))


def save_chat(role: str, text: str) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO chat(ts,role,text) VALUES(?,?,?)",
            (now(), role, text),
        )


def recent_chat(limit: int) -> list[tuple[str, str]]:
    if limit <= 0:
        return []
    with connect() as con:
        rows = con.execute(
            "SELECT role,text FROM chat ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return list(reversed(rows))


def speak(text: str) -> None:
    try:
        subprocess.run(["termux-tts-speak", text], check=False)
    except (FileNotFoundError, OSError):
        pass


def provider_config() -> tuple[str, str, str, str]:
    requested = os.getenv("KRAL_PROVIDER", "auto").strip().lower()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    hf_key = (
        os.getenv("HUGGINGFACE_TOKEN", "").strip()
        or os.getenv("HF_TOKEN", "").strip()
    )

    if requested not in {"auto", "openai", "huggingface", "hf"}:
        raise RuntimeError("KRAL_PROVIDER auto, openai veya huggingface olmalı.")

    if requested == "auto":
        if openai_key:
            requested = "openai"
        elif hf_key:
            requested = "huggingface"
        else:
            raise RuntimeError(
                "AI sağlayıcısı yapılandırılmamış. Codespaces secret olarak "
                "OPENAI_API_KEY veya HUGGINGFACE_TOKEN ekle."
            )

    if requested == "openai":
        if not openai_key:
            raise RuntimeError("OPENAI_API_KEY yapılandırılmamış.")
        return (
            "openai",
            openai_key,
            os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        )

    if not hf_key:
        raise RuntimeError("HUGGINGFACE_TOKEN yapılandırılmamış.")
    return (
        "huggingface",
        hf_key,
        os.getenv("HF_BASE_URL", "https://router.huggingface.co/v1"),
        os.getenv("HF_MODEL", DEFAULT_HF_MODEL),
    )


def request_json(base_url: str, token: str, payload: dict) -> dict:
    url = base_url.rstrip("/") + "/responses"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "User-Agent": "kral-asistan/1",
        },
    )
    timeout = max(10, min(int(os.getenv("KRAL_HTTP_TIMEOUT", "90")), 180))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"AI sağlayıcısı HTTP {exc.code} döndürdü.") from None
    except urllib.error.URLError as exc:
        raise RuntimeError("AI sağlayıcısına ağ bağlantısı kurulamadı.") from exc


def extract_output(data: dict) -> str:
    direct = data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    parts: list[str] = []
    for item in data.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                parts.append(content["text"])
    result = "".join(parts).strip()
    if not result:
        raise RuntimeError("AI sağlayıcısı metin çıktısı döndürmedi.")
    return result


def build_input(user_text: str) -> str:
    turns = max(0, min(int(os.getenv("KRAL_CONTEXT_TURNS", "8")), 40))
    history = recent_chat(turns * 2)
    chunks = []
    if history:
        chunks.append("Önceki konuşma:")
        for role, text in history:
            chunks.append(f"{role}: {text}")
        chunks.append("")
    chunks.append("Kullanıcı:")
    chunks.append(user_text)
    return "\n".join(chunks)


def ask_model(user_text: str) -> tuple[str, str, str]:
    text = user_text.strip()
    if not text:
        raise RuntimeError("Boş prompt gönderilemez.")
    max_chars = max(1000, min(int(os.getenv("KRAL_MAX_INPUT_CHARS", "12000")), 50000))
    if len(text) > max_chars:
        raise RuntimeError(f"Prompt {max_chars} karakter sınırını aşıyor.")

    provider, token, base_url, model = provider_config()
    max_output = max(64, min(int(os.getenv("KRAL_MAX_OUTPUT_TOKENS", "1200")), 8000))
    payload = {
        "model": model,
        "instructions": os.getenv("KRAL_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
        "input": build_input(text),
        "max_output_tokens": max_output,
    }
    data = request_json(base_url, token, payload)
    answer = extract_output(data)
    save_chat("user", text)
    save_chat("assistant", answer)
    return answer, provider, model


def print_status() -> None:
    requested = os.getenv("KRAL_PROVIDER", "auto").strip().lower()
    openai = bool(os.getenv("OPENAI_API_KEY", "").strip())
    hf = bool(
        os.getenv("HUGGINGFACE_TOKEN", "").strip()
        or os.getenv("HF_TOKEN", "").strip()
    )
    print(f"KRAL_PROVIDER={requested}")
    print(f"OPENAI_CONFIGURED={'YES' if openai else 'NO'}")
    print(f"HUGGINGFACE_CONFIGURED={'YES' if hf else 'NO'}")
    print(f"OPENAI_MODEL={os.getenv('OPENAI_MODEL', DEFAULT_OPENAI_MODEL)}")
    print(f"HF_MODEL={os.getenv('HF_MODEL', DEFAULT_HF_MODEL)}")
    print(f"LOCAL_MEMORY={db_path()}")


def handle_prompt(text: str) -> int:
    try:
        answer, provider, model = ask_model(text)
    except RuntimeError as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        return 2
    print(answer)
    print(f"\n[provider={provider} model={model}]", file=sys.stderr)
    return 0


def interactive() -> int:
    connect().close()
    print(
        "Kral Asistan. Komutlar: /durum | /kaydet <yazi> | /liste | "
        "/soyle <yazi> | /cik"
    )
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line == "/cik":
            return 0
        if line == "/durum":
            print_status()
            continue
        if line.startswith("/kaydet "):
            save_note(line[len("/kaydet "):].strip())
            print("✓ yerel hafızaya kaydedildi")
            continue
        if line == "/liste":
            rows = list_notes()
            if not rows:
                print("(kayıt yok)")
            for ts, text in rows:
                print(f"[{ts}] {text}")
            continue
        if line.startswith("/soyle "):
            text = line[len("/soyle "):].strip()
            speak(text)
            print("🗣️ gönderildi")
            continue
        handle_prompt(line)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Kral Asistan private AI console")
    parser.add_argument("--ask", help="Tek seferlik prompt")
    parser.add_argument("--status", action="store_true", help="Secret değerlerini göstermeden durum")
    args = parser.parse_args()
    if args.status:
        print_status()
        return 0
    if args.ask is not None:
        return handle_prompt(args.ask)
    return interactive()


if __name__ == "__main__":
    raise SystemExit(main())
