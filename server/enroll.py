"""Validate public Android registration and emit public server environment values.

This is an offline operator tool, never a self-enrollment web endpoint. Confirm
the exported registration belongs to Mehmet through a trusted channel first.
The tool does not establish real-world identity from an owner label.
"""
import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def validated_env(registration):
    if not isinstance(registration, dict) or registration.get("contract") != "OMEGA-OWNER-API-V1":
        raise ValueError("REGISTRATION_CONTRACT_INVALID")
    owner = registration.get("owner_id")
    device = registration.get("device_id")
    if not isinstance(owner, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", owner):
        raise ValueError("OWNER_ID_INVALID")
    encoded = []
    for field in ("owner_public_der_b64", "device_public_der_b64"):
        value = registration.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,4096}", value):
            raise ValueError("PUBLIC_KEY_ENCODING_INVALID")
        der = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        key = serialization.load_der_public_key(der)
        if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ValueError("PUBLIC_KEY_TYPE_INVALID")
        canonical_der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        if canonical_der != der:
            raise ValueError("PUBLIC_KEY_DER_INVALID")
        encoded.append((value, der))
    if encoded[0][1] == encoded[1][1]:
        raise ValueError("DISTINCT_KEYS_REQUIRED")
    if device != hashlib.sha256(encoded[1][1]).hexdigest():
        raise ValueError("DEVICE_ID_MISMATCH")
    return {"OMEGA_OWNER_ID": owner, "OMEGA_DEVICE_ID": device,
            "OMEGA_OWNER_PUBLIC_DER_B64": encoded[0][0], "OMEGA_DEVICE_PUBLIC_DER_B64": encoded[1][0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registration", type=Path, help="Android public registration JSON")
    parser.add_argument("--verified-owner", required=True, help="Owner ID independently verified by the operator")
    args = parser.parse_args()
    try:
        if args.registration.stat().st_size > 16384:
            raise ValueError("REGISTRATION_TOO_LARGE")
        values = validated_env(json.loads(args.registration.read_text(encoding="utf-8")))
        if values["OMEGA_OWNER_ID"] != args.verified_owner:
            raise ValueError("VERIFIED_OWNER_MISMATCH")
    except Exception:
        print("Registration rejected; verify the public export and the owner through a trusted channel.", file=sys.stderr)
        return 1
    for key, value in values.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
