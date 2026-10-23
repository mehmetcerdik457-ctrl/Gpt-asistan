#!/usr/bin/env python3
"""CI-only: capture actual OMEGA localhost HTTP bytes, no real provider calls."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

PINNED_OMEGA = "fd34e1a6b57b13644c6f2053fe97e86b485de10b"
MAX_HEALTH = 4096


def run(omega_dir, output_dir):
    omega_dir = Path(omega_dir).resolve()
    source_sha = subprocess.check_output(
        ["git", "-C", str(omega_dir), "rev-parse", "HEAD"], text=True, timeout=5
    ).strip()
    if source_sha != PINNED_OMEGA:
        raise RuntimeError("OMEGA_SOURCE_MISMATCH")
    sys.path.insert(0, str(omega_dir / "backend"))
    import server

    os.environ["OPENAI_API_KEY"] = "SYNTHETIC_CI_CONTRACT_NOT_CREDENTIAL"
    os.environ["OMEGA_EXECUTION_ENABLED"] = "false"
    os.environ["OMEGA_OWNER_VERIFIED"] = "false"
    if server.owner_execution_authorized() is not False:
        raise RuntimeError("UNSAFE_OWNER_GATE")

    api = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=api.serve_forever, daemon=True)
    thread.start()
    root = "http://127.0.0.1:" + str(api.server_port)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path, data=None):
        req = urllib.request.Request(
            root + path, data=data,
            method="POST" if data is not None else "GET",
            headers={"Content-Type": "application/json"} if data is not None else {})
        try:
            with opener.open(req, timeout=4) as response:
                return response.status, response.headers.get_content_type(), response.read(MAX_HEALTH + 1)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers.get_content_type(), exc.read(MAX_HEALTH + 1)

    try:
        status, media, raw = request("/api/health")
        if status != 200 or media != "application/json" or not 0 < len(raw) <= MAX_HEALTH:
            raise RuntimeError("HEALTH_HTTP_DENIED")
        obj = json.loads(raw)
        if (obj.get("status") != "PASS" or obj.get("owner_identity_verified") is not False
                or obj.get("execution_enabled") is not False):
            raise RuntimeError("HEALTH_CLAIMS_UNSAFE")
        model_status, _, model_body = request("/api/models")
        chat_status, _, chat_body = request("/api/chat", b'{"message":"synthetic only"}')
        if (model_status != 403 or chat_status != 403
                or json.loads(model_body).get("error") != "OWNER_EXECUTION_NOT_APPROVED"
                or json.loads(chat_body).get("error") != "OWNER_EXECUTION_NOT_APPROVED"):
            raise RuntimeError("EXECUTION_UNEXPECTEDLY_ALLOWED")
    finally:
        api.shutdown()
        api.server_close()
        thread.join(timeout=3)

    dst = Path(output_dir)
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "health.json").write_bytes(raw)
    (dst / "evidence.json").write_text(json.dumps({
        "source_sha": source_sha,
        "transport": "real_loopback_http",
        "health_sha256": hashlib.sha256(raw).hexdigest(),
        "models_http_status": model_status,
        "chat_http_status": chat_status,
        "tls_tested": False,
        "android_physical_device_tested": False,
        "owner_enrolled": False,
        "execution_approved": False,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("OMEGA_REAL_HTTP_KOTLIN_INPUT=CAPTURED")
    print("OMEGA_EXECUTION=DENIED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--omega-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    run(args.omega_dir, args.out_dir)


if __name__ == "__main__":
    main()
