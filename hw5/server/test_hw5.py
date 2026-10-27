import http.client
import os
import threading
import unittest
from datetime import datetime
from unittest.mock import patch

from google.api_core.exceptions import NotFound

import main


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.patches = []
        self.start_patch(
            patch.dict(os.environ, {
                "PROJECT_ID": "test-project",
                "BUCKET_NAME": "test-bucket",
                "TOPIC_ID": "test-topic",
                "RUN_ID": "local-test"
            })
        )
        self.saved = []

        def capture(record):
            self.saved.append(dict(record))

        self.save = self.start_patch(
            patch("main.save_request", side_effect=capture)
        )
        self.download = self.start_patch(
            patch.object(
                main.Handler,
                "download_file",
                return_value=(b"<html>Test</html>", "text/html")
            )
        )
        self.logger = self.start_patch(
            patch("http_core.cloud_logger")
        )
        self.publisher = self.start_patch(
            patch("http_core.publisher_client")
        )
        self.server = main.Server(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True
        )
        self.thread.start()

    def start_patch(self, patcher):
        result = patcher.start()
        self.patches.append(patcher)
        return result

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        for patcher in reversed(self.patches):
            patcher.stop()

    def request(self, method="GET", path="/data/0.html",
                headers=None, body=None):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=5
        )
        try:
            connection.request(
                method, path, body=body, headers=headers or {}
            )
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_success_and_header_extraction(self):
        status, body = self.request(headers={
            "X-country": "Georgia",
            "X-client-IP": "68.81.56.68",
            "X-gender": "Female",
            "X-age": "56-65",
            "X-income": "60k-100k",
            "X-time": "2026-10-26 19:00:00"
        })
        self.assertEqual(status, 200)
        self.assertEqual(body, b"<html>Test</html>")
        self.assertEqual(len(self.saved), 1)
        record = self.saved[0]
        self.assertEqual(record["country"], "georgia")
        self.assertEqual(record["client_ip"], "68.81.56.68")
        self.assertEqual(record["gender"], "Female")
        self.assertEqual(record["age_group"], "56-65")
        self.assertEqual(record["income_group"], "60k-100k")
        self.assertEqual(
            record["client_time"], datetime(2026, 10, 26, 19)
        )
        self.assertFalse(record["is_banned"])
        self.assertEqual(record["status_code"], 200)
        self.assertEqual(record["run_id"], "local-test")
        self.download.assert_called_once_with("data/0.html")

    def test_forbidden_country(self):
        status, _ = self.request(headers={"X-country": "Zimbabwe"})
        self.assertEqual(status, 400)
        self.assertTrue(self.saved[0]["is_banned"])
        self.assertEqual(self.saved[0]["status_code"], 400)
        self.download.assert_not_called()
        self.publisher.return_value.publish.assert_called_once()

    def test_missing_file(self):
        self.download.side_effect = NotFound("Missing file")
        status, _ = self.request(path="/data/missing.html")
        self.assertEqual(status, 404)
        self.assertEqual(self.saved[0]["status_code"], 404)
        self.assertEqual(
            self.saved[0]["requested_file"], "data/missing.html"
        )

    def test_post(self):
        status, body = self.request(
            method="POST",
            path="/",
            headers={"Content-Type": "application/json"},
            body='{"file":"data/0.html"}'
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, b"<html>Test</html>")
        self.assertEqual(
            self.saved[0]["requested_file"], "data/0.html"
        )

    def test_unsupported_methods(self):
        for method in (
            "PUT", "DELETE", "HEAD", "CONNECT",
            "OPTIONS", "TRACE", "PATCH"
        ):
            with self.subTest(method=method):
                status, body = self.request(method=method)
                self.assertEqual(status, 501)
                self.assertEqual(self.saved[-1]["status_code"], 501)
                if method == "HEAD":
                    self.assertEqual(body, b"")

    def test_missing_demographic_headers(self):
        status, _ = self.request()
        self.assertEqual(status, 200)
        for field in (
            "country", "client_ip", "gender",
            "age_group", "income_group", "client_time"
        ):
            self.assertIsNone(self.saved[0][field])

    def test_invalid_client_time(self):
        status, _ = self.request(headers={"X-time": "invalid"})
        self.assertEqual(status, 200)
        self.assertIsNone(self.saved[0]["client_time"])

    def test_database_failure(self):
        self.save.side_effect = RuntimeError("Database unavailable")
        status, body = self.request()
        self.assertEqual(status, 503)
        self.assertIn(b"Database unavailable", body)
        self.assertEqual(self.saved, [])


if __name__ == "__main__":
    unittest.main()
