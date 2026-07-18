import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import main


class ApiSecurityTests(unittest.TestCase):
    def setUp(self):
        main.RATE_LIMIT_BUCKETS.clear()
        self.client = TestClient(main.app)

    def tearDown(self):
        main.RATE_LIMIT_BUCKETS.clear()

    def test_api_responses_include_browser_security_headers(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["referrer-policy"], "strict-origin-when-cross-origin")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])

    def test_https_proxy_requests_receive_hsts(self):
        response = self.client.get("/health", headers={"x-forwarded-proto": "https"})

        self.assertEqual(response.headers["strict-transport-security"], "max-age=31536000; includeSubDomains")

    def test_oversized_json_request_is_rejected_before_processing(self):
        response = self.client.post(
            "/agent/chat",
            headers={"content-length": str(main.MAX_JSON_REQUEST_BYTES + 1)},
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["detail"], "Request body is too large.")

    def test_chat_rate_limit_rejects_the_next_request(self):
        stub_result = {
            "route": {"kind": "general"},
            "content": "ok",
            "facts": None,
            "used_live_data": False,
        }
        with patch("main.generate_agent_reply", new=AsyncMock(return_value=stub_result)):
            for _ in range(30):
                self.assertEqual(self.client.post("/agent/chat", json={"message": "hello"}).status_code, 200)
            response = self.client.post("/agent/chat", json={"message": "hello"})

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "60")

    def test_chat_response_keeps_internal_agent_diagnostics_server_side(self):
        stub_result = {
            "route": {"kind": "company", "ticker": "AAPL"},
            "content": "## Investment view\n\nApple remains profitable.",
            "facts": {"revenue": "sensitive internal payload"},
            "used_live_data": True,
            "evidence": {"trace_id": "internal-trace"},
            "risk_review": {"warnings": ["internal warning"]},
        }

        with patch("main.generate_agent_reply", new=AsyncMock(return_value=stub_result)):
            response = self.client.post("/agent/chat", json={"message": "Analyze Apple"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["content"], stub_result["content"])
        self.assertEqual(payload["data"], {"used_live_data": True})
        self.assertNotIn("facts", payload["data"])
        self.assertNotIn("evidence", payload["data"])
        self.assertNotIn("risk_review", payload["data"])
        self.assertNotIn("route", payload["data"])

    def test_unconfigured_admin_endpoint_is_not_public(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": ""}):
            response = self.client.get("/agent/sessions/recent")

        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()

