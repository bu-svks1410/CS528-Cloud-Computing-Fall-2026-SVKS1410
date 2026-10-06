# CS528 HW3 — laptop subscriber

Run this program on your Mac, with your existing gcloud user login. It explicitly
requests temporary credentials for the same service account attached to the cloud
function. No service account key or application-default login is used.

## Setup

From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest -v
python subscriber.py \
  --project=cultivated-link-508221-e6 \
  --bucket=cultivated-link-508221-e6-cs528-hw2 \
  --subscription=hw3-forbidden-requests-local \
  --service-account=hw3-service@cultivated-link-508221-e6.iam.gserviceaccount.com \
  --user-account=svks1410@bu.edu
```

Leave this Terminal open and use a second Terminal to send HTTP requests.
Control+C stops the subscriber. To restart it, activate `.venv` and run the same
subscriber command. Tests mock Google Cloud and do not access your project.

## Authentication explanation for the report

The administrator signs in to the Google Cloud CLI with `gcloud auth login`.
The administrator has Service Account Token Creator on hw3-service. The Python
program invokes `gcloud auth print-access-token --impersonate-service-account=...`
using that user's CLI login. Google issues a temporary token for hw3-service.
The program passes an explicit credential object to both cloud clients and refreshes
it via the same command when needed, conservatively treating tokens as expired
after 45 minutes. Tokens remain in memory and are not printed or saved to files.
No default-credential discovery is used. The source user's CLI login must remain
valid and retain permission to impersonate the account.

This approach avoids a long-lived downloaded private key while ensuring that
Pub/Sub and Storage requests use the homework service account's permissions.
The user's administrative credentials are used only by gcloud to obtain the
impersonated token, not as the credentials passed to the application clients.

## Processing and storage

The program pulls one message at a time, prints the error message, appends a JSON
line to `hw3-logs/forbidden-requests.jsonl`, then acknowledges the message.
Each line includes the original error message, request ID, country, time, and
Pub/Sub message ID. Duplicate deliveries do not add duplicate lines for the same
Pub/Sub message ID. Storage failures leave the message unacknowledged for retry.

The log is one object in a separate bucket prefix. Appending is implemented by
reading the existing content and replacing it with that content plus one line.
Generation preconditions prevent overwriting changes from another writer. This
small-homework approach reads the whole log for each message and is not intended
for large production logs. Run only one subscriber for this exercise.

The existing Homework 2 bucket has public read access, including for this log.
The log contains request metadata, not credentials. The cloud function's country
filter is a classroom simulation, not a barrier to direct access to the public bucket.

## Sources

- https://docs.cloud.google.com/sdk/gcloud/reference/auth/print-access-token
- https://docs.cloud.google.com/pubsub/docs/pull
- https://docs.cloud.google.com/storage/docs/request-preconditions
