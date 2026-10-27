#!/bin/bash

ensure_sql_secret() {
    local secret="$1"
    local versions
    local password_file

    if ! gcloud secrets describe "$secret" \
        --project="$PROJECT_ID" >/dev/null 2>&1; then
        gcloud secrets create "$secret" \
            --project="$PROJECT_ID" \
            --replication-policy=automatic \
            --quiet
    fi

    versions=$(gcloud secrets versions list "$secret" \
        --project="$PROJECT_ID" \
        --filter="state=ENABLED" \
        --format="value(name)" \
        --limit=1)

    if [ -z "$versions" ]; then
        mkdir -p .secrets
        chmod 700 .secrets
        password_file=$(mktemp .secrets/password.XXXXXX)
        chmod 600 "$password_file"

        python3 -c 'import secrets; print(secrets.token_hex(32), end="")' \
            > "$password_file"

        if ! gcloud secrets versions add "$secret" \
            --project="$PROJECT_ID" \
            --data-file="$password_file" \
            --quiet; then
            rm -f "$password_file"
            return 1
        fi

        rm -f "$password_file"
    fi
}

setup_sql() {
    local policy
    local database_exists
    local user_exists
    local app_password
    local admin_password

    ensure_sql_secret "$SQL_SECRET"
    ensure_sql_secret "${SQL_SECRET}-admin"

    if gcloud sql instances describe "$SQL_INSTANCE" \
        --project="$PROJECT_ID" >/dev/null 2>&1; then

        policy=$(gcloud sql instances describe "$SQL_INSTANCE" \
            --project="$PROJECT_ID" \
            --format="value(settings.activationPolicy)")

        if [ "$policy" != "ALWAYS" ]; then
            gcloud sql instances patch "$SQL_INSTANCE" \
                --project="$PROJECT_ID" \
                --activation-policy=ALWAYS \
                --quiet
        fi

        echo "Reusing the existing Cloud SQL instance."
    else
        gcloud sql instances create "$SQL_INSTANCE" \
            --project="$PROJECT_ID" \
            --region="$REGION" \
            --database-version="$SQL_VERSION" \
            --edition="$SQL_EDITION" \
            --tier="$SQL_TIER" \
            --availability-type=ZONAL \
            --storage-type=SSD \
            --storage-size=10 \
            --no-storage-auto-increase \
            --assign-ip \
            --no-backup \
            --quiet
    fi

    database_exists=$(gcloud sql databases list \
        --instance="$SQL_INSTANCE" \
        --project="$PROJECT_ID" \
        --filter="name=$SQL_DATABASE" \
        --format="value(name)")

    if [ -z "$database_exists" ]; then
        gcloud sql databases create "$SQL_DATABASE" \
            --instance="$SQL_INSTANCE" \
            --project="$PROJECT_ID" \
            --quiet
    fi

    app_password=$(gcloud secrets versions access latest \
        --secret="$SQL_SECRET" \
        --project="$PROJECT_ID")

    admin_password=$(gcloud secrets versions access latest \
        --secret="${SQL_SECRET}-admin" \
        --project="$PROJECT_ID")

    gcloud sql users set-password postgres \
        --instance="$SQL_INSTANCE" \
        --project="$PROJECT_ID" \
        --password="$admin_password" \
        --quiet

    user_exists=$(gcloud sql users list \
        --instance="$SQL_INSTANCE" \
        --project="$PROJECT_ID" \
        --filter="name=$SQL_USER" \
        --format="value(name)")

    if [ -z "$user_exists" ]; then
        gcloud sql users create "$SQL_USER" \
            --instance="$SQL_INSTANCE" \
            --project="$PROJECT_ID" \
            --password="$app_password" \
            --quiet
    else
        gcloud sql users set-password "$SQL_USER" \
            --instance="$SQL_INSTANCE" \
            --project="$PROJECT_ID" \
            --password="$app_password" \
            --quiet
    fi

    unset app_password admin_password

    retry_command gcloud secrets add-iam-policy-binding "$SQL_SECRET" \
        --project="$PROJECT_ID" \
        --member="serviceAccount:${SERVER_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role=roles/secretmanager.secretAccessor \
        --quiet >/dev/null

    SQL_CONNECTION=$(gcloud sql instances describe "$SQL_INSTANCE" \
        --project="$PROJECT_ID" \
        --format="value(connectionName)")
    export SQL_CONNECTION

    echo "Cloud SQL instance, database, and users are ready."
}
