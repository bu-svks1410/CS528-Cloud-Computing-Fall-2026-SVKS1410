import json
import os
from datetime import datetime, timezone

import functions_framework
import google.auth
from google.auth.transport.requests import AuthorizedSession


@functions_framework.http
def monitor_sql(request):
    if request.method != "POST":
        return (
            {"error": "Use POST"},
            405,
            {"Allow": "POST"}
        )

    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return {"error": "Expected a JSON object"}, 400

    action = payload.get("action", "check")
    if action not in ("check", "stop"):
        return {"error": "Action must be check or stop"}, 400

    project = os.environ["PROJECT_ID"]
    instance = os.environ["SQL_INSTANCE"]
    url = (
        "https://sqladmin.googleapis.com/sql/v1beta4/projects/"
        f"{project}/instances/{instance}"
    )

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    with AuthorizedSession(credentials) as session:
        response = session.get(url, timeout=30)
        if not response.ok:
            print(json.dumps({
                "event": "sql_status_check_failed",
                "upstream_status": response.status_code
            }), flush=True)
            return {"error": "Unable to read Cloud SQL status"}, 502

        data = response.json()
        state = data.get("state")
        policy = data.get("settings", {}).get("activationPolicy")

        result = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "instance": instance,
            "action": action,
            "state": state,
            "activation_policy": policy,
            "running_enabled": state == "RUNNABLE" and policy == "ALWAYS"
        }

        if action == "stop":
            if policy == "NEVER":
                result["result"] = "Stop policy is already set"
            else:
                response = session.patch(
                    url,
                    json={"settings": {"activationPolicy": "NEVER"}},
                    timeout=30
                )
                if not response.ok:
                    print(json.dumps({
                        "event": "sql_stop_failed",
                        "upstream_status": response.status_code
                    }), flush=True)
                    return {"error": "Unable to request Cloud SQL stop"}, 502

                operation = response.json()
                result["result"] = "Stop requested"
                result["operation"] = operation.get("name")
                result["operation_status"] = operation.get("status")
                print(json.dumps(result), flush=True)
                return result, 202

        print(json.dumps(result), flush=True)
        return result, 200
