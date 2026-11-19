"""Synthetic runner output tests, never represented as real device results."""
import copy
import unittest

from server.tests.test_android_delivery_evidence import module


class InstrumentationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.verifier = module("android_instrumentation_evidence")
        self.source = "a" * 40
        self.apk = "b" * 64
        self.summary = {"source_commit": self.source, "apk_sha256": self.apk,
                        "unit_tests": {"skipped": 1},
                        "skipped_tests": [{"classname": "Store", "name": "case0"}]}
        self.blocks = [f"INSTRUMENTATION_STATUS: class=Store\nINSTRUMENTATION_STATUS: test=case{i}\n"
                       f"INSTRUMENTATION_STATUS_CODE: 1\n"
                       f"INSTRUMENTATION_STATUS: class=Store\nINSTRUMENTATION_STATUS: test=case{i}\n"
                       f"INSTRUMENTATION_STATUS_CODE: 0\n" for i in range(16)]
        self.blocks.extend(
            f"INSTRUMENTATION_STATUS: class={classname}\nINSTRUMENTATION_STATUS: test={name}\n"
            "INSTRUMENTATION_STATUS_CODE: 1\n"
            f"INSTRUMENTATION_STATUS: class={classname}\nINSTRUMENTATION_STATUS: test={name}\n"
            "INSTRUMENTATION_STATUS_CODE: 0\n"
            for classname, name in sorted(self.verifier.REMINDER_TESTS)
        )
        self.suffix = ("".join(f"INSTRUMENTATION_RESULT: kral_reminder_{flag}=true\n"
                               for flag in self.verifier.REMINDER_FLAGS)
                       + f"OK ({len(self.blocks)} tests)\nINSTRUMENTATION_CODE: -1\n")

    def test_individual_passes_cover_the_skipped_jvm_test(self):
        result = self.verifier.verify("".join(self.blocks) + self.suffix,
                                      self.summary, self.source, self.apk)
        self.assertEqual(result["instrumentation_tests"], 21)
        self.assertEqual(result["jvm_skips_covered_on_android"], self.summary["skipped_tests"])
        self.assertTrue(result["local_task_reminder_background_verified"])

    def test_success_summary_alone_is_not_a_test_result(self):
        with self.assertRaisesRegex(ValueError, "TEST_COUNT_MISMATCH"):
            self.verifier.verify(self.suffix, self.summary, self.source, self.apk)

    def test_an_android_skip_cannot_cover_a_jvm_skip(self):
        data = "".join(self.blocks).replace("INSTRUMENTATION_STATUS_CODE: 0", "INSTRUMENTATION_STATUS_CODE: -3", 1)
        with self.assertRaisesRegex(ValueError, "TEST_NOT_PASSED"):
            self.verifier.verify(data + self.suffix, self.summary, self.source, self.apk)

    def test_missing_required_test_cannot_be_hidden_by_total_count(self):
        summary = copy.deepcopy(self.summary)
        summary["skipped_tests"][0]["name"] = "missingCase"
        with self.assertRaisesRegex(ValueError, "NOT_COVERED_ON_ANDROID"):
            self.verifier.verify("".join(self.blocks) + self.suffix, summary, self.source, self.apk)

    def test_another_build_cannot_supply_coverage(self):
        with self.assertRaisesRegex(ValueError, "BUILD_IDENTITY_MISMATCH"):
            self.verifier.verify("".join(self.blocks) + self.suffix, self.summary, "c" * 40, self.apk)

    def test_duplicate_runner_events_are_rejected(self):
        data = self.blocks[0] + "".join(self.blocks) + self.suffix
        with self.assertRaisesRegex(ValueError, "DUPLICATE_TEST"):
            self.verifier.verify(data, self.summary, self.source, self.apk)

    def test_background_test_cannot_be_replaced_by_another_passing_case(self):
        data = ("".join(self.blocks) + self.suffix).replace(
            "scheduledJobPostsPrivateNotificationAndOpensLockedActivity", "unrelatedSyntheticCase")
        with self.assertRaisesRegex(ValueError, "BACKGROUND_REMINDER_TEST_NOT_COVERED"):
            self.verifier.verify(data, self.summary, self.source, self.apk)

    def test_test_pass_without_actual_os_observation_is_rejected(self):
        data = "".join(self.blocks) + self.suffix.replace(
            "INSTRUMENTATION_RESULT: kral_reminder_actual_notification=true\n", "")
        with self.assertRaisesRegex(ValueError, "BACKGROUND_REMINDER_OS_EVIDENCE_MISSING"):
            self.verifier.verify(data, self.summary, self.source, self.apk)

    def test_duplicate_or_false_background_marker_is_rejected(self):
        for marker in ("false", "true\nINSTRUMENTATION_RESULT: kral_reminder_real_job_dispatch=true"):
            with self.subTest(marker=marker):
                data = "".join(self.blocks) + self.suffix.replace(
                    "kral_reminder_real_job_dispatch=true", f"kral_reminder_real_job_dispatch={marker}")
                with self.assertRaisesRegex(ValueError, "BACKGROUND_REMINDER_OS_EVIDENCE_MISSING"):
                    self.verifier.verify(data, self.summary, self.source, self.apk)
