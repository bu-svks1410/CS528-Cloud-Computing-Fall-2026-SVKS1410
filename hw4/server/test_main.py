import contextlib
import http.client
import io
import json
import threading
import unittest
from unittest.mock import Mock, patch

from google.api_core.exceptions import NotFound

import main


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)

        self.stack.enter_context(patch.dict("os.environ", {
            "PROJECT_ID": "test-project",
            "BUCKET_NAME": "test-bucket",
            "TOPIC_ID": "test-topic"
        }))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

        self.storage = Mock()
        self.blob = self.storage.bucket.return_value.blob.return_value
        self.blob.download_as_bytes.return_value = b"<html>test</html>"
        self.blob.content_type = "text/html"

        self.publisher = Mock()
        self.publisher.topic_path.return_value = "test-topic-path"
        self.logger = Mock()

        self.stack.enter_context(
            patch.object(main, "storage_client", return_value=self.storage)
        )
        self.stack.enter_context(
            patch.object(main, "publisher_client", return_value=self.publisher)
        )
        self.stack.enter_context(
            patch.object(main, "cloud_logger", return_value=self.logger)
        )

        self.server = main.Server(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True
        )
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=5
        )
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_get_file(self):
        status, headers, body = self.request("GET", "/data/0.html")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"<html>test</html>")
        self.assertEqual(headers["Content-Length"], str(len(body)))
        self.assertEqual(headers["Connection"], "close")
        self.storage.bucket.assert_called_with("test-bucket")
        self.storage.bucket.return_value.blob.assert_called_with("data/0.html")

    def test_post_payload_formats(self):
        cases = [
            ("application/json", '{"file":"data/0.html"}'),
            ("application/x-www-form-urlencoded", "file=data%2F0.html"),
            ("text/plain", "data/0.html")
        ]
        for content_type, payload in cases:
            with self.subTest(content_type=content_type):
                status, _, body = self.request(
                    "POST", "/", payload, {"Content-Type": content_type}
                )
                self.assertEqual(status, 200)
                self.assertEqual(body, b"<html>test</html>")

    def test_missing_file_warning(self):
        self.blob.download_as_bytes.side_effect = NotFound("missing")
        status, headers, _ = self.request("GET", "/data/missing.html")
        self.assertEqual(status, 404)
        call = self.logger.log_struct.call_args
        self.assertEqual(call.kwargs["severity"], "WARNING")
        self.assertEqual(call.args[0]["event"], "file_not_found")
        self.assertEqual(
            call.args[0]["request_id"], headers["X-Request-ID"]
        )

    def test_all_unsupported_methods(self):
        for method in ("PUT", "DELETE", "HEAD", "CONNECT", "OPTIONS", "TRACE", "PATCH"):
            with self.subTest(method=method):
                status, _, body = self.request(method, "/data/0.html")
                self.assertEqual(status, 501)
                self.assertEqual(
                    self.logger.log_struct.call_args.kwargs["severity"],
                    "ERROR"
                )
                if method == "HEAD":
                    self.assertEqual(body, b"")

    def test_all_forbidden_countries(self):
        for country in sorted(main.FORBIDDEN_COUNTRIES):
            with self.subTest(country=country):
                self.publisher.reset_mock()
                status, headers, _ = self.request(
                    "GET", "/data/0.html", headers={"X-country": country}
                )
                self.assertEqual(status, 400)
                call = self.logger.log_struct.call_args
                self.assertEqual(call.kwargs["severity"], "CRITICAL")
                event = json.loads(
                    self.publisher.publish.call_args.args[1].decode()
                )
                self.assertEqual(event["country"], country)
                self.assertEqual(event["request_id"], headers["X-Request-ID"])
                self.publisher.publish.return_value.result.assert_called_once_with(
                    timeout=30
                )
        self.blob.download_as_bytes.assert_not_called()

    def test_allowed_country(self):
        status, _, _ = self.request(
            "GET", "/data/0.html", headers={"X-country": "Canada"}
        )
        self.assertEqual(status, 200)
        self.publisher.publish.assert_not_called()

    def test_path_restrictions(self):
        for path in (
            "/hw4-logs/forbidden-requests.jsonl",
            "/data/../secret",
            "/data/%2e%2e/secret"
        ):
            with self.subTest(path=path):
                status, _, _ = self.request("GET", path)
                self.assertEqual(status, 404)
        self.blob.download_as_bytes.assert_not_called()

    def test_storage_failure(self):
        self.blob.download_as_bytes.side_effect = RuntimeError("unavailable")
        status, _, _ = self.request("GET", "/data/0.html")
        self.assertEqual(status, 503)
        self.assertEqual(
            self.logger.log_struct.call_args.args[0]["event"],
            "storage_failed"
        )

    def test_publish_failure(self):
        self.publisher.publish.return_value.result.side_effect = RuntimeError(
            "unavailable"
        )
        status, _, _ = self.request(
            "GET", "/data/0.html", headers={"X-country": "Iran"}
        )
        self.assertEqual(status, 503)
        self.assertEqual(
            self.logger.log_struct.call_args.args[0]["event"],
            "publish_failed"
        )

    def test_invalid_json(self):
        status, _, _ = self.request(
            "POST", "/", "{", {"Content-Type": "application/json"}
        )
        self.assertEqual(status, 400)
        self.blob.download_as_bytes.assert_not_called()


if __name__ == "__main__":
    unittest.main()
