retry_command() {
    local attempt
    for attempt in 1 2 3 4 5 6; do
        if "$@"; then
            return 0
        fi
        if [ "$attempt" -lt 6 ]; then
            sleep 10
        fi
    done
    return 1
}

setup_permissions() {
    local account="${VM_SA}@${PROJECT_ID}.iam.gserviceaccount.com"

    gcloud services enable \
        compute.googleapis.com \
        iam.googleapis.com \
        sqladmin.googleapis.com \
        secretmanager.googleapis.com \
        storage.googleapis.com \
        iap.googleapis.com \
        --project="$PROJECT_ID" \
        --quiet

    if ! gcloud iam service-accounts describe "$account" \
        --project="$PROJECT_ID" >/dev/null 2>&1; then
        gcloud iam service-accounts create "$VM_SA" \
            --project="$PROJECT_ID" \
            --display-name="HW6 model execution" \
            --quiet
    fi

    retry_command gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:${account}" \
        --role=roles/cloudsql.client \
        --condition=None \
        --quiet >/dev/null

    retry_command gcloud secrets add-iam-policy-binding "$SQL_SECRET" \
        --project="$PROJECT_ID" \
        --member="serviceAccount:${account}" \
        --role=roles/secretmanager.secretAccessor \
        --quiet >/dev/null

    retry_command gcloud storage buckets add-iam-policy-binding \
        "gs://${BUCKET_NAME}" \
        --member="serviceAccount:${account}" \
        --role=roles/storage.objectUser \
        --condition="expression=resource.name.startsWith('projects/_/buckets/${BUCKET_NAME}/objects/${OUTPUT_PREFIX}/'),title=hw6_object_access" \
        --quiet >/dev/null

    if ! gcloud compute firewall-rules describe "$SSH_FIREWALL" \
        --project="$PROJECT_ID" >/dev/null 2>&1; then
        gcloud compute firewall-rules create "$SSH_FIREWALL" \
            --project="$PROJECT_ID" \
            --network=default \
            --allow=tcp:22 \
            --source-ranges=35.235.240.0/20 \
            --target-tags=hw6-models \
            --quiet
    fi

    echo "HW6 service-account permissions and IAP SSH rule are ready."
}
