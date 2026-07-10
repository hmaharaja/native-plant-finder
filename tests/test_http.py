from __future__ import annotations

import unittest

from scraper.http import HttpClient


class HttpTests(unittest.TestCase):
    def test_retry(self):
        client = HttpClient(delay=0, retries=3, backoff=2)
        policy = client.session.get_adapter("https://").max_retries
        self.assertEqual(policy.total, 2)
        self.assertEqual(policy.backoff_factor, 2)
        self.assertIn("POST", policy.allowed_methods)
        self.assertIn(429, policy.status_forcelist)

    def test_attempt_count_includes_retry_history(self):
        class FakeResponse:
            raw = type("Raw", (), {"retries": type("Retries", (), {"history": (object(), object())})()})()

            def raise_for_status(self):
                return None

        class FakeSession:
            headers: dict[str, str] = {}

            def mount(self, prefix, adapter):
                return None

            def request(self, method, url, timeout, **kwargs):
                return FakeResponse()

        client = HttpClient(delay=0, session=FakeSession())
        client.get("https://example.test")
        self.assertEqual(client.attempts, 3)
        client.reset_attempts()
        self.assertEqual(client.attempts, 0)


if __name__ == "__main__":
    unittest.main()
