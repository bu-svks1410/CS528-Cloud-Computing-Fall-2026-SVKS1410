import argparse
import json
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from client import run
from deploy import BACKEND, REGION, REGIONAL, ZONES, describe


def states(project):
    raw = subprocess.check_output(["gcloud", "compute", "backend-services", "get-health", BACKEND,
                                   *REGIONAL, f"--project={project}", "--format=json"], text=True)
    return {entry["instance"].split("/")[-1]: entry["healthState"]
            for group in json.loads(raw) for entry in (group.get("status") or {}).get("healthStatus", [])}


def command(project, command_text):
    return subprocess.check_output(["gcloud", "compute", "ssh", "hw8-web-a", f"--zone={ZONES[0]}",
                                    f"--project={project}", "--tunnel-through-iap", "--quiet",
                                    "--command", command_text], text=True).strip()


def service(project, action):
    return float(command(project, f"sudo systemctl {action} hw8-server.service && date -u +%s.%N").splitlines()[-1])


def rows(path):
    with path.open() as source:
        return sorted((json.loads(line) for line in source if line.endswith("\n")), key=lambda row: row["sent"])


def served(row):
    return row["status"] in (200, 400) and row["zone"] in ZONES and not row["error"]


def experiment(project):
    healthy = {"hw8-web-a": "HEALTHY", "hw8-web-b": "HEALTHY"}
    if states(project) != healthy:
        raise RuntimeError("Both backends must be HEALTHY. Check startup and rerun.")
    command(project, "systemctl is-active hw8-server.service")
    ip = describe(project, "addresses", "hw8-ip", REGIONAL)["address"]
    directory = Path("results") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory.mkdir(parents=True)
    log = directory / "requests.jsonl"
    events = {"project": project, "region": REGION, "initial_health": healthy}
    event_file = directory / "events.json"
    stop = threading.Event()
    restore = False
    with ThreadPoolExecutor(max_workers=1) as pool:
        client = pool.submit(run, ip, 8080, log, stop)
        try:
            time.sleep(60)
            baseline = rows(log)
            if len(baseline) < 55 or not all(map(served, baseline)) or {row["zone"] for row in baseline} != set(ZONES):
                raise RuntimeError("Baseline did not show clean responses from both zones.")
            events["baseline_end"] = time.time()
            restore = True
            events["stopped"] = service(project, "stop")
            time.sleep(11)
            while time.time() < events["stopped"] + 60:
                events["outage_health"] = states(project)
                events["health_checked"] = time.time()
                outage = [r for r in rows(log) if r["sent"] >= events["stopped"]]
                stable = len(outage) >= 10 and all(served(r) and r["zone"] == ZONES[1] for r in outage[-10:])
                expected = {"hw8-web-a": "UNHEALTHY", "hw8-web-b": "HEALTHY"}
                if stable and events["outage_health"] == expected and events["health_checked"] - events["stopped"] < 60:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Failover not confirmed within one minute. Inspect health and curl each endpoint.")
            events["restart_begin"] = time.time()
            events["restarted"] = service(project, "start")
            restore = False
            while time.time() < events["restarted"] + 60:
                if any(served(r) and r["zone"] == ZONES[0] and events["restarted"] <= r["sent"] and r["received"] < events["restarted"] + 60 for r in rows(log)):
                    break
                time.sleep(0.25)
            else:
                raise RuntimeError("No response from the restored zone within 60 seconds. Inspect health and curl the service.")
            time.sleep(12)
            events["final_health"] = states(project)
            if events["final_health"] != healthy:
                raise RuntimeError("Both backends must report HEALTHY after recovery.")
            events["complete"] = True
        finally:
            stop.set()
            event_file.write_text(json.dumps(events, indent=2) + "\n")
            print(f"Run directory: {directory}", flush=True)
            try:
                client.result()
            finally:
                if restore:
                    service(project, "start")
    return directory


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    print(experiment(args.project))
