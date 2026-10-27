#!/bin/bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

set -a
. ./config.sh
set +a

. ./setup_permissions.sh
. ./setup_sql.sh
. ./sql_connection.sh
. ./setup_vms.sh

mkdir -p results .runtime
chmod 700 .runtime

for command in gcloud python3 curl tar; do
    command -v "$command" >/dev/null
done

for file in startup.sh setup_permissions.sh setup_sql.sh \
    sql_connection.sh setup_vms.sh; do
    bash -n "$file"
done

for function in setup_permissions setup_sql with_sql_connection setup_vms; do
    declare -F "$function" >/dev/null
done

if [ ! -x client/http-client ]; then
    echo "The new Linux client must be present and executable." >&2
    exit 1
fi

if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi

.venv/bin/python -m pip install -r requirements-lock.txt

gcloud projects describe "$PROJECT_ID" \
    --project="$PROJECT_ID" >/dev/null

gcloud storage ls "gs://${BUCKET_NAME}/data/0.html" \
    --project="$PROJECT_ID" >/dev/null

setup_permissions
setup_sql

with_sql_connection admin .venv/bin/python initialize_schema.py

with_sql_connection app .venv/bin/python - <<'PY'
import psycopg

with psycopg.connect() as connection:
    for table in ("requests", "request_errors"):
        row = connection.execute(
            "SELECT has_table_privilege(current_user, %s, 'SELECT'), "
            "has_table_privilege(current_user, %s, 'INSERT')",
            (table, table)
        ).fetchone()
        if row != (True, True):
            raise RuntimeError(f"Missing application permissions for {table}")

print("Application database permissions verified.")
PY

if ! gcloud artifacts repositories describe hw5-functions \
    --project="$PROJECT_ID" \
    --location="$REGION" >/dev/null 2>&1; then
    gcloud artifacts repositories create hw5-functions \
        --project="$PROJECT_ID" \
        --location="$REGION" \
        --repository-format=docker \
        --quiet
fi

gcloud functions deploy "$MONITOR_FUNCTION" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --gen2 \
    --runtime=python312 \
    --source=sql_monitor \
    --entry-point=monitor_sql \
    --trigger-http \
    --no-allow-unauthenticated \
    --service-account="${MONITOR_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --build-service-account="projects/${PROJECT_ID}/serviceAccounts/${BUILD_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --docker-repository="projects/${PROJECT_ID}/locations/${REGION}/repositories/hw5-functions" \
    --stage-bucket="$BUNDLE_BUCKET" \
    --set-env-vars="PROJECT_ID=${PROJECT_ID},SQL_INSTANCE=${SQL_INSTANCE}" \
    --memory=256Mi \
    --timeout=120s \
    --min-instances=0 \
    --max-instances=1 \
    --quiet

ACTIVE_ACCOUNT=$(gcloud auth list \
    --filter="status:ACTIVE" \
    --format="value(account)")

if [ -z "$ACTIVE_ACCOUNT" ]; then
    echo "No active gcloud account was found." >&2
    exit 1
fi

if [[ "$ACTIVE_ACCOUNT" == *.gserviceaccount.com ]]; then
    INVOKER_MEMBER="serviceAccount:${ACTIVE_ACCOUNT}"
else
    INVOKER_MEMBER="user:${ACTIVE_ACCOUNT}"
fi

gcloud run services add-iam-policy-binding "$MONITOR_FUNCTION" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --member="$INVOKER_MEMBER" \
    --role=roles/run.invoker \
    --quiet >/dev/null

gcloud functions describe "$MONITOR_FUNCTION" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --gen2 \
    --format="value(serviceConfig.uri)" \
    > .runtime/monitor-url.txt

setup_vms

echo "Infrastructure setup completed."
echo "Server URL: http://${SERVER_IP}:${PORT}"
echo "Verify VM startup and live requests before beginning the load test."
