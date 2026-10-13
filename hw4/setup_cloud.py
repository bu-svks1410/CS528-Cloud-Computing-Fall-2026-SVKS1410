import argparse
import json
import re
import subprocess
import sys
import time


MARKER = "CS528 HW4 managed resources"


def gcloud(project, args, read=False):
    command = [
        "gcloud", *args, f"--project={project}", "--quiet",
        "--format=json" if read else "--format=none"
    ]
    binding = "add-iam-policy-binding" in args
    attempts = 13 if binding else 1

    for attempt in range(attempts):
        result = subprocess.run(command, text=True, capture_output=True)

        if result.returncode == 0:
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr, flush=True)
            if read:
                return json.loads(result.stdout)
            if result.stdout:
                print(result.stdout, end="", flush=True)
            return None

        error = result.stderr.lower()
        role_not_ready = (
            "does not exist in the resource's hierarchy" in error
        )

        if binding and role_not_ready and attempt < attempts - 1:
            print(
                f"IAM role not yet available; retrying in 15 seconds "
                f"({attempt + 1}/{attempts - 1}).",
                flush=True
            )
            time.sleep(15)
            continue

        if result.stdout:
            print(result.stdout, end="", flush=True)
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr, flush=True)
        raise subprocess.CalledProcessError(
            result.returncode, command,
            output=result.stdout, stderr=result.stderr
        )


def ensure(project, listing, field, name, creation, labelled=False):
    entries = gcloud(project, listing, read=True)
    for entry in entries:
        value = entry.get(field, "").rsplit("/", 1)[-1]
        if value != name:
            continue
        owned = (
            entry.get("labels", {}).get("assignment") == "cs528-hw4"
            if labelled else entry.get("description") == MARKER
        )
        if not owned:
            raise RuntimeError(f"Existing resource is not managed by this script: {name}")
        print(f"Reusing {name}", flush=True)
        return
    print(f"Creating {name}", flush=True)
    gcloud(project, creation)


def setup(project, bucket):
    for value in (project, bucket):
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value):
            raise ValueError("Invalid project or bucket name")

    gcloud(project, [
        "services", "enable",
        "compute.googleapis.com", "iam.googleapis.com",
        "storage.googleapis.com", "pubsub.googleapis.com",
        "logging.googleapis.com", "monitoring.googleapis.com",
        "iap.googleapis.com"
    ])

    accounts = {}
    for role in ("server", "subscriber"):
        name = f"hw4-{role}-sa"
        email = f"{name}@{project}.iam.gserviceaccount.com"
        ensure(
            project,
            ["iam", "service-accounts", "list"],
            "email", email,
            [
                "iam", "service-accounts", "create", name,
                f"--display-name=HW4 {role}",
                f"--description={MARKER}"
            ]
        )
        accounts[role] = email

    roles = {
        "hw4FileReader": ["storage.objects.get"],
        "hw4LogWriter": [
            "storage.objects.get",
            "storage.objects.create",
            "storage.objects.delete"
        ]
    }

    for name, permissions in roles.items():
        ensure(
            project, ["iam", "roles", "list"], "name", name,
            [
                "iam", "roles", "create", name,
                f"--title={name}", f"--description={MARKER}",
                "--stage=GA", "--permissions=" + ",".join(permissions)
            ]
        )
        current = gcloud(project, ["iam", "roles", "describe", name], read=True)
        if set(current.get("includedPermissions", [])) != set(permissions):
            raise RuntimeError(f"Unexpected permissions in role {name}")
        if current.get("deleted") or current.get("stage") == "DISABLED":
            raise RuntimeError(f"Role is unavailable: {name}")

    for service, role, prefix in [
        ("server", "hw4FileReader", "data/"),
        ("subscriber", "hw4LogWriter", "hw4-logs/")
    ]:
        resource = f"projects/_/buckets/{bucket}/objects/{prefix}"
        condition = (
            f"expression=resource.name.startsWith('{resource}'),"
            f"title=hw4_{service}_objects"
        )
        gcloud(project, [
            "storage", "buckets", "add-iam-policy-binding", f"gs://{bucket}",
            f"--member=serviceAccount:{accounts[service]}",
            f"--role=projects/{project}/roles/{role}",
            f"--condition={condition}"
        ])

    topic = "hw4-forbidden-requests"
    subscription = "hw4-forbidden-requests-sub"

    ensure(
        project, ["pubsub", "topics", "list"], "name", topic,
        [
            "pubsub", "topics", "create", topic,
            "--labels=assignment=cs528-hw4"
        ],
        labelled=True
    )

    ensure(
        project, ["pubsub", "subscriptions", "list"], "name", subscription,
        [
            "pubsub", "subscriptions", "create", subscription,
            f"--topic={topic}", "--ack-deadline=60",
            "--labels=assignment=cs528-hw4"
        ],
        labelled=True
    )

    current = gcloud(
        project, ["pubsub", "subscriptions", "describe", subscription], read=True
    )
    if current.get("topic") != f"projects/{project}/topics/{topic}":
        raise RuntimeError("Subscription is attached to an unexpected topic")

    gcloud(project, [
        "pubsub", "topics", "add-iam-policy-binding", topic,
        f"--member=serviceAccount:{accounts['server']}",
        "--role=roles/pubsub.publisher"
    ])

    gcloud(project, [
        "pubsub", "subscriptions", "add-iam-policy-binding", subscription,
        f"--member=serviceAccount:{accounts['subscriber']}",
        "--role=roles/pubsub.subscriber"
    ])

    gcloud(project, [
        "projects", "add-iam-policy-binding", project,
        f"--member=serviceAccount:{accounts['server']}",
        "--role=roles/logging.logWriter", "--condition=None"
    ])

    print("HW4 permissions setup completed.", flush=True)
    return accounts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--bucket", required=True)
    args = parser.parse_args()
    setup(args.project, args.bucket)
