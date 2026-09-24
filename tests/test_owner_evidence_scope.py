"""Regression tests for the evidence/physical-acceptance trust boundary."""
import contextlib
import copy
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"tools"))
import verify_owner_real_device as v

HEAD="a"*40

class EvidenceScopeTests(unittest.TestCase):
    def rejected(self,fn):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as raised: fn()
        self.assertEqual(raised.exception.code,2)

    def test_ci_fixture_never_claims_physical_acceptance(self):
        result=v.validate_full(v.owner_fixture(),v.bridge_fixture(),HEAD)
        self.assertEqual(result["status"],"FULL_EVIDENCE_CONTENT_VALIDATED")
        self.assertEqual(result["physical_device_status"],"NOT_VERIFIED")
        self.assertNotIn("verified_actions",result)
        self.assertNotIn("RECORD",result["reported_actions"])

    def test_phone_name_or_asserted_physical_flag_is_not_attestation(self):
        owner=v.owner_fixture();owner["evidence"]["device_model"]="Infinix X6851"
        owner["physical_device_status"]="VERIFIED_REAL_DEVICE"
        result=v.validate_full(owner,v.bridge_fixture(),HEAD)
        self.assertEqual(result["physical_device_status"],"NOT_VERIFIED")
        self.assertIn("same_device_and_fresh_session",result["unverified_requirements"])

    def test_every_frozen_owner_identity_is_enforced(self):
        for key in ["package_name","version_name","version_code","artifact_sha256","signer_cert_sha256"]:
            with self.subTest(key=key):
                owner=v.owner_fixture();owner["evidence"][key]="incorrect"
                self.rejected(lambda:v.validate_full(owner,v.bridge_fixture(),HEAD))
        owner=v.owner_fixture();owner["git_head"]="b"*40
        self.rejected(lambda:v.validate_full(owner,v.bridge_fixture(),HEAD))

    def test_every_frozen_bridge_identity_is_enforced(self):
        for key in ["bridge_package","bridge_version_name","bridge_version_code","bridge_artifact_sha256","bridge_signer_cert_sha256","owner_package","owner_signer_cert_sha256"]:
            with self.subTest(key=key):
                bridge=v.bridge_fixture();bridge[key]="incorrect"
                self.rejected(lambda:v.validate_full(v.owner_fixture(),bridge,HEAD))

    def test_missing_runtime_claims_reject(self):
        for key in ["accessibility_enabled","service_connected","tap_pass","click_text_pass","scroll_forward_pass"]:
            owner=v.owner_fixture();owner["phone_agent"][key]=False
            self.rejected(lambda:v.validate_full(owner,v.bridge_fixture(),HEAD))
        for key in ["service_connected","launch_app_pass","swipe_pass","type_text_pass","verify_postcondition_pass"]:
            bridge=v.bridge_fixture();bridge[key]=False
            self.rejected(lambda:v.validate_full(v.owner_fixture(),bridge,HEAD))

    def test_events_are_required_not_just_boolean_flags(self):
        owner=v.owner_fixture();owner["phone_agent"]["events"]=[]
        self.rejected(lambda:v.validate_full(owner,v.bridge_fixture(),HEAD))
        bridge=v.bridge_fixture();bridge["events"]=[]
        self.rejected(lambda:v.validate_full(v.owner_fixture(),bridge,HEAD))

    def test_target_hit_requires_positive_integer(self):
        for value in [True,False,"1","bad",None,0,-1,1.5]:
            owner=v.owner_fixture();owner["phone_agent"]["self_test_target_hits"]=value
            self.rejected(lambda:v.validate_full(owner,v.bridge_fixture(),HEAD))

    def test_invalid_object_shapes_fail_closed(self):
        for value in [None,[],"text",42]:
            self.rejected(lambda:v.validate_owner(value))
            self.rejected(lambda:v.validate_bridge(value))
            owner=v.owner_fixture();owner["phone_agent"]["events"]=value
            self.rejected(lambda:v.validate_owner(owner))
        bridge=v.bridge_fixture();bridge["version"]=True
        self.rejected(lambda:v.validate_bridge(bridge))
        for value in [[],{},None,42]:
            owner=v.owner_fixture();owner["phone_agent"]["events"][0]["action"]=value
            self.rejected(lambda:v.validate_owner(owner))

    def test_device_metadata_required_but_not_physical_proof(self):
        for key in ["device_model","android_version"]:
            owner=v.owner_fixture();owner["evidence"].pop(key)
            self.rejected(lambda:v.validate_owner(owner))

    def test_malformed_duplicate_and_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path=pathlib.Path(td)/"evidence.json"
            for data in [b'{',b'[]',b'{"x":1,"x":2}',b'{"x":NaN}',b'\xff']:
                path.write_bytes(data)
                self.rejected(lambda:v.load_evidence(path))
            path.write_text(json.dumps(v.owner_fixture()))
            self.assertEqual(v.load_evidence(path),v.owner_fixture())

    def test_input_size_is_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            path=pathlib.Path(td)/"evidence.json";path.write_bytes(b' '*65)
            with patch.object(v,"MAX_EVIDENCE_BYTES",64):self.rejected(lambda:v.load_evidence(path))

    def test_wrong_checkout_or_unavailable_git_rejects(self):
        with patch.object(v.subprocess,"run",return_value=subprocess.CompletedProcess([],0,"b"*40+"\n","")):
            self.rejected(lambda:v.verify_checkout_head(HEAD))
        with patch.object(v.subprocess,"run",side_effect=OSError()):
            self.rejected(lambda:v.verify_checkout_head(HEAD))
        responses=[subprocess.CompletedProcess([],0,HEAD+"\n",""),
                   subprocess.CompletedProcess([],0,pathlib.Path(v.__file__).read_text(),"")]
        with patch.object(v.subprocess,"run",side_effect=responses):
            self.assertEqual(v.verify_checkout_head(HEAD),HEAD)

    def test_modified_verifier_source_is_rejected(self):
        responses=[subprocess.CompletedProcess([],0,HEAD+"\n",""),
                   subprocess.CompletedProcess([],0,"different committed source","")]
        with patch.object(v.subprocess,"run",side_effect=responses):
            self.rejected(lambda:v.verify_checkout_head(HEAD))

    def test_contract_scope_is_explicit_and_artifacts_unchanged(self):
        c=v.contract(HEAD)
        self.assertEqual(c["success_status"],"FULL_EVIDENCE_CONTENT_VALIDATED")
        self.assertEqual(c["physical_device_status"],"NOT_VERIFIED")
        self.assertEqual(c["owner"]["signed_sha256"],"be15d47df7573fe4da7500cbd31f5caf21df380f0084c623d6e7a4a5e15f84b7")
        self.assertEqual(c["bridge"]["signed_sha256"],"8588f221bd91baf9b8a6183267dd9180ab019a94264b6dfb0d112279802d48f2")

if __name__=="__main__": unittest.main()
