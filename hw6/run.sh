#!/bin/bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

source ./config.sh
source ./cloud_sql.sh
source ./setup_permissions.sh
source ./sql_connection.sh

mkdir -p .runtime results
chmod 700 .runtime

exec 9>.runtime/run.lock
if ! flock -n 9; then
    echo "Another HW6 controller is already running." >&2
    exit 1
fi

for command in gcloud python3 tar timeout; do
    command -v "$command" >/dev/null
done

for file in startup.sh run_vm.sh cloud_sql.sh setup_permissions.sh; do
    bash -n "$file"
done

.venv/bin/python -m py_compile \
    main.py data.py model_utils.py country_model.py \
    income_model.py vm_runner.py migrate.py

existing=$(gcloud compute instances list \
    --project="$PROJECT_ID" \
    --filter="name=${VM_NAME}" \
    --format='value(name)')

if [ -n "$existing" ]; then
    echo "A VM named $VM_NAME already exists. Inspect it before proceeding." >&2
    exit 1
fi

execution_id=$(python3 -c 'import uuid; print(uuid.uuid4().hex)')
execution_prefix="${OUTPUT_PREFIX}/executions/${execution_id}"
bundle_object="${OUTPUT_PREFIX}/deployment/${execution_id}.tar.gz"
local_results="results/${execution_id}"

mkdir -p "$local_results"
printf '%s\n' "$execution_id" > .runtime/latest-execution.txt

sql_managed=0
vm_managed=0

cleanup() {
    local original_status=$?
    local cleanup_status=0

    trap - EXIT INT TERM
    set +e

    if [ "$vm_managed" -eq 1 ]; then
        gcloud compute instances get-serial-port-output "$VM_NAME" \
            --project="$PROJECT_ID" \
            --zone="$ZONE" \
            > "$local_results/vm-serial.log" 2>&1

        remaining=$(gcloud compute instances list \
            --project="$PROJECT_ID" \
            --filter="name=${VM_NAME}" \
            --format='value(name)')

        if [ "$?" -ne 0 ]; then
            cleanup_status=1
        elif [ -n "$remaining" ]; then
            gcloud compute instances delete "$VM_NAME" \
                --project="$PROJECT_ID" \
                --zone="$ZONE" \
                --delete-disks=boot \
                --quiet || cleanup_status=1
        fi

        gcloud compute instances list \
            --project="$PROJECT_ID" \
            --filter="name=${VM_NAME}" \
            --format=json \
            > "$local_results/remaining-vms.json"

        if [ "$?" -ne 0 ]; then
            cleanup_status=1
        else
            python3 - "$local_results/remaining-vms.json" <<'PY'
import json
import sys

with open(sys.argv[1]) as source:
    instances = json.load(source)
if instances:
    raise SystemExit("VM cleanup verification failed.")
print("Verified: HW6 VM deleted.")
PY
            if [ "$?" -ne 0 ]; then
                cleanup_status=1
            fi
        fi
    fi

    if [ "$sql_managed" -eq 1 ]; then
        set_sql_policy NEVER || cleanup_status=1

        gcloud sql instances describe "$SQL_INSTANCE" \
            --project="$PROJECT_ID" \
            --format="json(name,state,settings.activationPolicy)" \
            > "$local_results/sql-final-state.json"

        if [ "$?" -ne 0 ]; then
            cleanup_status=1
        else
            cat "$local_results/sql-final-state.json"
        fi
    fi

    if [ "$cleanup_status" -ne 0 ]; then
        echo "Cleanup needs attention. Inspect the saved results." >&2
        exit 1
    fi

    exit "$original_status"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

setup_permissions

sql_managed=1
set_sql_policy ALWAYS

with_sql_connection admin .venv/bin/python migrate.py \
    2>&1 | tee "$local_results/migration.txt"

SQL_CONNECTION=$(gcloud sql instances describe "$SQL_INSTANCE" \
    --project="$PROJECT_ID" \
    --format='value(connectionName)')

export PROJECT_ID BUCKET_NAME SQL_CONNECTION SQL_DATABASE SQL_USER SQL_SECRET
export HW6_EXECUTION_PREFIX="$execution_prefix"

stage=$(mktemp -d .runtime/bundle.XXXXXX)

cp main.py data.py model_utils.py country_model.py income_model.py \
    vm_runner.py run_vm.sh requirements-lock.txt "$stage/"

python3 - "$stage/runtime-config.sh" <<'PY'
import os
import shlex
import sys
from pathlib import Path

keys = (
    "PROJECT_ID",
    "BUCKET_NAME",
    "SQL_CONNECTION",
    "SQL_DATABASE",
    "SQL_USER",
    "SQL_SECRET"
)

values = {key: os.environ[key] for key in keys}
values["OUTPUT_PREFIX"] = os.environ["HW6_EXECUTION_PREFIX"]

Path(sys.argv[1]).write_text(
    "".join(
        f"{key}={shlex.quote(value)}\n"
        for key, value in values.items()
    )
)
PY

tar -czf ".runtime/${execution_id}.tar.gz" -C "$stage" .

gcloud storage cp ".runtime/${execution_id}.tar.gz" \
    "gs://${BUCKET_NAME}/${bundle_object}" \
    --project="$PROJECT_ID"

vm_managed=1

gcloud compute instances create "$VM_NAME" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    --machine-type="$VM_MACHINE" \
    --image-project=ubuntu-os-cloud \
    --image-family=ubuntu-2404-lts-amd64 \
    --boot-disk-type=pd-standard \
    --boot-disk-size=20GB \
    --network=default \
    --tags=hw6-models \
    --service-account="${VM_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --scopes=cloud-platform \
    --metadata="hw6-bucket=${BUCKET_NAME},hw6-bundle=${bundle_object}" \
    --metadata-from-file=startup-script=startup.sh \
    --quiet

ready=0

for attempt in $(seq 1 90); do
    if timeout 30 gcloud compute ssh "$VM_NAME" \
        --project="$PROJECT_ID" \
        --zone="$ZONE" \
        --tunnel-through-iap \
        --quiet \
        --ssh-flag="-o ConnectTimeout=10" \
        --ssh-flag="-o BatchMode=yes" \
        --command="sudo -n test -f /opt/hw6/ready" \
        >> "$local_results/readiness.log" 2>&1; then
        ready=1
        break
    fi

    echo "Waiting for VM installation: check $attempt"
    sleep 10
done

if [ "$ready" -ne 1 ]; then
    echo "VM installation did not become ready." >&2
    exit 1
fi

echo "VM installation ready. Starting model execution."

timeout 7200 gcloud compute ssh "$VM_NAME" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    --tunnel-through-iap \
    --quiet \
    --ssh-flag="-o ServerAliveInterval=30" \
    --ssh-flag="-o ServerAliveCountMax=6" \
    --command="sudo -n -u hw6 bash /opt/hw6/run_vm.sh" \
    2>&1 | tee "$local_results/model-run.log"

gcloud storage ls \
    "gs://${BUCKET_NAME}/${execution_prefix}/runs/*/completed.json" \
    --project="$PROJECT_ID" \
    > "$local_results/completion-locations.txt"

completion_uri=$(python3 - "$local_results/completion-locations.txt" <<'PY'
import sys
from pathlib import Path

locations = [
    line.strip()
    for line in Path(sys.argv[1]).read_text().splitlines()
    if line.strip().startswith("gs://") and line.strip().endswith("/completed.json")
]

if len(locations) != 1:
    raise SystemExit("Expected exactly one completed model run.")

print(locations[0])
PY
)

bucket_run="${completion_uri%/completed.json}"

gcloud storage cp "${bucket_run}/*" "$local_results/" \
    --project="$PROJECT_ID"

for filename in metrics.json country_test_predictions.csv income_test_predictions.csv; do
    echo "Bucket output: ${bucket_run}/${filename}"
    gcloud storage cat "${bucket_run}/${filename}" \
        --project="$PROJECT_ID"
done

echo "HW6 model outputs retrieved successfully."
echo "Local results: $local_results"
echo "Bucket results: $bucket_run"
echo "Beginning VM deletion and database shutdown."
