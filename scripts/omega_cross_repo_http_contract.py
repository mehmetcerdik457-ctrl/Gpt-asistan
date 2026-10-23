#!/usr/bin/env python3
"""CI-only: capture actual OMEGA localhost HTTP bytes, no real provider calls."""
import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

PINNED_OMEGA = "46894ad9d87ad7c75c3c51e003b1931e890199c4"
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
    import owner_auth_v1
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec

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

    def request(path, data=None, extra_headers=None):
        headers = {"Content-Type": "application/json"} if data is not None else {}
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(
            root + path, data=data,
            method="POST" if data is not None else "GET", headers=headers)
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

        # Existing KRAL's OmegaEnvelope.MODELS has exactly this P-256 wire form.
        # Keys are disposable CI-generated, never user Owner/Android keys.
        with tempfile.TemporaryDirectory(prefix="omega-models-signature-") as temp:
            owner_key = ec.generate_private_key(ec.SECP256R1())
            device_key = ec.generate_private_key(ec.SECP256R1())
            der = lambda key: key.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
            encode = lambda data: base64.urlsafe_b64encode(data).decode().rstrip("=")
            owner_id = "synthetic-ci-owner"
            device_id = hashlib.sha256(der(device_key)).hexdigest()
            os.environ["OMEGA_OWNER_ID"] = owner_id
            os.environ["OMEGA_DEVICE_ID"] = device_id
            os.environ["OMEGA_OWNER_PUBLIC_DER_B64"] = encode(der(owner_key))
            os.environ["OMEGA_DEVICE_PUBLIC_DER_B64"] = encode(der(device_key))
            os.environ["OMEGA_NONCE_DB"] = str(Path(temp) / "nonce.db")
            body = b"{}"
            timestamp = str(int(time.time()))
            nonce = uuid.uuid4().hex
            path = "/api/v1/owner/models"
            # Construct independently, checking interoperability with OMEGA.
            canonical = ("OMEGA-OWNER-API-V1\\nPOST\\n" + path + "\\n"
                + hashlib.sha256(body).hexdigest() + "\\n" + timestamp + "\\n"
                + nonce + "\\n" + owner_id + "\\n" + device_id).encode()
            if canonical != owner_auth_v1.canonical(
                "POST", path, body, timestamp, nonce, owner_id, device_id
            ):
                raise RuntimeError("OWNER_MODELS_WIRE_MISMATCH")
            headers = {
                "X-Omega-Owner-Id": owner_id,
                "X-Omega-Device-Id": device_id,
                "X-Omega-Timestamp": timestamp,
                "X-Omega-Nonce": nonce,
                "X-Omega-Owner-Proof": encode(owner_key.sign(canonical, ec.ECDSA(hashes.SHA256()))),
                "X-Omega-Device-Proof": encode(device_key.sign(canonical, ec.ECDSA(hashes.SHA256()))),
            }
            signed_models_status, _, signed_models_body = request(path, body, headers)
            replay_status, _, replay_body = request(path, body, headers)
            if (signed_models_status != 403
                or json.loads(signed_models_body).get("error") != "OWNER_EXECUTION_NOT_APPROVED"
                or replay_status != 403
                or json.loads(replay_body).get("error") != "OWNER_AUTH_REPLAY_OR_STORAGE_DENIED"):
                raise RuntimeError("OWNER_MODELS_SIGNED_POLICY_FAILED")
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
        "signed_models_http_status": signed_models_status,
        "signed_models_error": "OWNER_EXECUTION_NOT_APPROVED",
        "signed_models_replay_http_status": replay_status,
        "signed_models_replay_error": "OWNER_AUTH_REPLAY_OR_STORAGE_DENIED",
        "chat_http_status": chat_status,
        "tls_tested": False,
        "android_physical_device_tested": False,
        "owner_enrolled": False,
        "execution_approved": False,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("OMEGA_REAL_HTTP_KOTLIN_INPUT=CAPTURED")
    print("OMEGA_EXECUTION=DENIED")
    print("OMEGA_SIGNED_MODELS_ROUTE=VALID_SIGNATURE_BUT_DENIED")
    print("OMEGA_SIGNED_MODELS_REPLAY=DENIED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--omega-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    run(args.omega_dir, args.out_dir)


if __name__ == "__main__":
    main()
