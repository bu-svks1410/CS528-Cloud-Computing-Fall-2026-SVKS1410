import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from prepare_startup import build_startup
from setup_cloud import MARKER, ensure, gcloud, setup


ROOT = Path(__file__).resolve().parent


def save_record(name, data):
    directory = ROOT / "results"
    directory.mkdir(exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Saved {path}", flush=True)


def create(args):
    scripts = build_startup(args.project, args.bucket)
    accounts = setup(args.project, args.bucket)
    region = args.zone.rsplit("-", 1)[0]

    gcloud(args.project, ["compute", "networks", "describe", "default"], read=True)

    ensure(
        args.project,
        ["compute", "addresses", "list", f"--regions={region}"],
        "name", "hw4-server-ip",
        [
            "compute", "addresses", "create", "hw4-server-ip",
            f"--region={region}", f"--description={MARKER}",
            "--network-tier=PREMIUM"
        ]
    )

    address = gcloud(args.project, [
        "compute", "addresses", "describe", "hw4-server-ip",
        f"--region={region}"
    ], read=True)

    for name, ports, sources, target in [
        ("hw4-http", "tcp:8080", "0.0.0.0/0", "hw4-server"),
        ("hw4-ssh", "tcp:22", "35.235.240.0/20", "hw4-vm")
    ]:
        ensure(
            args.project,
            ["compute", "firewall-rules", "list"],
            "name", name,
            [
                "compute", "firewall-rules", "create", name,
                "--network=default", "--direction=INGRESS",
                f"--allow={ports}", f"--source-ranges={sources}",
                f"--target-tags={target}", f"--description={MARKER}"
            ]
        )

    instances = []
    for role, machine in [
        ("server", "f1-micro"),
        ("subscriber", "e2-micro"),
        ("client", "e2-small")
    ]:
        name = f"hw4-{role}"
        command = [
            "compute", "instances", "create", name,
            f"--zone={args.zone}", f"--machine-type={machine}",
            "--image-family=" + (
                "ubuntu-2404-lts-amd64" if role == "client" else "debian-12"
            ),
            "--image-project=" + (
                "ubuntu-os-cloud" if role == "client" else "debian-cloud"
            ),
            "--boot-disk-size=10GB", "--boot-disk-type=pd-standard",
            "--network=default", "--network-tier=PREMIUM",
            f"--tags=hw4-vm,hw4-{role}",
            "--labels=assignment=cs528-hw4",
            f"--description={MARKER}"
        ]

        if role == "client":
            command += ["--no-service-account", "--no-scopes"]
        else:
            command += [
                f"--service-account={accounts[role]}",
                "--scopes=cloud-platform",
                f"--metadata-from-file=startup-script={scripts[role]}"
            ]

        if role == "server":
            command.append(f"--address={address['address']}")

        ensure(
            args.project,
            ["compute", "instances", "list", f"--zones={args.zone}"],
            "name", name, command
        )

        instance = gcloud(args.project, [
            "compute", "instances", "describe", name,
            f"--zone={args.zone}"
        ], read=True)

        if instance["machineType"].rsplit("/", 1)[-1] != machine:
            raise RuntimeError(f"Unexpected machine type for {name}")

        if instance["status"] != "RUNNING":
            raise RuntimeError(f"{name} is not running: {instance['status']}")

        instances.append({
            "name": name,
            "machineType": instance["machineType"],
            "creationTimestamp": instance["creationTimestamp"],
            "status": instance["status"],
            "networkInterfaces": instance["networkInterfaces"]
        })

    save_record("deployment.json", {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "project": args.project,
        "bucket": args.bucket,
        "zone": args.zone,
        "server_ip": address["address"],
        "instances": instances
    })

    print(f"Server URL: http://{address['address']}:8080/data/0.html")
    print("VM creation completed. Service installation may still be running.")


def delete(args):
    region = args.zone.rsplit("-", 1)[0]
    groups = [
        (
            ["compute", "instances"],
            ["hw4-server", "hw4-subscriber", "hw4-client"],
            [f"--zones={args.zone}"],
            [f"--zone={args.zone}", "--delete-disks=boot"],
            False
        ),
        (
            ["compute", "addresses"],
            ["hw4-server-ip"],
            [f"--regions={region}"],
            [f"--region={region}"],
            False
        ),
        (
            ["compute", "firewall-rules"],
            ["hw4-http", "hw4-ssh"],
            [], [], False
        ),
        (
            ["pubsub", "subscriptions"],
            ["hw4-forbidden-requests-sub"],
            [], [], True
        ),
        (
            ["pubsub", "topics"],
            ["hw4-forbidden-requests"],
            [], [], True
        )
    ]

    jobs = []
    for group, names, list_flags, delete_flags, labelled in groups:
        entries = gcloud(args.project, [*group, "list", *list_flags], read=True)
        for entry in entries:
            name = entry["name"].rsplit("/", 1)[-1]
            if name not in names:
                continue
            owned = (
                entry.get("labels", {}).get("assignment") == "cs528-hw4"
                if labelled else entry.get("description") == MARKER
            )
            if not owned:
                raise RuntimeError(f"Refusing to delete an unmanaged resource: {name}")
            jobs.append((group, name, delete_flags))

    outcomes = []
    for group, name, flags in jobs:
        print(f"Deleting {' '.join(group)} {name}", flush=True)
        outcome = {"resource": " ".join(group), "name": name}
        try:
            gcloud(args.project, [*group, "delete", name, *flags])
            outcome["deleted"] = True
        except subprocess.CalledProcessError as exc:
            outcome["deleted"] = False
            outcome["error"] = str(exc)
        outcome["finished_at"] = datetime.now(timezone.utc).isoformat()
        outcomes.append(outcome)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    save_record(f"deletion-{stamp}.json", {
        "project": args.project,
        "zone": args.zone,
        "outcomes": outcomes
    })

    if any(not item["deleted"] for item in outcomes):
        raise RuntimeError("Some deletions failed. Check the output before retrying.")

    print("HW4 compute and Pub/Sub cleanup completed.")
    print("The existing bucket, saved logs, service accounts, and IAM roles are retained.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["create", "delete"])
    parser.add_argument("--project", required=True)
    parser.add_argument("--bucket")
    parser.add_argument("--zone", default="us-central1-a")
    args = parser.parse_args()

    if args.action == "create":
        if not args.bucket:
            parser.error("--bucket is required for create")
        create(args)
    else:
        delete(args)
