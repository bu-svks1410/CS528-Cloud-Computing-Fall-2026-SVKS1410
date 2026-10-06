import argparse
import json
import subprocess
import time
from datetime import datetime, timedelta, timezone

from google.api_core.exceptions import DeadlineExceeded, NotFound, PreconditionFailed
from google.auth.credentials import Credentials
from google.cloud import pubsub_v1, storage


class GcloudCredentials(Credentials):
    def __init__(self, service_account, project, user_account):
        super().__init__()
        self.service_account = service_account
        self.project = project
        self.user_account = user_account

    def refresh(self, request):
        started = datetime.now(timezone.utc).replace(tzinfo=None)
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token",
             f"--impersonate-service-account={self.service_account}",
             f"--project={self.project}", f"--account={self.user_account}",
             "--lifetime=3600", "--quiet"],
            capture_output=True, text=True, timeout=60, check=False)
        if result.returncode != 0:
            raise RuntimeError("Service account impersonation failed: " + result.stderr.strip())
        token = result.stdout.strip()
        if not token or any(c.isspace() for c in token):
            raise RuntimeError("gcloud did not return a valid token format")
        self.token = token
        self.expiry = started + timedelta(minutes=45)


def append_event(bucket, object_name, event):
    line = json.dumps(event, ensure_ascii=True) + "\n"
    for attempt in range(5):
        blob = bucket.blob(object_name)
        try:
            try:
                blob.reload(timeout=20, retry=None)
            except NotFound:
                previous, generation = "", 0
            else:
                generation = int(blob.generation)
                previous = blob.download_as_text(
                    if_generation_match=generation, timeout=20, retry=None)
            for existing_line in previous.splitlines():
                if existing_line.strip():
                    existing = json.loads(existing_line)
                    if existing.get("pubsub_message_id") == event["pubsub_message_id"]:
                        return False
            if previous and not previous.endswith("\n"):
                previous += "\n"
            blob.upload_from_string(
                previous + line, content_type="application/x-ndjson",
                if_generation_match=generation, timeout=20, retry=None)
            return True
        except (PreconditionFailed, NotFound):
            if attempt == 4:
                raise
            time.sleep(0.2)


def process_message(subscriber, subscription, received, bucket, object_name):
    subscriber.modify_ack_deadline(
        request={"subscription": subscription, "ack_ids": [received.ack_id],
                 "ack_deadline_seconds": 600}, timeout=20, retry=None)
    event = json.loads(received.message.data.decode("utf-8"))
    if not isinstance(event, dict) or event.get("event") != "forbidden_request":
        raise ValueError("Expected a forbidden_request JSON object")
    for field in ("message", "country", "request_id"):
        if not isinstance(event.get(field), str):
            raise ValueError(f"Missing or invalid {field}")
    event["pubsub_message_id"] = received.message.message_id
    event["received_at"] = datetime.now(timezone.utc).isoformat()
    print(f"ERROR: {event['message']} | method={event.get('method')} "
          f"path={event.get('path')} request_id={event['request_id']}", flush=True)
    added = append_event(bucket, object_name, event)
    subscriber.acknowledge(
        request={"subscription": subscription, "ack_ids": [received.ack_id]},
        timeout=20, retry=None)
    state = "Saved" if added else "Already saved (duplicate delivery)"
    print(f"{state}: gs://{bucket.name}/{object_name}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--subscription", default="hw3-forbidden-requests-local")
    parser.add_argument("--service-account", required=True)
    parser.add_argument("--user-account", required=True)
    parser.add_argument("--log-object", default="hw3-logs/forbidden-requests.jsonl")
    args = parser.parse_args()
    if not args.log_object.startswith("hw3-logs/"):
        parser.error("--log-object must start with hw3-logs/")
    credentials = GcloudCredentials(args.service_account, args.project, args.user_account)
    credentials.refresh(None)
    storage_client = storage.Client(project=args.project, credentials=credentials)
    bucket = storage_client.bucket(args.bucket)
    subscriber = pubsub_v1.SubscriberClient(credentials=credentials)
    subscription = subscriber.subscription_path(args.project, args.subscription)
    print(f"Authenticated as: {args.service_account}", flush=True)
    print(f"Listening on: {subscription}", flush=True)
    print(f"Log file: gs://{args.bucket}/{args.log_object}", flush=True)
    print("Keep this Terminal running. Press Control+C to stop.", flush=True)
    try:
        while True:
            try:
                response = subscriber.pull(
                    request={"subscription": subscription, "max_messages": 1},
                    timeout=30, retry=None)
            except DeadlineExceeded:
                continue
            except Exception as exc:
                print(f"Receive failed: {exc}. Retrying in 5 seconds.", flush=True)
                time.sleep(5)
                continue
            if not response.received_messages:
                time.sleep(1)
            for received in response.received_messages:
                try:
                    process_message(subscriber, subscription, received, bucket, args.log_object)
                except Exception as exc:
                    print(f"Processing failed: {exc}. Message not acknowledged.", flush=True)
                    try:
                        subscriber.modify_ack_deadline(
                            request={"subscription": subscription,
                                     "ack_ids": [received.ack_id], "ack_deadline_seconds": 0},
                            timeout=20, retry=None)
                    except Exception:
                        pass
                    time.sleep(5)
    except KeyboardInterrupt:
        print("\nSubscriber stopped.", flush=True)
    finally:
        subscriber.close()
        storage_client.close()


if __name__ == "__main__":
    main()
