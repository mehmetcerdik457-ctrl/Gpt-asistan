"""Disposable HTTPS fixture using the real gateway and a synthetic OpenAI transport.

Never use this process as a deployment. All keys are generated test identities;
the OpenAI transport is replaced before the gateway starts accepting requests.
"""
import argparse
import base64
import datetime
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path
import signal
import ssl
import tempfile
import threading
import urllib.error
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import uuid

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from server import gateway


def b64(value):
    return base64.b64encode(value).decode("ascii")


def public_der(key):
    return key.public_key().public_bytes(serialization.Encoding.DER,
                                         serialization.PublicFormat.SubjectPublicKeyInfo)


def private_der(key):
    return key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    if args.ready_file.exists():
        parser.error("Ready file already exists; preserve previous fixture evidence")
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix="kral-android-fixture-") as directory:
        root = Path(directory)
        owner, device, tls_key = (ec.generate_private_key(ec.SECP256R1()) for _ in range(3))
        now = datetime.datetime.now(datetime.timezone.utc)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "KRAL disposable localhost fixture")])
        certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(tls_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .sign(tls_key, hashes.SHA256()))
        cert_path, key_path = root / "certificate.pem", root / "tls-key.pem"
        cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(tls_key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        device_id = hashlib.sha256(public_der(device)).hexdigest()
        url_b64 = lambda value: base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
        environment = {
            "OPENAI_API_KEY": "synthetic-android-fixture-key",
            "OPENAI_ALLOWED_MODELS": "fixture-alias",
            "OMEGA_OWNER_ID": "android-fixture", "OMEGA_DEVICE_ID": device_id,
            "OMEGA_OWNER_PUBLIC_DER_B64": url_b64(public_der(owner)),
            "OMEGA_DEVICE_PUBLIC_DER_B64": url_b64(public_der(device)),
            "OMEGA_NONCE_DB": str(root / "nonces.sqlite3"),
        }
        evidence = {"mocked_responses_calls": 0, "external_provider_calls": 0,
                    "completed": 0, "typed_failures": 0}
        lock = threading.Lock()

        class SyntheticTransport:
            def open(self, request, **_kwargs):
                if request.full_url != "https://api.openai.com/v1/responses":
                    raise AssertionError("FIXTURE_DENIES_ALL_EXTERNAL_DESTINATIONS")
                payload = json.loads(request.data)
                user = payload["input"][-1]["content"]
                request_id = "req_fixture_" + uuid.uuid4().hex
                with lock:
                    evidence["mocked_responses_calls"] += 1
                for status, code in ((401, "invalid_api_key"), (403, "permission_denied"),
                                     (404, "model_not_found")):
                    if "KRAL_ACCEPT_" + str(status) in user:
                        with lock:
                            evidence["typed_failures"] += 1
                        raise urllib.error.HTTPError(request.full_url, status, "Synthetic failure",
                            {"x-request-id": request_id},
                            io.BytesIO(gateway.json_bytes({"error": {"code": code}})))
                if "KRAL_ACCEPT_TIMEOUT" in user:
                    raise TimeoutError("Synthetic timeout")
                body = {"id": "resp_fixture_" + uuid.uuid4().hex, "status": "completed",
                        "model": "fixture-model-001", "output": [{"type": "message",
                        "content": [{"type": "output_text", "text": "KRAL_OK"}]}]}
                response = io.BytesIO(gateway.json_bytes(body))
                response.status = 200
                response.headers = {"x-request-id": request_id}
                with lock:
                    evidence["completed"] += 1
                return response

        with patch.dict(os.environ, environment), \
                patch("server.gateway.urllib.request.build_opener", return_value=SyntheticTransport()):
            service = gateway.Gateway(gateway.Store(str(root / "data.sqlite3")))
            server = ThreadingHTTPServer(("127.0.0.1", args.port), gateway.handler_for(service))
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(str(cert_path), str(key_path))
            server.socket = context.wrap_socket(server.socket, server_side=True)
            info = {"pid": os.getpid(), "port": server.server_port,
                "instrumentation_args": {
                    "kralFixtureBase": "https://localhost:" + str(server.server_port),
                    "kralFixtureCa": b64(certificate.public_bytes(serialization.Encoding.DER)),
                    "kralFixtureOwnerPrivate": b64(private_der(owner)),
                    "kralFixtureDevicePrivate": b64(private_der(device)),
                    "kralFixtureDeviceId": device_id,
                }}
            with args.ready_file.open("x") as stream:
                json.dump(info, stream)
            print("KRAL_HTTPS_FIXTURE_READY port=" + str(server.server_port), flush=True)

            def stop(*_args):
                threading.Thread(target=server.shutdown, daemon=True).start()

            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            try:
                server.serve_forever()
            finally:
                server.server_close()
                service.tasks.close()
                evidence_path = args.ready_file.with_suffix(".evidence.json")
                evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
                print("KRAL_HTTPS_FIXTURE_STOPPED", flush=True)


if __name__ == "__main__":
    main()
