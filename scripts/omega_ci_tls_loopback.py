#!/usr/bin/env python3
"""CI-only OMEGA backend serving temporary self-signed TLS on host loopback."""
import argparse
import base64
import hashlib
import json
import os
import ssl
import tempfile
import threading
import subprocess
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

OMEGA_SOURCE = "46894ad9d87ad7c75c3c51e003b1931e890199c4"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--omega-dir", required=True)
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    directory = Path(args.omega_dir).resolve()
    sha = subprocess.check_output(
        ["git", "-C", str(directory), "rev-parse", "HEAD"],
        text=True, timeout=5).strip()
    if sha != OMEGA_SOURCE:
        raise SystemExit("WRONG_OMEGA_SOURCE")
    sys.path.insert(0, str(directory / "backend"))
    import server
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    os.environ["OPENAI_API_KEY"] = "SYNTHETIC_CI_NOT_CREDENTIAL"
    os.environ["OMEGA_OWNER_VERIFIED"] = "false"
    os.environ["OMEGA_EXECUTION_ENABLED"] = "false"
    if server.owner_execution_authorized() is not False:
        raise SystemExit("OWNER_POLICY_OPEN")
    # Synthetic public-key fixture exists ONLY inside this disposable CI server.
    # The real OMEGA production handler never exposes /__ci__/synthetic-key-provision.
    for name in ("OMEGA_OWNER_ID", "OMEGA_DEVICE_ID", "OMEGA_OWNER_PUBLIC_DER_B64",
                 "OMEGA_DEVICE_PUBLIC_DER_B64", "OMEGA_NONCE_DB"):
        os.environ.pop(name, None)
    registered = threading.Event()
    lock = threading.Lock()

    class SyntheticOnlyHandler(server.Handler):
        def do_POST(self):
            if self.path != "/__ci__/synthetic-key-provision":
                return super().do_POST()
            with lock:
                if registered.is_set():
                    self._send(409, {"error": "CI_ALREADY_REGISTERED"})
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 8192:
                        raise ValueError("BODY_SIZE")
                    body = json.loads(self.rfile.read(size))
                    needed = {"owner_id", "device_id", "owner_public_der_b64",
                              "device_public_der_b64"}
                    if not isinstance(body, dict) or set(body) != needed:
                        raise ValueError("FIELDS")
                    if body["owner_id"] != "synthetic-ci-owner":
                        raise ValueError("IDENTITY")
                    owner_der = base64.urlsafe_b64decode(body["owner_public_der_b64"] + "===")
                    device_der = base64.urlsafe_b64decode(body["device_public_der_b64"] + "===")
                    if (len(owner_der) > 256 or len(device_der) > 256
                            or owner_der == device_der
                            or body["device_id"] != hashlib.sha256(device_der).hexdigest()):
                        raise ValueError("DEVICE")
                    for der in (owner_der, device_der):
                        key = serialization.load_der_public_key(der)
                        if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
                            raise ValueError("CURVE")
                except (TypeError, ValueError, KeyError, AttributeError):
                    self._send(400, {"error": "CI_FIXTURE_DENIED"})
                    return
                os.environ["OMEGA_OWNER_ID"] = body["owner_id"]
                os.environ["OMEGA_DEVICE_ID"] = body["device_id"]
                os.environ["OMEGA_OWNER_PUBLIC_DER_B64"] = body["owner_public_der_b64"]
                os.environ["OMEGA_DEVICE_PUBLIC_DER_B64"] = body["device_public_der_b64"]
                registered.set()
                self._send(201, {"ci_fixture_bound": True,
                                 "owner_identity_verified": False,
                                 "execution_enabled": False})

    with tempfile.TemporaryDirectory(prefix="omega-nonces-ci-") as temp:
        os.environ["OMEGA_NONCE_DB"] = str(Path(temp) / "nonce.sqlite")
        app = ThreadingHTTPServer(("127.0.0.1", 18443), SyntheticOnlyHandler)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.minimum_version = ssl.TLSVersion.TLSv1_2
        tls.load_cert_chain(args.cert, args.key)
        app.socket = tls.wrap_socket(app.socket, server_side=True)
        print("OMEGA_TLS_LOOPBACK_STARTED", flush=True)
        print("OMEGA_CI_SYNTHETIC_PUBLIC_KEYS_ONLY=READY", flush=True)
        app.serve_forever()


if __name__ == "__main__":
    main()
