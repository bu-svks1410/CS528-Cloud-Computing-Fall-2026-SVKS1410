wait_sql_operation() {
    local operation="$1"
    local response
    local status
    local attempt

    for attempt in $(seq 1 180); do
        response=$(gcloud sql operations describe "$operation" \
            --project="$PROJECT_ID" \
            --format=json) || return 1

        status=$(printf '%s' "$response" | python3 -c \
            'import json, sys; print(json.load(sys.stdin)["status"])') || return 1

        if [ "$status" = "DONE" ]; then
            printf '%s' "$response" | python3 -c '
import json
import sys

operation = json.load(sys.stdin)
if operation.get("error"):
    print(json.dumps(operation["error"], indent=2), file=sys.stderr)
    sys.exit(1)
print("Cloud SQL operation completed successfully.")
'
            return $?
        fi

        if [ "$((attempt % 6))" -eq 1 ]; then
            echo "Waiting for Cloud SQL operation ${operation}: ${status}"
        fi

        sleep 10
    done

    echo "Cloud SQL operation is still pending after 30 minutes: $operation" >&2
    return 1
}

wait_sql_idle() {
    local operations
    local operation

    operations=$(gcloud sql operations list \
        --instance="$SQL_INSTANCE" \
        --project="$PROJECT_ID" \
        --filter='status!=DONE' \
        --format='value(name)') || return 1

    for operation in $operations; do
        wait_sql_operation "$operation" || return 1
    done
}

set_sql_policy() {
    local desired="$1"
    local current
    local operation

    case "$desired" in
        ALWAYS|NEVER) ;;
        *)
            echo "Unsupported Cloud SQL activation policy." >&2
            return 1
            ;;
    esac

    wait_sql_idle || return 1

    current=$(gcloud sql instances describe "$SQL_INSTANCE" \
        --project="$PROJECT_ID" \
        --format='value(settings.activationPolicy)') || return 1

    if [ "$current" != "$desired" ]; then
        operation=$(gcloud sql instances patch "$SQL_INSTANCE" \
            --project="$PROJECT_ID" \
            --activation-policy="$desired" \
            --async \
            --quiet \
            --format='value(name)') || return 1

        if [ -z "$operation" ]; then
            echo "Cloud SQL did not return an operation name." >&2
            return 1
        fi

        wait_sql_operation "$operation" || return 1
    fi

    current=$(gcloud sql instances describe "$SQL_INSTANCE" \
        --project="$PROJECT_ID" \
        --format='value(settings.activationPolicy)') || return 1

    if [ "$current" != "$desired" ]; then
        echo "Cloud SQL activation policy verification failed." >&2
        return 1
    fi

    echo "Cloud SQL activation policy verified: $desired"
}
