# CS528 HW4

A Python HTTP server running on Google Compute Engine serves HTML files from Cloud Storage. A second service receives forbidden-country notifications through Pub/Sub and saves them to a bucket log.

The server uses Python HTTPServer on port 8080. Both services start automatically when their VMs are created.

## Request handling

- GET and POST return the requested file with status 200.
- Missing files return 404 and create a WARNING log.
- Unsupported methods return 501 and create an ERROR log.
- Forbidden-country requests return 400, create a CRITICAL log, and send a Pub/Sub notification.

## Main files

- server/: HTTP server and tests.
- subscriber/: Pub/Sub subscriber and tests.
- deploy.py: Creates and deletes HW4 resources.
- setup_cloud.py: Sets up service accounts, permissions, and Pub/Sub.
- prepare_startup.py: Generates VM startup scripts.
- requirements-lock.txt: Required Python packages.
- client/: Provided Linux HTTP client.
- monitor.py and stress_client.py: Performance testing.
- summarize_results.py and plot_results.py: Results summary and graphs.
- results/httpserver/: Test results.
- screenshots/: Browser and billing screenshots.

## Setup

Run the deployment commands from this folder in Google Cloud Shell.

The project needs billing enabled, the default VPC network, and an existing bucket in the same project containing the HTML files under data/. The signed-in account needs permission to create resources and configure service accounts and IAM.

Replace YOUR_PROJECT_ID and YOUR_BUCKET_NAME below.

## Create the VMs

```bash
python3 deploy.py create \
  --project=YOUR_PROJECT_ID \
  --bucket=YOUR_BUCKET_NAME \
  --zone=us-central1-a
```

This creates the server, subscriber, and client VMs and their required resources. The server and subscriber install their dependencies and start automatically.

The server uses f1-micro with Debian 12. The subscriber uses e2-micro with Debian 12. The client uses e2-small with Ubuntu 24.04.

The command prints the server URL. Allow time for startup installation to finish before testing.

## Test the server

Replace SERVER_IP with the address printed during deployment.

```bash
curl -i http://SERVER_IP:8080/data/0.html
```

```bash
curl -i \
  -H "Content-Type: application/json" \
  --data '{"file":"data/0.html"}' \
  http://SERVER_IP:8080/
```

```bash
curl -i \
  -H "X-country: Iran" \
  http://SERVER_IP:8080/data/0.html
```

## Run the provided client

Copy the Linux client to the client VM:

```bash
gcloud compute scp client/http-client hw4-client:~/http-client \
  --project=YOUR_PROJECT_ID \
  --zone=us-central1-a \
  --tunnel-through-iap
```

Run 100 requests:

```bash
gcloud compute ssh hw4-client \
  --project=YOUR_PROJECT_ID \
  --zone=us-central1-a \
  --tunnel-through-iap \
  --command="chmod +x ~/http-client && ~/http-client -d SERVER_IP -b none -w data -n 100 -i 11999 -p 8080 -r 528 -t 30"
```

The index assumes files numbered 0 through 11999.

## Unit tests

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
(cd server && ../.venv/bin/python -m unittest -v)
(cd subscriber && ../.venv/bin/python -m unittest -v)
```

These tests mock Google Cloud services.

## Performance testing

Tests used one to four concurrent clients for 180 seconds each, with a 30-second timeout and without the verbose flag. Measurements and graphs are saved in results/httpserver/stress/. The report explains the results.

## Delete the VMs

```bash
python3 deploy.py delete \
  --project=YOUR_PROJECT_ID \
  --zone=us-central1-a
```

This deletes the HW4 VMs, boot disks, reserved IP, firewall rules, and Pub/Sub topic and subscription.

The existing bucket, saved logs, service accounts, IAM roles, and local files are retained. Automatic deletion and recreation were tested, and the VMs were deleted after testing.
