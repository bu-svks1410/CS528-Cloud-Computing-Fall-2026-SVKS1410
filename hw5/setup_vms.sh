#!/bin/bash

write_vm_config() {
    local role="$1"
    local name="$2"

    python3 - "$role" ".runtime/${name}.json" <<'PY'
import json
import os
import sys
from pathlib import Path

role, filename = sys.argv[1:]
keys = [
    "PROJECT_ID", "BUCKET_NAME", "BUNDLE_BUCKET", "BUNDLE_OBJECT"
]
config = {key: os.environ[key] for key in keys}
config["ROLE"] = role

if role == "server":
    config.update({
        "TOPIC_ID": os.environ["TOPIC_ID"],
        "SQL_CONNECTION": os.environ["SQL_CONNECTION"],
        "SQL_SECRET": os.environ["SQL_SECRET"],
        "PGHOST": "127.0.0.1",
        "PGPORT": "5432",
        "PGDATABASE": os.environ["SQL_DATABASE"],
        "PGUSER": os.environ["SQL_USER"],
        "PGSSLMODE": "disable",
        "PORT": os.environ["PORT"],
        "RUN_ID": "demonstration"
    })
elif role == "subscriber":
    config.update({
        "SUBSCRIPTION_ID": os.environ["SUBSCRIPTION_ID"],
        "SUBSCRIBER_LOG_OBJECT": os.environ["SUBSCRIBER_LOG_OBJECT"]
    })

Path(filename).write_text(json.dumps(config, indent=2) + "\n")
print(f"Prepared {role} VM configuration.")
PY
}

create_hw5_vm() {
    local name="$1"
    local role="$2"
    local machine="$3"
    local account="$4"
    local status
    local tags="hw5-vm"
    local extra_args=()

    write_vm_config "$role" "$name"

    if gcloud compute instances describe "$name" \
        --project="$PROJECT_ID" \
        --zone="$ZONE" >/dev/null 2>&1; then

        status=$(gcloud compute instances describe "$name" \
            --project="$PROJECT_ID" \
            --zone="$ZONE" \
            --format="value(status)")

        if [ "$status" = "TERMINATED" ]; then
            gcloud compute instances start "$name" \
                --project="$PROJECT_ID" \
                --zone="$ZONE" \
                --quiet
        elif [ "$status" != "RUNNING" ]; then
            echo "$name is in state $status. Wait before retrying setup." >&2
            return 1
        fi

        echo "Reusing $name with its existing installed files."
        return 0
    fi

    if [ "$role" = "server" ]; then
        tags="hw5-vm,hw5-http"
        extra_args+=(--address="$SERVER_IP")
    fi

    gcloud compute instances create "$name" \
        --project="$PROJECT_ID" \
        --zone="$ZONE" \
        --machine-type="$machine" \
        --image-project=ubuntu-os-cloud \
        --image-family=ubuntu-2404-lts-amd64 \
        --boot-disk-type=pd-standard \
        --boot-disk-size=10GB \
        --network=default \
        --tags="$tags" \
        --service-account="${account}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --scopes=cloud-platform \
        --metadata-from-file="startup-script=startup.sh,hw5-config=.runtime/${name}.json" \
        "${extra_args[@]}" \
        --quiet
}

setup_vms() {
    mkdir -p .runtime
    chmod 700 .runtime

    export PROJECT_ID BUCKET_NAME BUNDLE_BUCKET BUNDLE_OBJECT
    export TOPIC_ID SQL_CONNECTION SQL_SECRET SQL_DATABASE SQL_USER
    export PORT SUBSCRIPTION_ID SUBSCRIBER_LOG_OBJECT

    gcloud compute networks describe default \
        --project="$PROJECT_ID" >/dev/null

    tar \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        -czf .runtime/hw5.tar.gz \
        server subscriber client requirements-lock.txt

    gcloud storage cp .runtime/hw5.tar.gz \
        "gs://${BUNDLE_BUCKET}/${BUNDLE_OBJECT}" \
        --project="$PROJECT_ID"

    if ! gcloud compute addresses describe "$SERVER_IP_NAME" \
        --project="$PROJECT_ID" \
        --region="$REGION" >/dev/null 2>&1; then
        gcloud compute addresses create "$SERVER_IP_NAME" \
            --project="$PROJECT_ID" \
            --region="$REGION" \
            --quiet
    fi

    SERVER_IP=$(gcloud compute addresses describe "$SERVER_IP_NAME" \
        --project="$PROJECT_ID" \
        --region="$REGION" \
        --format="value(address)")
    export SERVER_IP

    if ! gcloud compute firewall-rules describe "$HTTP_FIREWALL" \
        --project="$PROJECT_ID" >/dev/null 2>&1; then
        gcloud compute firewall-rules create "$HTTP_FIREWALL" \
            --project="$PROJECT_ID" \
            --network=default \
            --allow="tcp:${PORT}" \
            --source-ranges=0.0.0.0/0 \
            --target-tags=hw5-http \
            --quiet
    fi

    if ! gcloud compute firewall-rules describe "$SSH_FIREWALL" \
        --project="$PROJECT_ID" >/dev/null 2>&1; then
        gcloud compute firewall-rules create "$SSH_FIREWALL" \
            --project="$PROJECT_ID" \
            --network=default \
            --allow=tcp:22 \
            --source-ranges=35.235.240.0/20 \
            --target-tags=hw5-vm \
            --quiet
    fi

    create_hw5_vm "$SERVER_VM" server "$SERVER_MACHINE" "$SERVER_SA"
    create_hw5_vm "$SUBSCRIBER_VM" subscriber "$SUBSCRIBER_MACHINE" "$SUBSCRIBER_SA"
    create_hw5_vm "$CLIENT_VM" client "$CLIENT_MACHINE" "$CLIENT_SA"

    printf '%s\n' "$SERVER_IP" > .runtime/server-ip.txt
    echo "Server URL: http://${SERVER_IP}:${PORT}"
    echo "VM startup installation may still be running."
}
