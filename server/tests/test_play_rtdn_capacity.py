"""Bounded RTDN HTTP admission and capacity recovery with a real local server."""
import unittest
from unittest.mock import Mock

from server.play_rtdn import RtdnDenied, RtdnRetry
from server.tests import test_play_rtdn as fixture


class RtdnCapacityTests(unittest.TestCase):
    def setUp(self):
        self.http = fixture.RtdnHttpTests(methodName="test_authenticated_test_push_audit_http_200_no_grant")
        self.http.setUp()
        self.addCleanup(self.http.tearDown)
        self.gateway = self.http.owner_fixture.gateway

    def test_full_capacity_returns_retryable_503_without_processing_then_recovers(self):
        processor = Mock()
        processor.process.return_value = True
        self.gateway.rtdn_processor = processor
        permits = self.gateway.rtdn_inflight
        for _ in range(4):
            self.assertTrue(permits.acquire(blocking=False))
        try:
            status, data = self.http.post()
            self.assertEqual((status, data["error"]), (503, "RTDN_BUSY"))
            processor.process.assert_not_called()
        finally:
            for _ in range(4):
                permits.release()
        self.assertEqual(self.http.post()[0], 200)
        processor.process.assert_called_once()

    def test_provider_failure_releases_capacity_for_next_delivery(self):
        processor = Mock()
        processor.process.side_effect = [RtdnRetry("unavailable")] * 5 + [True]
        self.gateway.rtdn_processor = processor
        for _ in range(5):
            status, data = self.http.post()
            self.assertEqual((status, data["error"]), (503, "RTDN_RETRY_REQUIRED"))
        self.assertEqual(self.http.post()[0], 200)
        self.assertEqual(processor.process.call_count, 6)

    def test_authentication_failure_releases_capacity_for_next_delivery(self):
        processor = Mock()
        processor.process.side_effect = [RtdnDenied("RTDN_AUTH_DENIED")] * 5 + [True]
        self.gateway.rtdn_processor = processor
        for _ in range(5):
            status, data = self.http.post()
            self.assertEqual((status, data["error"]), (403, "RTDN_AUTH_DENIED"))
        self.assertEqual(self.http.post()[0], 200)
        self.assertEqual(processor.process.call_count, 6)
