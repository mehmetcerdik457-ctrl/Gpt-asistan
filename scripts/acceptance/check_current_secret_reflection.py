"""Independent current-tree secret reflection attack, synthetic sentinel only."""
import base64, hashlib, http.client, io, json, os, sys, tempfile, threading, time, unittest, urllib.error, uuid
from pathlib import Path
from unittest.mock import patch
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, os.getenv('KRAL_INDEPENDENT_SOURCE', str(REPO_ROOT)))
from server import gateway as g
from server import owner_auth_v1 as auth
SENTINEL='KRAL_ISOLATED_SECRET_SENTINEL_20261104'

class Response(io.BytesIO):
    status=200
    def __init__(self,payload,headers=None):super().__init__(json.dumps(payload).encode());self.headers=headers or {}

def payload():return {'status':'completed','model':'isolated-model','id':'resp_isolated', 'output':[{'type':'message','content':[{'type':'output_text','text':'Harmless isolated output'}]}]}

def b64(raw):return base64.urlsafe_b64encode(raw).decode().rstrip('=')
def der(key):return key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)

class SecretReflection(unittest.TestCase):
    def test_error_metadata_exact_and_embedded_key_are_omitted(self):
        for reflected in (SENTINEL,'prefix_'+SENTINEL+'_suffix'):
            with self.subTest(shape='exact' if reflected==SENTINEL else 'embedded'):
                with patch.dict(os.environ,{'OPENAI_API_KEY':SENTINEL}),patch('urllib.request.build_opener') as opener:
                    opener.return_value.open.side_effect=urllib.error.HTTPError('https://api.openai.com/v1/responses',401,'not public',{'x-request-id':reflected},io.BytesIO(json.dumps({'error':{'code':reflected,'message':SENTINEL}}).encode()))
                    with self.assertRaises(g.Denied) as caught:g.OpenAIProvider().reply('isolated-model','harmless')
                    self.assertIsNone(caught.exception.provider_request_id);self.assertIsNone(caught.exception.provider_error_code)
                    self.assertNotIn(SENTINEL,str(caught.exception))
    def test_success_header_key_is_omitted(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':SENTINEL}),patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=Response(payload(),{'x-request-id':'prefix_'+SENTINEL})
            text,model,elapsed,metadata=g.OpenAIProvider().reply_with_metadata('isolated-model','harmless')
            self.assertIsNone(metadata['request_id']);self.assertNotIn(SENTINEL,json.dumps(metadata))
    def test_success_secret_bearing_model_id_and_text_are_rejected(self):
        for field in ('model','id','text'):
            body=payload()
            if field=='text':body['output'][0]['content'][0]['text']='prefix_'+SENTINEL
            else:body[field]='prefix_'+SENTINEL
            with self.subTest(field=field),patch.dict(os.environ,{'OPENAI_API_KEY':SENTINEL}),patch('urllib.request.build_opener') as opener:
                opener.return_value.open.return_value=Response(body)
                with self.assertRaises(g.Denied) as caught:g.OpenAIProvider().reply('isolated-model','harmless')
                self.assertNotIn(SENTINEL,str(caught.exception))
    def test_real_signed_http_error_and_saved_history_exclude_upstream_key(self):
        with tempfile.TemporaryDirectory(prefix='kral-reflection-http-') as temp:
            owner=ec.generate_private_key(ec.SECP256R1());device=ec.generate_private_key(ec.SECP256R1())
            device_id=hashlib.sha256(der(device)).hexdigest()
            env={'OPENAI_API_KEY':SENTINEL,'OPENAI_ALLOWED_MODELS':'isolated-model','OMEGA_OWNER_ID':'isolated-owner',
                 'OMEGA_DEVICE_ID':device_id,'OMEGA_OWNER_PUBLIC_DER_B64':b64(der(owner)),
                 'OMEGA_DEVICE_PUBLIC_DER_B64':b64(der(device)),'OMEGA_NONCE_DB':temp+'/nonce.db'}
            def upstream(request,**kwargs):
                sent=json.loads(request.data)
                if sent['max_output_tokens']==64:return Response(payload())
                raise urllib.error.HTTPError('https://api.openai.com/v1/responses',401,'not public',{'x-request-id':SENTINEL},io.BytesIO(json.dumps({'error':{'code':SENTINEL,'message':SENTINEL}}).encode()))
            with patch.dict(os.environ,env),patch('urllib.request.build_opener') as opener:
                opener.return_value.open.side_effect=upstream
                gateway=g.Gateway(g.Store(temp+'/store.db'))
                httpd=g.ThreadingHTTPServer(('127.0.0.1',0),g.handler_for(gateway))
                thread=threading.Thread(target=lambda:httpd.serve_forever(poll_interval=.05),daemon=True);thread.start()
                def post(route,data):
                    path=g.PREFIX+route;raw=g.json_bytes(data);ts=str(int(time.time()));nonce=uuid.uuid4().hex
                    message=auth.canonical('POST',path,raw,ts,nonce,'isolated-owner',device_id)
                    headers={'Content-Type':'application/json','X-Omega-Owner-Id':'isolated-owner','X-Omega-Device-Id':device_id,'X-Omega-Timestamp':ts,'X-Omega-Nonce':nonce,
                             'X-Omega-Owner-Proof':b64(owner.sign(message,ec.ECDSA(hashes.SHA256()))),'X-Omega-Device-Proof':b64(device.sign(message,ec.ECDSA(hashes.SHA256())))}
                    conn=http.client.HTTPConnection('127.0.0.1',httpd.server_port,timeout=5)
                    try:conn.request('POST',path,body=raw,headers=headers);res=conn.getresponse();return res.status,json.loads(res.read())
                    finally:conn.close()
                try:
                    self.assertEqual(post('models',{})[0],200)
                    status,body=post('chat',{'message':'Harmless independent security test','model':'isolated-model'})
                    self.assertEqual(status,502);self.assertEqual(body['error'],'PROVIDER_AUTH_DENIED')
                    self.assertIsNone(body['provider_request_id']);self.assertIsNone(body['provider_error_code'])
                    self.assertNotIn(SENTINEL,json.dumps(body))
                    status,history=post('history',{})
                    self.assertEqual(status,200);self.assertEqual(history['messages'],[])
                    self.assertNotIn(SENTINEL,json.dumps(history))
                finally:httpd.shutdown();httpd.server_close();thread.join(timeout=2);gateway.tasks.close()

if __name__=='__main__':
    print('Examined gateway source SHA-256: '+hashlib.sha256(Path(g.__file__).read_bytes()).hexdigest())
    unittest.main(verbosity=2)
