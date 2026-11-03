#!/bin/bash

with_sql_connection() (
    set -euo pipefail
    local mode="$1"
    shift
    local secret
    local proxy_pid
    local connection_name

    mkdir -p .runtime
    chmod 700 .runtime

    if [ ! -x .runtime/cloud-sql-proxy ]; then
        curl --fail --location --retry 5 \
            https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.26.3/cloud-sql-proxy.linux.amd64 \
            --output .runtime/cloud-sql-proxy
        chmod 700 .runtime/cloud-sql-proxy
    fi

    case "$mode" in
        admin)
            export PGUSER="postgres"
            secret="${SQL_SECRET}-admin"
            ;;
        app)
            export PGUSER="$SQL_USER"
            secret="$SQL_SECRET"
            ;;
        *)
            echo "Connection mode must be admin or app." >&2
            exit 1
            ;;
    esac

    connection_name=$(gcloud sql instances describe "$SQL_INSTANCE" \
        --project="$PROJECT_ID" \
        --format="value(connectionName)")

    PGPASSWORD=$(gcloud secrets versions access latest \
        --secret="$secret" \
        --project="$PROJECT_ID")
    export PGPASSWORD

    export PGHOST="127.0.0.1"
    export PGDATABASE="$SQL_DATABASE"
    export PGSSLMODE="disable"
    export PGCONNECT_TIMEOUT="5"
    export SQL_USER

    PGPORT=$(python3 - <<'PY'
import socket

with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)
    export PGPORT

    CSQL_PROXY_TOKEN=$(gcloud auth print-access-token \
        --project="$PROJECT_ID")
    export CSQL_PROXY_TOKEN

    .runtime/cloud-sql-proxy \
        --address=127.0.0.1 \
        --port="$PGPORT" \
        "$connection_name" > .runtime/sql-proxy.log 2>&1 &
    proxy_pid=$!
    unset CSQL_PROXY_TOKEN

    trap 'kill "$proxy_pid" 2>/dev/null || true; wait "$proxy_pid" 2>/dev/null || true' EXIT

    .venv/bin/python - "$proxy_pid" <<'PY'
import os
import sys
import time

import psycopg

pid = int(sys.argv[1])
last_error = None

for attempt in range(30):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        raise SystemExit(
            "SQL proxy exited. Check .runtime/sql-proxy.log."
        )

    try:
        with psycopg.connect() as connection:
            connection.execute("SELECT 1")
        print("Database connection verified.")
        break
    except psycopg.OperationalError as error:
        last_error = error
        time.sleep(2)
else:
    raise SystemExit(f"Database connection failed: {last_error}")
PY

    "$@"
)
