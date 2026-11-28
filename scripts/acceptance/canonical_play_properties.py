#!/usr/bin/env python3
"""Seeded property/mutation stress of the ACTUAL canonical Play server modules.

No Google service, HTTP server, signing service or database is contacted.
One generated case can perform several documented target calls; it is not a
pytest repetition count. Reproduction requires this script, seed, exact target
file hashes and the same Python runtime.
"""
from __future__ import annotations
import argparse
import base64
from collections import Counter
from dataclasses import asdict, replace
import hashlib
import hmac
import importlib
import inspect
import json
from pathlib import Path
import random
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

NOW = 1_794_000_000
NOW_MS = NOW * 1000
AUDIENCE = "https://stress.invalid/api/v1/play/rtdn"
EMAIL = "push@stress.iam.gserviceaccount.com"
SUBSCRIPTION = "projects/stress/subscriptions/canonical-rtdn"
SECRET = b"canonical-stress-synthetic-secret-32-bytes"
KNOWN_TYPES = (1,2,3,4,5,6,7,8,9,10,11,12,13,17,18,19,20,22)
SOURCE_FILES = (
    "server/play_rtdn.py", "server/play_entitlement_gate.py",
    "server/play_subscription_mapper.py", "server/play_account_id.py",
    "server/play_google_api.py", "server/play_subscription_lifecycle.py",
    "server/play_rtdn_store.py",
)
WEIGHTS = (("rtdn_parser", 50), ("oidc_claim_types", 15),
           ("entitlement_ownership", 20), ("fresh_provider_owner_mapping", 10),
           ("obfuscated_account_identity", 5))

def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",",":"),
                      default=lambda x: {"python_type":type(x).__name__,"repr":repr(x)}).encode()

def sha_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def snapshot(source):
    files = {name:sha_file(source/name) for name in SOURCE_FILES}
    manifest_hash = hashlib.sha256(canonical(files)).hexdigest()
    def git(*args):
        p = subprocess.run(["git",*args], cwd=source, capture_output=True, text=True, timeout=10)
        return p.stdout.strip() if p.returncode == 0 else None
    return {"repository_path":str(source), "git_commit":git("rev-parse","HEAD"),
            "git_tree":git("rev-parse","HEAD^{tree}"),
            "git_dirty_paths":git("status","--porcelain=v1"),
            "target_file_sha256":files, "target_manifest_sha256":manifest_hash}

class NetworkDenied(RuntimeError):
    pass

class NoNetwork:
    def __init__(self):
        self.attempts = 0
        self.originals = []
    def deny(self, *args, **kwargs):
        self.attempts += 1
        raise NetworkDenied("STRESS_NETWORK_FORBIDDEN")
    def install(self):
        for obj, name in ((socket,"create_connection"),(socket.socket,"connect"),
                          (urllib.request,"urlopen")):
            self.originals.append((obj,name,getattr(obj,name)))
            setattr(obj,name,self.deny)
    def restore(self):
        for obj,name,value in reversed(self.originals):
            setattr(obj,name,value)

class FakeResponse:
    status = 200
    def __init__(self, raw):
        self.raw = raw
    def read(self, size=-1):
        return self.raw if size < 0 else self.raw[:size]
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False

class Harness:
    def __init__(self, source, seed):
        self.source, self.rng, self.seed = source, random.Random(seed), seed
        self.rtdn = importlib.import_module("server.play_rtdn")
        self.gate = importlib.import_module("server.play_entitlement_gate")
        self.account = importlib.import_module("server.play_account_id")
        self.mapper = importlib.import_module("server.play_subscription_mapper")
        self.api = importlib.import_module("server.play_google_api")
        for module in (self.rtdn,self.gate,self.account,self.mapper,self.api):
            if not Path(inspect.getfile(module)).resolve().is_relative_to(source):
                raise RuntimeError("wrong target module imported")
        self.claims = None
        self.side_effect_attempts = 0
        self.provider_opener_calls = 0
        self.target_calls = Counter()
        def forbidden(*args, **kwargs):
            self.side_effect_attempts += 1
            raise RuntimeError("STRESS_PERSISTENCE_OR_OAUTH_FORBIDDEN")
        self.processor = self.rtdn.PlayRtdnProcessor(
            audience=AUDIENCE, service_account_email=EMAIL, subscription=SUBSCRIPTION,
            allowed_products={"orba_pro_monthly"}, server_secret=SECRET,
            db_factory=forbidden, oauth_supplier=forbidden,
            verifier=lambda *_:self.claims, clock=lambda:NOW,
        )

    def uid(self, i):
        return f"{i:x}-{self.rng.getrandbits(64):016x}"

    def event(self, uid, is_test=False):
        value = {"version":"1.0","packageName":self.gate.PACKAGE,
                 "eventTimeMillis":str(NOW_MS+self.rng.randrange(-100000,100000))}
        if is_test:
            value["testNotification"] = {"version":"1.0","case":uid}
        else:
            value["subscriptionNotification"] = {
                "version":"1.0","notificationType":self.rng.choice(KNOWN_TYPES),
                "purchaseToken":"token-"+uid,
            }
        return value

    def wrapped(self, event, uid, *, payload=None, data=None, subscription=SUBSCRIPTION):
        if payload is None:
            payload = json.dumps(event, ensure_ascii=True, separators=(",",":")).encode()
        if data is None:
            data = base64.b64encode(payload).decode()
        return json.dumps({"subscription":subscription,
            "message":{"messageId":"message-"+uid,"data":data}},
            separators=(",",":")).encode(), payload

    def parser_case(self, i):
        uid, mode = self.uid(i), i % 40
        is_test = mode in (0,1,2)
        event = self.event(uid,is_test)
        raw,payload = self.wrapped(event,uid)
        expected = mode < 8
        label = "valid_test" if is_test else "valid_subscription"
        token = None if is_test else event["subscriptionNotification"]["purchaseToken"]
        if mode == 3:
            outer=json.loads(raw)
            outer["message"]["message_id"]=outer["message"].pop("messageId")
            raw=canonical(outer);label="valid_legacy_snake_message_id"
        if mode == 8:
            raw,payload = self.wrapped(event,uid,subscription=SUBSCRIPTION+"-wrong")
            label="wrong_subscription"
        elif mode == 9:
            event["packageName"] += ".wrong"; raw,payload=self.wrapped(event,uid);label="wrong_package"
        elif mode == 10:
            event["subscriptionNotification"]["notificationType"]=True
            raw,payload=self.wrapped(event,uid);label="boolean_notification_type"
        elif mode == 11:
            outer=json.loads(raw);del outer["message"]["messageId"];raw=canonical(outer);label="missing_message_id"
        elif mode == 12:
            outer=json.loads(raw);outer["message"]=[uid];raw=canonical(outer);label="message_not_object"
        elif mode == 13:
            outer=json.loads(raw);outer["message"]["data"]="!"+outer["message"]["data"]
            raw=canonical(outer);label="invalid_base64"
        elif mode == 14:
            outer=json.loads(raw);outer["message"]["data"]+="\n"
            raw=canonical(outer);label="base64_whitespace"
        elif mode == 15:
            while len(payload)%3 != 2: payload += b" "
            encoded=base64.b64encode(payload).decode()
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
            altered=encoded[:-2]+alphabet[alphabet.index(encoded[-2])|1]+"="
            raw,_=self.wrapped(event,uid,payload=payload,data=altered);label="noncanonical_base64_padbits"
        elif mode == 16:
            raw=b'{"subscription":"wrong",'+raw[1:];label="duplicate_outer_subscription"
        elif mode == 17:
            raw=b'{"message":null,'+raw[1:];label="duplicate_outer_message"
        elif mode == 18:
            body=payload.decode(); marker='"packageName":'+json.dumps(self.gate.PACKAGE)
            body=body.replace(marker,'"packageName":"wrong",'+marker)
            raw,payload=self.wrapped(event,uid,payload=body.encode());label="duplicate_inner_package"
        elif mode == 19:
            body=payload.decode(); n=event["subscriptionNotification"]["notificationType"]
            body=body.replace('"notificationType":'+str(n),'"notificationType":false,"notificationType":'+str(n))
            raw,payload=self.wrapped(event,uid,payload=body.encode());label="duplicate_inner_notification_type"
        elif mode == 20:
            event["testNotification"]={"version":"1.0"};raw,payload=self.wrapped(event,uid);label="mixed_test_subscription"
        elif mode == 21:
            event=self.event(uid,True);event["voidedPurchaseNotification"]={"purchaseToken":"token-"+uid}
            raw,payload=self.wrapped(event,uid);label="mixed_test_voided"
        elif mode == 22:
            event["voidedPurchaseNotification"]={"purchaseToken":"token-"+uid}
            raw,payload=self.wrapped(event,uid);label="mixed_subscription_voided"
        elif mode == 23:
            event["subscriptionNotification"]["notificationType"]=99
            raw,payload=self.wrapped(event,uid);label="unknown_subscription_type"
        elif mode == 24:
            event["eventTimeMillis"]=True;raw,payload=self.wrapped(event,uid);label="boolean_event_time"
        elif mode == 25:
            event["eventTimeMillis"]="-"+str(i+1);raw,payload=self.wrapped(event,uid);label="negative_event_time"
        elif mode == 26:
            raw,payload=self.wrapped(event,uid,payload=canonical([event]));label="inner_not_object"
        elif mode == 27:
            raw=bytearray(raw);label="body_not_bytes"
        elif mode == 28:
            raw=b'{"case":"'+uid.encode()+b'","\xff":0}';label="invalid_utf8"
        elif mode == 29:
            event["subscriptionNotification"]=None;raw,payload=self.wrapped(event,uid);label="null_notification_detail"
        elif mode == 30:
            event["invalid_metric"]=float("nan");raw,payload=self.wrapped(event,uid);label="nonfinite_inner_json"
        elif mode == 31:
            raw=raw[:-1]+b',"nested":'+b"["*7000+json.dumps(uid).encode()+b"]"*7000+b"}"
            label="excessively_nested_json"
        elif mode == 32:
            raw=raw+b" "*(self.rtdn.MAX_BODY+1-len(raw));label="oversize_body"
        elif mode == 33:
            outer=json.loads(raw);outer["message"]["data"]={"case":uid};raw=canonical(outer);label="data_not_string"
        elif mode == 34:
            outer=json.loads(raw);outer["message"]["messageId"]="x"*129+uid;raw=canonical(outer);label="oversize_message_id"
        elif mode == 35:
            event["subscriptionNotification"]["notificationType"]=2.0
            raw,payload=self.wrapped(event,uid);label="float_notification_type"
        elif mode == 36:
            raw,payload=self.wrapped(event,uid,payload=canonical(None));label="null_inner_json"
        elif mode == 37:
            event["eventTimeMillis"]="9"*18;raw,payload=self.wrapped(event,uid);label="oversize_event_time"
        elif mode == 38:
            event["futureNotification"]={"case":uid};raw,payload=self.wrapped(event,uid);label="multiple_future_notification"
        elif mode == 39:
            outer=json.loads(raw);outer["message"]["message_id"]="conflict-"+uid
            raw=canonical(outer);label="conflicting_message_id_aliases"
        def invoke():
            self.target_calls["PlayRtdnProcessor.unpack"]+=1
            value=self.processor.unpack(raw)
            exact=(value[0]=="message-"+uid and value[1]==payload
                   and value[2]==token and value[3] is is_test)
            return True, exact
        return label,expected,bytes(raw),invoke,(self.rtdn.RtdnDenied,)

    def auth_case(self, i):
        uid,mode=self.uid(i),i%20
        claims={"iss":"https://accounts.google.com","aud":AUDIENCE,"email":EMAIL,
                "email_verified":True,"iat":NOW-self.rng.randrange(0,3599),
                "exp":NOW+self.rng.randrange(1,3601),"case":uid}
        authorization="Bearer synthetic."+uid+".signature"
        expected=mode<4;label="valid_injected_verified_claims"
        changes={
          4:("email_verified","true"),5:("email_verified",1),6:("email_verified",1.0),
          7:("email_verified",False),8:("aud",AUDIENCE+"-wrong"),
          9:("email","wrong@other.iam.gserviceaccount.com"),
          10:("iss","https://attacker.invalid"),11:("iss",[]),
          12:("iat",True),13:("exp",str(NOW+1000)),14:("iat",NOW+1),
          15:("exp",NOW),16:("iat",NOW-3601),
        }
        if mode in changes:
            field,value=changes[mode];claims[field]=value;label="invalid_"+field+"_"+type(value).__name__
        elif mode==17:
            authorization="Bearer "+uid+"\n";label="invalid_bearer_control"
        elif mode==18:
            claims=[uid];label="claims_not_object"
        elif mode==19:
            del claims["email_verified"];label="missing_verified_email"
        def invoke():
            self.claims=claims
            self.target_calls["PlayRtdnProcessor.authenticate"]+=1
            self.processor.authenticate(authorization)
            return True,True
        return label,expected,canonical([authorization,claims]),invoke,(self.rtdn.RtdnDenied,)

    def entitlement_case(self,i):
        uid,mode=self.uid(i),i%30
        owner="owner-"+uid;product="orba_pro_"+str(i)
        digest=hashlib.sha256(("token-"+uid).encode()).hexdigest()
        state=self.rng.choice(("SUBSCRIPTION_STATE_ACTIVE","SUBSCRIPTION_STATE_IN_GRACE_PERIOD","SUBSCRIPTION_STATE_CANCELED"))
        p=self.gate.VerifiedPlayPurchase(self.gate.PACKAGE,product,digest,owner,
                                        NOW_MS+self.rng.randrange(1,100000),state,True,True)
        args={"owner_id":owner,"product_id":product,"token_sha256":digest,"now_ms":NOW_MS}
        expected=mode<6;label="valid_owner_bound_access"
        edits={
          6:{"verified_by_google_api":"true"},7:{"verified_by_google_api":1},
          8:{"acknowledged":"true"},9:{"acknowledged":1},
          10:{"package_name":self.gate.PACKAGE+".wrong"},11:{"product_id":product+"_wrong"},
          12:{"owner_id":owner+"_wrong"},13:{"purchase_token_sha256":"0"*64},
          14:{"purchase_token_sha256":None},15:{"purchase_token_sha256":[]},
          16:{"purchase_token_sha256":"é"*64},17:{"expires_at_ms":True},
          18:{"expires_at_ms":NOW_MS},19:{"expires_at_ms":NOW_MS-1},
          20:{"subscription_state":"SUBSCRIPTION_STATE_ON_HOLD"},
          21:{"subscription_state":"SUBSCRIPTION_STATE_PAUSED"},
          22:{"subscription_state":"SUBSCRIPTION_STATE_EXPIRED"},
          23:{"subscription_state":"SUBSCRIPTION_STATE_PENDING"},
          24:{"subscription_state":"UNRECOGNIZED_"+uid},
          25:{"verified_by_google_api":False},
        }
        if mode in edits:
            values=edits[mode];p=replace(p,**values);label="invalid_purchase_"+next(iter(values))+"_"+str(mode)
        elif mode==26:
            args["owner_id"] += "_wrong";label="mismatched_request_owner"
        elif mode==27:
            args["now_ms"]=True;label="boolean_request_clock"
        elif mode==28:
            args["token_sha256"]="bad-"+uid;label="malformed_request_hash"
        elif mode==29:
            p=asdict(p);label="client_dict_not_verified_purchase"
        data=[asdict(p) if type(p) is self.gate.VerifiedPlayPurchase else p,args]
        def invoke():
            self.target_calls["entitlement_allowed"]+=1
            answer=self.gate.entitlement_allowed(p,**args)
            return answer, type(answer) is bool
        return label,expected,canonical(data),invoke,()

    def owner_mapping_case(self,i):
        uid,mode=self.uid(i),i%20
        owner="owner-"+uid;product="orba_pro_"+str(i);token="token-"+uid
        expected_hmac=hmac.new(SECRET,b"orba-play-obfuscated-account-v1\0"+owner.encode(),hashlib.sha256).hexdigest()
        body={"subscriptionState":"SUBSCRIPTION_STATE_ACTIVE",
              "acknowledgementState":"ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED",
              "lineItems":[{"productId":product,"expiryTime":"2030-01-01T00:00:00Z"}],
              "externalAccountIdentifiers":{"obfuscatedExternalAccountId":expected_hmac},
              "case":uid}
        expected=mode<4;label="valid_fresh_owner_mapping"
        if mode==4:
            body["externalAccountIdentifiers"]["obfuscatedExternalAccountId"]="0"*64;label="stolen_valid_token_other_owner"
        elif mode==5:
            del body["externalAccountIdentifiers"];label="missing_owner_association"
        elif mode==6:
            body["externalAccountIdentifiers"]["obfuscatedExternalAccountId"]=True;label="boolean_owner_association"
        elif mode==7:
            body["externalAccountIdentifiers"]["obfuscatedExternalAccountId"]="é"*64;label="unicode_owner_association"
        elif mode==8:
            body["lineItems"][0]["productId"] += "_wrong";label="wrong_response_product"
        elif mode==9:
            body["lineItems"]*=2;label="ambiguous_duplicate_line_items"
        elif mode==10:
            body["lineItems"][0]["expiryTime"]=True;label="boolean_response_expiry"
        elif mode==11:
            body["subscriptionState"]=[];label="nonstring_response_state"
        elif mode==12:
            body["acknowledgementState"]="unknown-"+uid;label="unknown_response_acknowledgement"
        elif mode==13:
            body["lineItems"]=[];label="empty_response_line_items"
        elif mode==14:
            body["invalid_metric"]=float("nan");label="nonfinite_provider_json"
        elif mode==15:
            body["externalAccountIdentifiers"]=None;label="null_response_owner_identifiers"
        elif mode==16:
            owner="";label="empty_authenticated_owner"
        elif mode==17:
            product=None;label="nonstring_requested_product"
        elif mode==18:
            body=[body];label="provider_not_object"
        raw=canonical(body)
        if mode==19:
            target='"obfuscatedExternalAccountId":'+json.dumps(expected_hmac)
            raw=raw.replace(target.encode(),('"obfuscatedExternalAccountId":"wrong",'+target).encode())
            label="duplicate_provider_owner_association"
        def opener(request,timeout):
            self.provider_opener_calls+=1
            if request.get_method()!="GET" or timeout!=8:
                raise RuntimeError("provider transport contract changed")
            return FakeResponse(raw)
        def invoke():
            self.target_calls["verify_and_map_subscription"]+=1
            mapped=self.mapper.verify_and_map_subscription(
                purchase_token=token, access_token="synthetic-offline-oauth",
                owner_id=owner, product_id=product, server_secret=SECRET, opener=opener)
            exact=(type(mapped) is self.gate.VerifiedPlayPurchase
                   and mapped.owner_id==owner and mapped.product_id==product
                   and mapped.purchase_token_sha256==hashlib.sha256(token.encode()).hexdigest()
                   and mapped.verified_by_google_api is True)
            return True,exact
        return label,expected,raw+canonical([owner,product,token]),invoke,(
            self.mapper.PlayMappingError,self.api.PlayVerificationError,ValueError)

    def account_case(self,i):
        uid,mode=self.uid(i),i%10
        owner="owner-"+uid;secret=hashlib.sha256(("key-"+uid).encode()).digest()
        expected=mode<4;label="valid_keyed_distinct_owner_reference"
        if mode==4: owner="";label="empty_owner"
        elif mode==5: owner=" "*self.rng.randrange(1,20);label="blank_owner"
        elif mode==6: owner="x"*257+uid;label="oversize_owner_utf8"
        elif mode==7: secret=secret[:self.rng.randrange(0,32)];label="short_account_secret"
        elif mode==8: secret="synthetic-"+uid;label="nonbytes_account_secret"
        elif mode==9: owner=None;label="nonstring_owner"
        def invoke():
            self.target_calls["obfuscated_play_account_id"]+=1
            value=self.account.obfuscated_play_account_id(authenticated_owner_id=owner,server_secret=secret)
            self.target_calls["obfuscated_play_account_id"]+=2
            again=self.account.obfuscated_play_account_id(authenticated_owner_id=owner,server_secret=secret)
            other=self.account.obfuscated_play_account_id(authenticated_owner_id=owner+"-other",server_secret=secret)
            exact=(type(value) is str and len(value)==64 and all(c in "0123456789abcdef" for c in value)
                   and value==again and value!=other and owner not in value)
            return True,exact
        return label,expected,canonical([owner,secret]),invoke,(ValueError,)

def run(args):
    source=args.source.resolve()
    if not (source/"server/play_rtdn.py").is_file():
        raise RuntimeError("canonical source not found")
    before=snapshot(source)
    sys.path.insert(0,str(source))
    network=NoNetwork();network.install()
    started=time.perf_counter()
    result={"schema":"omega.canonical.seeded-properties.v1","seed":args.seed,
            "python":sys.version,"python_executable":sys.executable,
            "python_recursion_limit":sys.getrecursionlimit(),
            "requested_generated_cases":args.cases,"generated_cases":0,
            "source_before":before,"families":{},"samples":[],
            "live_google_or_network_calls":False,"database_calls":False,
            "scope":"Seeded parser/schema, injected-OIDC-claim type checks and pure/fake-transport ownership properties; no real signer, delivery, durability or purchase proof"}
    digest=hashlib.sha256()
    try:
        h=Harness(source,args.seed)
        allocation=[(name,args.cases*weight//100) for name,weight in WEIGHTS]
        name,count=allocation[-1];allocation[-1]=(name,count+args.cases-sum(n for _,n in allocation))
        for family,count in allocation:
            family_start=time.perf_counter()
            stats=Counter();labels={}
            factory={"rtdn_parser":h.parser_case,"oidc_claim_types":h.auth_case,
                "entitlement_ownership":h.entitlement_case,
                "fresh_provider_owner_mapping":h.owner_mapping_case,
                "obfuscated_account_identity":h.account_case}[family]
            for i in range(count):
                label,expected,raw,invoke,rejections=factory(i)
                digest.update(family.encode()+b"\0"+str(i).encode()+b"\0"+label.encode()+b"\0")
                digest.update(hashlib.sha256(raw).digest())
                stats["generated"]+=1;stats["expected_accepted" if expected else "expected_rejected"]+=1
                label_stats=labels.setdefault(label,Counter())
                label_stats["generated"]+=1
                violated=False;unexpected=None;actual=None;reason=None
                try:
                    actual,exact=invoke()
                    if type(actual) is not bool:
                        stats["nonboolean_results"]+=1;reason="nonboolean_result";violated=True
                        actual=bool(actual)
                    stats["accepted" if actual else "rejected"]+=1
                    label_stats["accepted" if actual else "rejected"]+=1
                    if actual!=expected:
                        violated=True;reason="accepted_invalid" if actual else "rejected_valid"
                    if actual and not exact:
                        violated=True;reason="accepted_output_invariant"
                except rejections:
                    actual=False;stats["rejected"]+=1;label_stats["rejected"]+=1
                    if expected: violated=True;reason="rejected_valid"
                except Exception as exc:
                    unexpected=type(exc).__module__+"."+type(exc).__name__
                    stats["unexpected_exceptions"]+=1
                    label_stats["unexpected_exceptions"]+=1
                    violated=True;reason="unexpected_exception"
                if violated:
                    stats["invariant_violations"]+=1;label_stats["invariant_violations"]+=1
                    if len(result["samples"])<100:
                        result["samples"].append({"family":family,"index":i,"mutation":label,
                            "expected_accept":expected,"actual_accept":actual,"reason":reason,
                            "exception_type":unexpected,"input_sha256":hashlib.sha256(raw).hexdigest()})
                result["generated_cases"]+=1
            stats["elapsed_seconds"]=round(time.perf_counter()-family_start,6)
            result["families"][family]={"counts":dict(stats),
                "mutations":{k:dict(v) for k,v in sorted(labels.items())}}
            print(json.dumps({"progress_family":family,"counts":dict(stats)}),flush=True)
        result["target_function_calls"]=dict(h.target_calls)
        result["synthetic_provider_get_calls"]=h.provider_opener_calls
        result["forbidden_side_effect_attempts"]=h.side_effect_attempts
        result["blocked_network_attempts"]=network.attempts
    finally:
        network.restore()
    result["source_after"]=snapshot(source)
    result["target_sources_unchanged"]=(
        result["source_before"]["target_file_sha256"]==result["source_after"]["target_file_sha256"])
    result["elapsed_seconds"]=round(time.perf_counter()-started,6)
    result["generated_input_catalog_sha256"]=digest.hexdigest()
    result["harness_sha256"]=sha_file(Path(__file__).resolve())
    totals=Counter()
    for entry in result["families"].values():
        for key,value in entry["counts"].items():
            if key!="elapsed_seconds": totals[key]+=value
    result["totals"]=dict(totals)
    result["positive_controls_present"]=all(
        entry["counts"].get("expected_accepted",0)>0 for entry in result["families"].values())
    result["pass"]=bool(result["generated_cases"]==args.cases and
        result["target_sources_unchanged"] and result["positive_controls_present"] and
        not totals.get("invariant_violations") and not totals.get("unexpected_exceptions") and
        not result.get("forbidden_side_effect_attempts") and not result.get("blocked_network_attempts"))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf-8") as target:
        json.dump(result,target,ensure_ascii=True,sort_keys=True,indent=2);target.write("\n")
    print(json.dumps({"output":str(args.output),"generated_cases":result["generated_cases"],
        "totals":result["totals"],"elapsed_seconds":result["elapsed_seconds"],"pass":result["pass"],
        "target_sources_unchanged":result["target_sources_unchanged"]}),flush=True)
    return 0 if result["pass"] else 1

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--cases",type=int,default=1_000_000)
    p.add_argument("--seed",type=int,default=20261117)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if not 100<=args.cases<=10_000_000: p.error("cases must be 100..10000000")
    return run(args)

if __name__=="__main__":
    raise SystemExit(main())

