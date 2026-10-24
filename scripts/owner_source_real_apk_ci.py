"""Local-only PR50 verification using an actual APK, with fresh temporary keys.

Does NOT enroll production Owner identities, reach external networks, invoke models,
or modify the input APK. 127.0.0.1 only. Run from PR50 source root:
  PYTHONPATH=. python scripts/owner_source_real_apk_ci.py APK_PATH
"""
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
import threading
import time
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from server import owner_auth_v1 as auth
from server.gateway import BoundedThreadingHTTPServer, Gateway, Store, handler_for


def b64(data):
    return base64.urlsafe_b64encode(data).decode().rstrip('=')


class DenyLiveModels:
    name = 'offline-real-apk-check'

    def configured(self):
        return False

    def reply(self, *_args, **_kwargs):
        raise AssertionError('Unexpected model call')


def main(file):
    supplied = Path(file)
    original = hashlib.sha256(supplied.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='kral-real-apk-test-') as tmp:
        root = Path(tmp)
        checked = root / 'reference.apk'
        shutil.copyfile(supplied, checked)
        assert hashlib.sha256(checked.read_bytes()).hexdigest() == original
        owner_priv = ec.generate_private_key(ec.SECP256R1())
        device_priv = ec.generate_private_key(ec.SECP256R1())
        def der(priv):
            return priv.public_key().public_bytes(serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo)
        owner_der, device_der = der(owner_priv), der(device_priv)
        owner_id = 'offline-apk-ci-owner'
        device_id = hashlib.sha256(device_der).hexdigest()
        endpoint = '/api/v1/owner/sources'
        body = json.dumps({'action': 'inspect', 'source_id': 'reference.apk'},
                          separators=(',', ':')).encode()
        nonce = secrets.token_hex(24)
        timestamp = str(int(time.time()))
        canonical = auth.canonical('POST', endpoint, body, timestamp, nonce, owner_id, device_id)
        headers = {
            'Content-Type': 'application/json',
            'X-Omega-Owner-Id': owner_id,
            'X-Omega-Device-Id': device_id,
            'X-Omega-Timestamp': timestamp,
            'X-Omega-Nonce': nonce,
            'X-Omega-Owner-Proof': b64(owner_priv.sign(canonical, ec.ECDSA(hashes.SHA256()))),
            'X-Omega-Device-Proof': b64(device_priv.sign(canonical, ec.ECDSA(hashes.SHA256()))),
        }
        env = {
            'OMEGA_OWNER_ID': owner_id,
            'OMEGA_DEVICE_ID': device_id,
            'OMEGA_OWNER_PUBLIC_DER_B64': b64(owner_der),
            'OMEGA_DEVICE_PUBLIC_DER_B64': b64(device_der),
            'OMEGA_NONCE_DB': str(root / 'nonce.sqlite3'),
            'OMEGA_DATA_DB': str(root / 'data.sqlite3'),
            'KRAL_SOURCE_ROOT': tmp,
        }
        with patch.dict(os.environ, env, clear=False):
            gateway = Gateway(Store(env['OMEGA_DATA_DB']), provider=DenyLiveModels())
            server = BoundedThreadingHTTPServer(('127.0.0.1', 0), handler_for(gateway), max_workers=2)
            runner = threading.Thread(target=server.serve_forever, daemon=True)
            runner.start()
            try:
                def request(body_arg, headers_arg):
                    conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=8)
                    try:
                        conn.request('POST', endpoint, body_arg, headers_arg)
                        response = conn.getresponse()
                        return response.status, json.loads(response.read())
                    finally:
                        conn.close()
                unauthorized_code, _ = request(body, {'Content-Type': 'application/json'})
                success_code, result = request(body, headers)
                replay_code, replay = request(body, headers)
                assert unauthorized_code == 403, unauthorized_code
                assert success_code == 200, (success_code, result)
                assert replay_code == 403, (replay_code, replay)
                source = result['source']
                assert source['read_only'] is True
                assert source['status'] == 'ANALYZED_STATIC', source
                assert source['sha256'] == original
                assert source['size_bytes'] == supplied.stat().st_size
                assert source['apk_structure']['status'] == 'ZIP_STRUCTURE_VERIFIED', source
                assert source['apk_structure']['model_inference_tested'] is False
                assert source['integration_status'] == 'NOT_CONNECTED'
                assert hashlib.sha256(supplied.read_bytes()).hexdigest() == original
                assert hashlib.sha256(checked.read_bytes()).hexdigest() == original
                result_log = {
                    'check': 'PR50 temporary-key signed HTTP + actual APK bytes',
                    'source_git_commit': os.environ.get('KRAL_EXACT_HEAD_SHA'),
                    'api': endpoint,
                    'real_apk_sha256': original,
                    'real_apk_size': supplied.stat().st_size,
                    'first_unauthenticated_status': unauthorized_code,
                    'signed_status': success_code,
                    'replay_status': replay_code,
                    'static_apk_structure': source['apk_structure'],
                    'original_untouched': True,
                    'uses_temporary_owner_keys': True,
                    'physical_device_verified': False,
                    'live_model_verified': False,
                    'production_owner_enrolled': False,
                }
                print(json.dumps(result_log, indent=2, ensure_ascii=False))
            finally:
                server.shutdown()
                server.server_close()
                runner.join(timeout=6)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: python scripts/owner_source_real_apk_ci.py APK_PATH')
    main(sys.argv[1])
