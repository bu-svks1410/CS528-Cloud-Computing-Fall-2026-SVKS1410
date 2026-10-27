#!/bin/bash
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
. ./config.sh

failures=0

remove_resource() {
    if ! "$@"; then
        failures=$((failures + 1))
        echo "A cleanup command failed; continuing with other resources." >&2
    fi
}

if gcloud sql instances describe "$SQL_INSTANCE" \
    --project="$PROJECT_ID" >/dev/null 2>&1; then
    remove_resource gcloud sql instances patch "$SQL_INSTANCE" \
        --project="$PROJECT_ID" \
        --activation-policy=NEVER \
        --quiet
fi

for vm in "$SERVER_VM" "$SUBSCRIBER_VM" "$CLIENT_VM"; do
    if gcloud compute instances describe "$vm" \
        --project="$PROJECT_ID" \
        --zone="$ZONE" >/dev/null 2>&1; then
        remove_resource gcloud compute instances delete "$vm" \
            --project="$PROJECT_ID" \
            --zone="$ZONE" \
            --delete-disks=boot \
            --quiet
    fi
done

if gcloud compute addresses describe "$SERVER_IP_NAME" \
    --project="$PROJECT_ID" \
    --region="$REGION" >/dev/null 2>&1; then
    remove_resource gcloud compute addresses delete "$SERVER_IP_NAME" \
        --project="$PROJECT_ID" \
        --region="$REGION" \
        --quiet
fi

for rule in "$HTTP_FIREWALL" "$SSH_FIREWALL"; do
    if gcloud compute firewall-rules describe "$rule" \
        --project="$PROJECT_ID" >/dev/null 2>&1; then
        remove_resource gcloud compute firewall-rules delete "$rule" \
            --project="$PROJECT_ID" \
            --quiet
    fi
done

if gcloud pubsub subscriptions describe "$SUBSCRIPTION_ID" \
    --project="$PROJECT_ID" >/dev/null 2>&1; then
    remove_resource gcloud pubsub subscriptions delete "$SUBSCRIPTION_ID" \
        --project="$PROJECT_ID" \
        --quiet
fi

if gcloud pubsub topics describe "$TOPIC_ID" \
    --project="$PROJECT_ID" >/dev/null 2>&1; then
    remove_resource gcloud pubsub topics delete "$TOPIC_ID" \
        --project="$PROJECT_ID" \
        --quiet
fi

if gcloud functions describe "$MONITOR_FUNCTION" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --gen2 >/dev/null 2>&1; then
    remove_resource gcloud functions delete "$MONITOR_FUNCTION" \
        --project="$PROJECT_ID" \
        --region="$REGION" \
        --gen2 \
        --quiet
fi

if gcloud artifacts repositories describe hw5-functions \
    --project="$PROJECT_ID" \
    --location="$REGION" >/dev/null 2>&1; then
    remove_resource gcloud artifacts repositories delete hw5-functions \
        --project="$PROJECT_ID" \
        --location="$REGION" \
        --quiet
fi

if gcloud storage buckets describe "gs://$BUNDLE_BUCKET" \
    --project="$PROJECT_ID" >/dev/null 2>&1; then
    remove_resource gcloud storage rm --recursive \
        "gs://$BUNDLE_BUCKET" \
        --project="$PROJECT_ID" \
        --quiet
fi

if [ "$failures" -ne 0 ]; then
    echo "Cleanup encountered $failures failed command(s)." >&2
    exit 1
fi

echo "Cleanup commands finished. Verify resource status separately."
echo "The Cloud SQL instance and its data were retained."
echo "The existing data bucket, saved logs, passwords, and service accounts were retained."
