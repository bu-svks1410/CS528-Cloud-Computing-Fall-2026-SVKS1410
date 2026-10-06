# CS528 Homework 3

## Programs

- cloud_function/main.py: HTTP cloud function, entry point serve_file.
- laptop_service/subscriber.py: Pub/Sub subscriber running on macOS.
- Each program directory contains its requirements and offline tests.

## Cloud resources

- Project: cultivated-link-508221-e6
- Region: us-central1
- Bucket: cultivated-link-508221-e6-cs528-hw2
- Input files: data/
- Output log: hw3-logs/forbidden-requests.jsonl
- Service account: hw3-service@cultivated-link-508221-e6.iam.gserviceaccount.com
- Topic: hw3-forbidden-requests
- Subscription: hw3-forbidden-requests-local

## Behavior

GET takes the filename from the URL path.
POST accepts a JSON payload such as {"file":"data/0.html"}.
Existing files return 200; missing files return 404.
Unsupported HTTP methods return 501 in the application.
Requests from the assignment's forbidden countries return 400 and publish a notification.
The laptop subscriber prints each notification and appends it to the bucket log.

Both programs use the same service account.
The laptop obtains short-lived impersonated credentials through gcloud.
No service account keys or application-default login are used.

## Verified client run

100 requests: 94 returned 200 and 6 returned 400 for forbidden countries.
All six forbidden notifications were verified in Cloud Logging and the bucket log.

## Platform limitation

Google Cloud Run blocks TRACE and CONNECT before they reach the function.
The public endpoint returned 405 for TRACE and 400 for CONNECT.
The application returns 501 for both methods in offline routing tests.

Reference: https://docs.cloud.google.com/run/docs/known-issues

See the submitted PDF report for setup commands, test evidence, screenshots,
authentication details, and limitations.
