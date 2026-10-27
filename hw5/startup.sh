#!/bin/bash
set -euo pipefail

if [ -f /var/log/startup_already_done ]; then
    echo "Startup installation already completed."
    exit 0
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv curl ca-certificates

if ! id hw5 >/dev/null 2>&1; then
    useradd --system --create-home --shell /usr/sbin/nologin hw5
fi

mkdir -p /opt/hw5
umask 077

python3 - <<'PY'
import base64
import json
import os
import re
import tarfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

metadata = "http://metadata.google.internal/computeMetadata/v1/"


def fetch(url, headers):
    for attempt in range(12):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except Exception:
            if attempt == 11:
                raise
            time.sleep(5)


def metadata_value(path):
    return fetch(metadata + path, {"Metadata-Flavor": "Google"})


config = json.loads(
    metadata_value("instance/attributes/hw5-config")
)
role = config["ROLE"]
if role not in {"server", "subscriber", "client"}:
    raise ValueError("Invalid VM role")

token = json.loads(
    metadata_value("instance/service-accounts/default/token")
)["access_token"]
headers = {"Authorization": "Bearer " + token}

bucket = urllib.parse.quote(config["BUNDLE_BUCKET"], safe="")
name = urllib.parse.quote(config["BUNDLE_OBJECT"], safe="")
url = (
    "https://storage.googleapis.com/storage/v1/b/"
    + bucket + "/o/" + name + "?alt=media"
)
archive = Path("/opt/hw5-bundle.tar.gz")
archive.write_bytes(fetch(url, headers))

with tarfile.open(archive, "r:gz") as bundle:
    bundle.extractall("/opt/hw5", filter="data")
archive.unlink()

if role == "server":
    project = urllib.parse.quote(config["PROJECT_ID"], safe="")
    secret = urllib.parse.quote(config["SQL_SECRET"], safe="")
    url = (
        "https://secretmanager.googleapis.com/v1/projects/"
        + project + "/secrets/" + secret + "/versions/latest:access"
    )
    result = json.loads(fetch(url, headers))
    config["PGPASSWORD"] = base64.b64decode(
        result["payload"]["data"]
    ).decode("utf-8")

lines = []
for key, value in config.items():
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
        raise ValueError("Invalid configuration key")
    value = str(value)
    if not re.fullmatch(r"[A-Za-z0-9_./:@-]+", value):
        raise ValueError("Invalid configuration value for " + key)
    lines.append(key + "=" + value)

path = Path("/etc/hw5.env")
path.write_text("\n".join(lines) + "\n")
os.chmod(path, 0o600)
print("Deployment files and environment are ready.")
PY

set -a
. /etc/hw5.env
set +a

if [ "$ROLE" != "client" ]; then
    python3 -m venv /opt/hw5/.venv
    /opt/hw5/.venv/bin/python -m pip install \
        -r /opt/hw5/requirements-lock.txt
fi

if [ "$ROLE" = "server" ]; then
    curl --fail --location --retry 5 \
        https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.26.3/cloud-sql-proxy.linux.amd64 \
        --output /usr/local/bin/cloud-sql-proxy
    chmod 755 /usr/local/bin/cloud-sql-proxy

    cat > /etc/systemd/system/hw5-sql-proxy.service <<'UNIT'
[Unit]
Description=HW5 Cloud SQL Auth Proxy
Wants=network-online.target
After=network-online.target

[Service]
User=hw5
EnvironmentFile=/etc/hw5.env
ExecStart=/usr/local/bin/cloud-sql-proxy --address=127.0.0.1 --port=5432 ${SQL_CONNECTION}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

    cat > /etc/systemd/system/hw5-server.service <<'UNIT'
[Unit]
Description=HW5 HTTP server
Wants=network-online.target hw5-sql-proxy.service
After=network-online.target hw5-sql-proxy.service

[Service]
User=hw5
WorkingDirectory=/opt/hw5/server
EnvironmentFile=/etc/hw5.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/hw5/.venv/bin/python /opt/hw5/server/main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
LogRateLimitIntervalSec=0

[Install]
WantedBy=multi-user.target
UNIT

elif [ "$ROLE" = "subscriber" ]; then
    cat > /etc/systemd/system/hw5-subscriber.service <<'UNIT'
[Unit]
Description=HW5 Pub/Sub subscriber
Wants=network-online.target
After=network-online.target

[Service]
User=hw5
WorkingDirectory=/opt/hw5/subscriber
EnvironmentFile=/etc/hw5.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/hw5/.venv/bin/python /opt/hw5/subscriber/subscriber.py --project=${PROJECT_ID} --bucket=${BUCKET_NAME} --subscription=${SUBSCRIPTION_ID} --log-object=${SUBSCRIBER_LOG_OBJECT}
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
LogRateLimitIntervalSec=0

[Install]
WantedBy=multi-user.target
UNIT

else
    chmod 755 /opt/hw5/client/http-client
fi

chown -R hw5:hw5 /opt/hw5
systemctl daemon-reload

if [ "$ROLE" = "server" ]; then
    systemctl enable --now hw5-sql-proxy.service hw5-server.service
elif [ "$ROLE" = "subscriber" ]; then
    systemctl enable --now hw5-subscriber.service
fi

touch /var/log/startup_already_done
echo "HW5 VM startup completed."
