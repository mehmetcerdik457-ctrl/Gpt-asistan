#!/usr/bin/env python3
"""CI-only OMEGA backend serving temporary self-signed TLS on host loopback."""
import argparse
import os
import ssl
import subprocess
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

OMEGA_SOURCE = "fd34e1a6b57b13644c6f2053fe97e86b485de10b"


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

    os.environ["OPENAI_API_KEY"] = "SYNTHETIC_CI_NOT_CREDENTIAL"
    os.environ["OMEGA_OWNER_VERIFIED"] = "false"
    os.environ["OMEGA_EXECUTION_ENABLED"] = "false"
    if server.owner_execution_authorized() is not False:
        raise SystemExit("OWNER_POLICY_OPEN")
    app = ThreadingHTTPServer(("127.0.0.1", 18443), server.Handler)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    tls.load_cert_chain(args.cert, args.key)
    app.socket = tls.wrap_socket(app.socket, server_side=True)
    print("OMEGA_TLS_LOOPBACK_STARTED", flush=True)
    app.serve_forever()


if __name__ == "__main__":
    main()
