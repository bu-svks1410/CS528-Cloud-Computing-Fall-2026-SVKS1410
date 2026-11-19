import argparse
import json
import subprocess
from pathlib import Path

from prepare_startup import build_startup
from setup_cloud import MARKER, gcloud, setup

REGION = "us-central1"
ZONES = ("us-central1-a", "us-central1-b")
REGIONAL = [f"--region={REGION}"]
BACKEND = "hw8-backend"
FRONTEND = "hw8-forward"
CHECK = "hw8-health"


def describe(project, kind, name, scope):
    cmd = ["gcloud", "compute", *kind.split(), "describe", name, *scope,
           f"--project={project}", "--format=json", "--quiet"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return json.loads(result.stdout)
    if "was not found" in result.stderr.lower() or "could not be found" in result.stderr.lower():
        return None
    raise RuntimeError(result.stderr.strip())


def resources():
    yield "firewall-rules", "hw8-web", [], ["--network=default", "--allow=tcp:8080", "--source-ranges=0.0.0.0/0", "--target-tags=hw8-web"]
    yield "firewall-rules", "hw8-iap", [], ["--network=default", "--allow=tcp:22", "--source-ranges=35.235.240.0/20", "--target-tags=hw8-vm"]
    yield "addresses", "hw8-ip", REGIONAL, ["--network-tier=PREMIUM"]
    for role, zone in [("web-a", ZONES[0]), ("web-b", ZONES[1]), ("subscriber", ZONES[0])]:
        yield "instances", f"hw8-{role}", [f"--zone={zone}"], []
    for letter, zone in zip("ab", ZONES):
        yield "instance-groups unmanaged", f"hw8-group-{letter}", [f"--zone={zone}"], []
    yield "health-checks", CHECK, REGIONAL, ["--port=8080", "--request-path=/healthz", "--check-interval=2s", "--timeout=1s", "--healthy-threshold=2", "--unhealthy-threshold=2"]
    yield "backend-services", BACKEND, REGIONAL, ["--load-balancing-scheme=EXTERNAL", "--protocol=TCP", f"--health-checks={CHECK}", f"--health-checks-region={REGION}", "--session-affinity=NONE"]
    yield "forwarding-rules", FRONTEND, REGIONAL, ["--load-balancing-scheme=EXTERNAL", "--ports=8080", "--address=hw8-ip", f"--backend-service={BACKEND}", "--network-tier=PREMIUM", "--ip-protocol=TCP"]


def create(project, bucket):
    gcloud(project, ["storage", "objects", "describe", f"gs://{bucket}/data/0.html"], read=True)
    accounts = setup(project, bucket)
    scripts = build_startup(project, bucket)
    for kind, name, scope, flags in resources():
        current = describe(project, kind, name, scope)
        if current and current.get("description") != MARKER:
            raise RuntimeError(f"Resource belongs to a different deployment: {name}")
        if not current:
            command = ["compute", *kind.split(), "create"]
            if kind == "health-checks":
                command.append("http")
            if kind == "instances":
                role = "subscriber" if name == "hw8-subscriber" else "server"
                flags = ["--machine-type=e2-micro", "--network=default", "--image-family=debian-12",
                         "--image-project=debian-cloud", "--boot-disk-type=pd-standard", "--boot-disk-size=10GB",
                         "--tags=hw8-vm" if role == "subscriber" else "--tags=hw8-vm,hw8-web",
                         f"--service-account={accounts[role]}", "--scopes=cloud-platform",
                         f"--metadata-from-file=startup-script={scripts[role]}"]
            gcloud(project, [*command, name, *scope, *flags, f"--description={MARKER}"])
        if kind == "instance-groups unmanaged":
            vm = "hw8-web-" + name[-1]
            members = gcloud(project, ["compute", *kind.split(), "list-instances", name, *scope], read=True)
            if not any(item["instance"].endswith("/" + vm) for item in members):
                gcloud(project, ["compute", *kind.split(), "add-instances", name, *scope, f"--instances={vm}"])
        if kind == "backend-services":
            backend = describe(project, kind, name, scope)
            for letter, zone in zip("ab", ZONES):
                group = "hw8-group-" + letter
                if not any(b["group"].endswith("/" + group) for b in backend.get("backends", [])):
                    gcloud(project, ["compute", kind, "add-backend", name, *scope, f"--instance-group={group}", f"--instance-group-zone={zone}"])
    ip = describe(project, "addresses", "hw8-ip", REGIONAL)["address"]
    print(f"Frontend: http://{ip}:8080", flush=True)


def cleanup(project):
    for kind, name, scope, flags in reversed(list(resources())):
        current = describe(project, kind, name, scope)
        if current is None:
            continue
        if current.get("description") != MARKER:
            raise RuntimeError(f"Refusing to delete resource without HW8 description: {name}")
        extra = ["--delete-disks=boot"] if kind == "instances" else []
        gcloud(project, ["compute", *kind.split(), "delete", name, *scope, *extra])
    for kind, name in [("subscriptions", "hw8-forbidden-requests-sub"), ("topics", "hw8-forbidden-requests")]:
        items = gcloud(project, ["pubsub", kind, "list"], read=True)
        for item in items:
            if item["name"].endswith("/" + name) and item.get("labels", {}).get("assignment") == "cs528-hw8":
                gcloud(project, ["pubsub", kind, "delete", name])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["create", "cleanup"])
    parser.add_argument("--project", required=True)
    parser.add_argument("--bucket")
    args = parser.parse_args()
    if args.action == "create":
        if not args.bucket:
            parser.error("create requires --bucket")
        create(args.project, args.bucket)
    else:
        cleanup(args.project)
