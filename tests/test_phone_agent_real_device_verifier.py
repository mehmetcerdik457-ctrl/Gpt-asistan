import copy, json, pathlib, tempfile, unittest
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import verify_phone_agent_real_device as v

ROOT=pathlib.Path(__file__).resolve().parents[1]
EXPECTED=ROOT/"control-plane/runtime/phone_agent_real_device_expected.json"
VALID=ROOT/"tests/fixtures/phone_agent_real_device_valid.json"

class TestPhoneAgentRealDeviceVerifier(unittest.TestCase):
    def test_valid_fixture(self):
        result=v.validate(VALID,EXPECTED)
        self.assertEqual(result["status"],"PHONE_AGENT_REAL_DEVICE_EVIDENCE_VERIFIED")
        self.assertEqual(result["target_head"],"f3fc3977999640309df4574e97810fd1ea8f5240")

    def _expect_failure(self, data, status):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)/"evidence.json"
            p.write_text(json.dumps(data),encoding="utf-8")
            with self.assertRaises(SystemExit):
                v.validate(p,EXPECTED)

    def test_hash_mismatch_fails(self):
        data=json.loads(VALID.read_text())
        data["evidence"]["artifact_sha256"]="0"*64
        self._expect_failure(data,"REAL_DEVICE_IDENTITY_MISMATCH")

    def test_runtime_missing_scroll_fails(self):
        data=json.loads(VALID.read_text())
        data["phone_agent"]["scroll_forward_pass"]=False
        data["phone_agent"]["runtime_postcondition_result"]="PENDING"
        data["phone_agent"]["events"]=[e for e in data["phone_agent"]["events"] if e["action"]!="SCROLL_FORWARD"]
        self._expect_failure(data,"PHONE_AGENT_SCROLL_NOT_VERIFIED")

if __name__=="__main__":
    unittest.main()
