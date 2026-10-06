import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import functions_framework
from google.api_core.exceptions import NotFound

os.environ.update(PROJECT_ID="test-project", BUCKET_NAME="test-bucket", TOPIC_ID="test-topic")
app = functions_framework.create_app(
    target="serve_file", source=str(Path(__file__).with_name("main.py")))
main = sys.modules["main"]


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.blob = Mock(content_type="text/html")
        self.blob.download_as_bytes.return_value = b"<h1>test file</h1>"
        self.storage = Mock()
        self.storage.bucket.return_value.blob.return_value = self.blob
        self.publisher = Mock()
        self.publisher.topic_path.return_value = "projects/test-project/topics/test-topic"
        self.addCleanup(patch.stopall)
        patch.object(main, "storage_client", return_value=self.storage).start()
        patch.object(main, "publisher_client", return_value=self.publisher).start()

    def test_get_paths_and_bytes(self):
        for path in ("/0.html", "/data/0.html", "/test-bucket/data/0.html"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, b"<h1>test file</h1>")
                self.storage.bucket.return_value.blob.assert_called_with("data/0.html")

    def test_post_formats(self):
        for kwargs in ({"json": {"file": "data/0.html"}},
                       {"data": {"file": "data/0.html"}},
                       {"data": "data/0.html", "content_type": "text/plain"}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.client.post("/", **kwargs).status_code, 200)

    def test_missing_file_and_both_log_formats(self):
        self.blob.download_as_bytes.side_effect = NotFound("missing")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            response = self.client.get("/data/missing.html")
        self.assertEqual(response.status_code, 404)
        lines = out.getvalue().splitlines()
        self.assertEqual(json.loads(lines[0])["event"], "file_not_found")
        self.assertTrue(lines[1].startswith("ERROR file_not_found"))

    def test_all_seven_unsupported_methods(self):
        for method in ("PUT", "DELETE", "HEAD", "CONNECT", "OPTIONS", "TRACE", "PATCH"):
            with self.subTest(method=method):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    response = self.client.open("/data/0.html", method=method)
                self.assertEqual(response.status_code, 501)
                self.assertEqual(json.loads(out.getvalue().splitlines()[0])["status"], 501)
        self.storage.bucket.assert_not_called()

    def test_forbidden_countries_publish_before_return(self):
        for country in sorted(main.FORBIDDEN_COUNTRIES) + ["IR", " North Korea ", "MM"]:
            with self.subTest(country=country), contextlib.redirect_stdout(io.StringIO()):
                response = self.client.get("/data/0.html", headers={"X-country": country})
                self.assertEqual(response.status_code, 400)
                event = json.loads(self.publisher.publish.call_args.args[1])
                self.assertEqual(event["country"], main.country_name(country))
                self.assertEqual(event["request_id"], response.headers["X-Request-ID"])
                self.publisher.publish.return_value.result.assert_called_with(timeout=30)
        self.storage.bucket.assert_not_called()

    def test_allowed_country_and_no_header(self):
        for headers in ({}, {"X-country": "United States"}):
            self.assertEqual(self.client.get("/data/0.html", headers=headers).status_code, 200)
        self.publisher.publish.assert_not_called()

    def test_log_directory_not_served(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.client.get("/hw3-logs/events.jsonl").status_code, 404)
        self.storage.bucket.assert_not_called()

    def test_bad_post_and_traversal(self):
        with contextlib.redirect_stdout(io.StringIO()):
            for payload in ({}, {"file": 4}, {"file": "data/../hw3-logs/events.jsonl"}):
                self.assertEqual(self.client.post("/", json=payload).status_code, 404)

    def test_backend_failures_not_mislabeled_as_missing(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.blob.download_as_bytes.side_effect = RuntimeError("storage unavailable")
            self.assertEqual(self.client.get("/data/0.html").status_code, 503)
            self.publisher.publish.return_value.result.side_effect = RuntimeError("unavailable")
            self.assertEqual(self.client.get("/data/0.html", headers={"X-country": "Iran"}).status_code, 503)


if __name__ == "__main__":
    unittest.main()
