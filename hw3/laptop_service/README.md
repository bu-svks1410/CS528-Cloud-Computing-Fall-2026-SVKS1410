# CS528 HW3 — Laptop Subscriber

Receives forbidden-country notifications from Pub/Sub and:

- Prints each error message
- Appends each notification to a log in Cloud Storage
- Checks message IDs to avoid duplicate records
- Acknowledges messages after saving them

## Files

- `subscriber.py` – main program
- `test_subscriber.py` – offline tests
- `requirements.txt` – required libraries

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
gcloud auth login
```

The signed-in user must have permission to impersonate the service account. The service account must have permission to receive subscription messages and read and update the bucket log.

## Run the tests

```bash
python3 -m unittest -v
```

Tests mock Google Cloud services and do not access live resources.

## Run the program

Replace the placeholders before running:

```bash
python3 subscriber.py \
  --project=PROJECT_ID \
  --bucket=BUCKET_NAME \
  --subscription=SUBSCRIPTION_ID \
  --service-account=SERVICE_ACCOUNT_EMAIL \
  --user-account=USER_EMAIL
```

The project resources and service account are given in the report. Use an authenticated user with permission to impersonate that service account.

| Option | Meaning |
| ------ | ------- |
| `--project ID` | Google Cloud project |
| `--bucket NAME` | Bucket containing the output log |
| `--subscription ID` | Pub/Sub subscription to receive messages from |
| `--service-account EMAIL` | Service account used by the cloud function |
| `--user-account EMAIL` | Signed-in Google Cloud user used for impersonation |

Keep the subscriber running while sending requests to the cloud function from another Terminal tab. Press Control+C to stop it.

## Output

Notifications are saved to `hw3-logs/forbidden-requests.jsonl` in the bucket. Each record includes the error message, request ID, country, timestamp, and Pub/Sub message ID.

## Authentication

The program obtains temporary service account credentials through gcloud and refreshes them automatically. No downloaded service account key or application-default login is used.
