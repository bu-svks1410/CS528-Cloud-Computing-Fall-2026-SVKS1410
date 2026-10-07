# CS528 HW3

Two services serve HTML files from Google Cloud Storage and process forbidden-country requests.

- The cloud function handles HTTP requests and returns file contents.
- Pub/Sub carries forbidden-country notifications to the laptop subscriber.
- The subscriber prints notifications and saves them to Cloud Storage.

## Files

- `cloud_function/main.py` – HTTP cloud function, entry point `serve_file`
- `cloud_function/test_main.py` – cloud function tests
- `cloud_function/requirements.txt` – cloud function dependencies
- `laptop_service/subscriber.py` – Pub/Sub subscriber running on macOS
- `laptop_service/test_subscriber.py` – subscriber tests
- `laptop_service/requirements.txt` – subscriber dependencies
- `laptop_service/README.md` – subscriber documentation

## Behavior

GET requests specify the filename in the URL path. POST requests provide the filename in a JSON payload such as `{"file":"data/0.html"}`.

| Request | Response |
| ------- | -------- |
| Existing file | 200 with the file contents |
| Missing file | 404 with an error log |
| Unsupported HTTP method reaching the application | 501 with an error log |
| Forbidden-country request | 400 with a Pub/Sub notification |

The cloud function records errors using structured logs and plain print statements.

## Laptop subscriber

The subscriber receives forbidden-country notifications, prints each error message, and appends a JSON record to `hw3-logs/forbidden-requests.jsonl`.

Messages are acknowledged after successful storage. Pub/Sub message IDs prevent duplicate records on redelivery. Generation checks prevent overwriting concurrent changes to the log.

## Authentication

Both services use the same service account. The laptop subscriber obtains temporary impersonated credentials through gcloud and refreshes them automatically. No downloaded service account keys or application-default login are used.

## Tests and results

Each program includes offline tests that mock Google Cloud services.

The provided HTTP client made 100 requests:

- 94 returned 200
- 6 returned 400 for forbidden countries

All six forbidden-country notifications were verified in Cloud Logging and the bucket log.

## Platform limitation

Google Cloud Run blocks TRACE and CONNECT before they reach the function. The public endpoint returned 405 for TRACE and 400 for CONNECT. Both methods returned 501 in offline application tests.

Reference: https://docs.cloud.google.com/run/docs/known-issues

## Report

The PDF report contains configuration and deployment steps, execution commands, screenshots, test evidence, and authentication details.
