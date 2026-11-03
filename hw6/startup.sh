#!/bin/bash
set -euo pipefail

exec > >(tee -a /var/log/hw6-startup.log) 2>&1

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y python3 python3-venv curl ca-certificates

if ! id hw6 >/dev/null 2>&1; then
    useradd --system --create-home --shell /usr/sbin/nologin hw6
fi

mkdir -p /opt/hw6
cd /opt/hw6

python3 - <<'PY'
import json
import tarfile
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

metadata_root = "http://metadata.google.internal/computeMetadata/v1/"


def fetch(url, headers):
    for attempt in range(12):
        try:
            request = Request(url, headers=headers)
            with urlopen(request, timeout=60) as response:
                return response.read()
        except Exception:
            if attempt == 11:
                raise
            time.sleep(5)


def metadata(path):
    return fetch(
        metadata_root + path,
        {"Metadata-Flavor": "Google"}
    )


bucket = metadata("instance/attributes/hw6-bucket").decode().strip()
object_name = metadata("instance/attributes/hw6-bundle").decode().strip()

token = json.loads(
    metadata("instance/service-accounts/default/token")
)["access_token"]

url = (
    "https://storage.googleapis.com/storage/v1/b/"
    + quote(bucket, safe="")
    + "/o/"
    + quote(object_name, safe="")
    + "?alt=media"
)

archive = Path("/opt/hw6-bundle.tar.gz")
archive.write_bytes(
    fetch(url, {"Authorization": "Bearer " + token})
)

with tarfile.open(archive, "r:gz") as bundle:
    bundle.extractall("/opt/hw6", filter="data")

archive.unlink()
print("HW6 code bundle downloaded.", flush=True)
PY

python3 -m venv /opt/hw6/.venv

/opt/hw6/.venv/bin/python -m pip install \
    -r /opt/hw6/requirements-lock.txt

curl --fail --location --retry 5 \
    https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.26.3/cloud-sql-proxy.linux.amd64 \
    --output /usr/local/bin/cloud-sql-proxy

chmod 755 /usr/local/bin/cloud-sql-proxy

/opt/hw6/.venv/bin/python -c \
    'import main, vm_runner; print("VM Python imports passed.")'

mkdir -p /opt/hw6/results
chown -R hw6:hw6 /opt/hw6

touch /opt/hw6/ready

echo "HW6 VM installation completed."
