# CS528 HW3 — Laptop Subscriber

Receives forbidden-country notifications from Pub/Sub, prints each error message, and saves the notifications to Cloud Storage.

## Files

- `subscriber.py` – main program
- `test_subscriber.py` – offline tests
- `requirements.txt` – required libraries

## Processing

The subscriber processes one message at a time and acknowledges it after saving the record. Pub/Sub message IDs are checked to avoid duplicate entries on redelivery. Storage failures leave messages unacknowledged for retry.

## Configuration

The program accepts the following command-line options:

| Option | Meaning |
| ------ | ------- |
| `--project ID` | Google Cloud project |
| `--bucket NAME` | Bucket containing the output log |
| `--subscription ID` | Pub/Sub subscription receiving notifications |
| `--service-account EMAIL` | Service account used by the cloud function |
| `--user-account EMAIL` | Signed-in Google Cloud user used for impersonation |

Configuration and execution commands are included in the report.

## Output

Notifications are saved to `hw3-logs/forbidden-requests.jsonl`. Each record includes the error message, request ID, country, timestamp, and Pub/Sub message ID.

The program reads the existing log and uploads its contents with the new record appended. Generation checks prevent overwriting concurrent changes. This approach is suitable for small logs.

## Authentication

The subscriber uses the same service account as the cloud function. It obtains temporary credentials through gcloud and refreshes them automatically.

The signed-in user requires permission to impersonate the service account. The service account requires permission to receive subscription messages and read and update the bucket log.

Tokens remain in memory. No downloaded service account key or application-default login is used.

## Tests

The offline tests mock Google Cloud services and do not access live resources. Six subscriber tests passed during verification.
