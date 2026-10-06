import contextlib
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from google.api_core.exceptions import NotFound, PreconditionFailed

import subscriber as module


class SubscriberTests(unittest.TestCase):
    def setUp(self):
        self.event = {"event": "forbidden_request", "message": "Permission denied: Iran",
                      "country": "iran", "request_id": "request-1", "pubsub_message_id": "id-1"}
        self.bucket = Mock()
        self.blob = self.bucket.blob.return_value

    def test_create_new_log(self):
        self.blob.reload.side_effect = NotFound("missing")
        self.assertTrue(module.append_event(self.bucket, "hw3-logs/log.jsonl", self.event))
        call = self.blob.upload_from_string.call_args
        self.assertEqual(call.kwargs["if_generation_match"], 0)
        self.assertEqual(json.loads(call.args[0]), self.event)

    def test_append_preserves_previous_line(self):
        self.blob.generation = 17
        previous = json.dumps({"pubsub_message_id": "older", "message": "old error"}) + "\n"
        self.blob.download_as_text.return_value = previous
        module.append_event(self.bucket, "hw3-logs/log.jsonl", self.event)
        call = self.blob.upload_from_string.call_args
        self.assertTrue(call.args[0].startswith(previous))
        self.assertEqual(len(call.args[0].splitlines()), 2)
        self.assertEqual(call.kwargs["if_generation_match"], 17)

    def test_duplicate_not_appended(self):
        self.blob.generation = 18
        self.blob.download_as_text.return_value = json.dumps(self.event) + "\n"
        self.assertFalse(module.append_event(self.bucket, "hw3-logs/log.jsonl", self.event))
        self.blob.upload_from_string.assert_not_called()

    @patch.object(module.time, "sleep")
    def test_conflict_reloads_and_retries(self, sleep):
        self.blob.generation = 19
        self.blob.download_as_text.return_value = ""
        self.blob.upload_from_string.side_effect = [PreconditionFailed("changed"), None]
        self.assertTrue(module.append_event(self.bucket, "hw3-logs/log.jsonl", self.event))
        self.assertEqual(self.blob.reload.call_count, 2)

    @patch.object(module, "append_event")
    def test_ack_only_after_successful_write(self, append):
        client = Mock()
        received = SimpleNamespace(ack_id="ack-1", message=SimpleNamespace(
            data=json.dumps(self.event).encode(), message_id="id-1"))
        append.side_effect = RuntimeError("storage down")
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            module.process_message(client, "subscription", received, self.bucket, "hw3-logs/log.jsonl")
        client.acknowledge.assert_not_called()
        append.side_effect = None
        append.return_value = True
        with contextlib.redirect_stdout(io.StringIO()):
            module.process_message(client, "subscription", received, self.bucket, "hw3-logs/log.jsonl")
        client.acknowledge.assert_called_once()

    @patch.object(module.subprocess, "run")
    def test_keyless_auth_and_refresh(self, run):
        run.return_value = SimpleNamespace(returncode=0, stdout="test-token\n", stderr="")
        credentials = module.GcloudCredentials("sa@example.com", "project", "user@example.com")
        credentials.refresh(None)
        self.assertTrue(credentials.valid)
        self.assertEqual(credentials.token, "test-token")
        command = run.call_args.args[0]
        self.assertIn("--impersonate-service-account=sa@example.com", command)
        self.assertNotIn("application-default", command)
        headers = {}
        credentials.before_request(None, "GET", "https://example.com", headers)
        self.assertEqual(headers["authorization"], "Bearer test-token")
        self.assertEqual(run.call_count, 1)
        credentials.expiry = module.datetime(2000, 1, 1)
        credentials.before_request(None, "GET", "https://example.com", {})
        self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
