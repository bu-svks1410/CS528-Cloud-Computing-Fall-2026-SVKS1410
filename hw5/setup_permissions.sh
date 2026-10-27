#!/bin/bash

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

grant_project_role() {
    local account="$1"
    local role="$2"
    retry_command gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --project="$PROJECT_ID" \
        --member="serviceAccount:${account}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role="$role" \
        --condition=None \
        --quiet >/dev/null
}

setup_permissions() {
    gcloud services enable \
        compute.googleapis.com \
        iam.googleapis.com \
        storage.googleapis.com \
        pubsub.googleapis.com \
        logging.googleapis.com \
        monitoring.googleapis.com \
        sqladmin.googleapis.com \
        secretmanager.googleapis.com \
        cloudfunctions.googleapis.com \
        cloudbuild.googleapis.com \
        artifactregistry.googleapis.com \
        run.googleapis.com \
        iap.googleapis.com \
        --project="$PROJECT_ID" \
        --quiet

    local account
    for account in "$SERVER_SA" "$SUBSCRIBER_SA" "$CLIENT_SA" \
        "$MONITOR_SA" "$BUILD_SA"; do
        if ! gcloud iam service-accounts describe \
            "${account}@${PROJECT_ID}.iam.gserviceaccount.com" \
            --project="$PROJECT_ID" >/dev/null 2>&1; then
            gcloud iam service-accounts create "$account" \
                --display-name="$account" \
                --project="$PROJECT_ID" \
                --quiet
        fi
    done

    if ! gcloud storage buckets describe "gs://$BUNDLE_BUCKET" \
        --project="$PROJECT_ID" >/dev/null 2>&1; then
        gcloud storage buckets create "gs://$BUNDLE_BUCKET" \
            --project="$PROJECT_ID" \
            --location="$REGION" \
            --uniform-bucket-level-access \
            --public-access-prevention \
            --soft-delete-duration=0
    fi

    gcloud storage buckets update "gs://$BUNDLE_BUCKET" \
        --project="$PROJECT_ID" \
        --uniform-bucket-level-access \
        --public-access-prevention

    for account in "$SERVER_SA" "$SUBSCRIBER_SA" "$CLIENT_SA"; do
        retry_command gcloud storage buckets add-iam-policy-binding \
            "gs://$BUNDLE_BUCKET" \
            --project="$PROJECT_ID" \
            --member="serviceAccount:${account}@${PROJECT_ID}.iam.gserviceaccount.com" \
            --role=roles/storage.objectViewer \
            --condition=None >/dev/null
    done

    grant_project_role "$SERVER_SA" roles/cloudsql.client
    grant_project_role "$SERVER_SA" roles/logging.logWriter
    grant_project_role "$BUILD_SA" roles/cloudbuild.builds.builder

    if ! gcloud iam roles describe hw5SqlMonitor \
        --project="$PROJECT_ID" >/dev/null 2>&1; then
        gcloud iam roles create hw5SqlMonitor \
            --project="$PROJECT_ID" \
            --title="HW5 SQL Monitor" \
            --permissions=cloudsql.instances.get,cloudsql.instances.update \
            --stage=GA
    else
        gcloud iam roles update hw5SqlMonitor \
            --project="$PROJECT_ID" \
            --permissions=cloudsql.instances.get,cloudsql.instances.update \
            --stage=GA
    fi

    grant_project_role "$MONITOR_SA" \
        "projects/${PROJECT_ID}/roles/hw5SqlMonitor"

    if ! gcloud pubsub topics describe "$TOPIC_ID" \
        --project="$PROJECT_ID" >/dev/null 2>&1; then
        gcloud pubsub topics create "$TOPIC_ID" \
            --project="$PROJECT_ID"
    fi

    if ! gcloud pubsub subscriptions describe "$SUBSCRIPTION_ID" \
        --project="$PROJECT_ID" >/dev/null 2>&1; then
        gcloud pubsub subscriptions create "$SUBSCRIPTION_ID" \
            --project="$PROJECT_ID" \
            --topic="$TOPIC_ID" \
            --ack-deadline=600
    fi

    retry_command gcloud pubsub topics add-iam-policy-binding "$TOPIC_ID" \
        --project="$PROJECT_ID" \
        --member="serviceAccount:${SERVER_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role=roles/pubsub.publisher >/dev/null

    retry_command gcloud pubsub subscriptions add-iam-policy-binding \
        "$SUBSCRIPTION_ID" \
        --project="$PROJECT_ID" \
        --member="serviceAccount:${SUBSCRIBER_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role=roles/pubsub.subscriber >/dev/null

    retry_command gcloud storage buckets add-iam-policy-binding \
        "gs://$BUCKET_NAME" \
        --project="$PROJECT_ID" \
        --member="serviceAccount:${SERVER_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role=roles/storage.objectViewer \
        --condition="expression=resource.name.startsWith('projects/_/buckets/${BUCKET_NAME}/objects/data/'),title=hw5_data_read" \
        >/dev/null

    retry_command gcloud storage buckets add-iam-policy-binding \
        "gs://$BUCKET_NAME" \
        --project="$PROJECT_ID" \
        --member="serviceAccount:${SUBSCRIBER_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role=roles/storage.objectUser \
        --condition="expression=resource.name == 'projects/_/buckets/${BUCKET_NAME}/objects/${SUBSCRIBER_LOG_OBJECT}',title=hw5_log_access" \
        >/dev/null

    echo "HW5 permissions and supporting resources are ready."
}
