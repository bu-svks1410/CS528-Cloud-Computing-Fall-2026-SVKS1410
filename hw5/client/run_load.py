import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    host, port = sys.argv[1:]
    output = Path.home() / "hw5-load-results"
    output.mkdir(exist_ok=False)

    command = [
        "sudo", "-n", "-u", "hw5",
        "/opt/hw5/client/http-client",
        "-d", host,
        "-b", "none",
        "-w", "data",
        "-n", "50000",
        "-i", "11999",
        "-p", port,
        "-r", "528",
        "-t", "30"
    ]

    state = {
        "started_at": now(),
        "command": command,
        "requests_per_client": 50000,
        "seed": 528,
        "clients": [],
        "finished_at": None
    }

    def save():
        temporary = output / "status.tmp"
        temporary.write_text(json.dumps(state, indent=2) + "\n")
        temporary.replace(output / "status.json")

    processes = []
    logs = []
    save()

    try:
        for number in (1, 2):
            log = (output / f"client-{number}.log").open("w")
            logs.append(log)
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT
            )
            processes.append(process)
            state["clients"].append({
                "client": number,
                "pid": process.pid,
                "started_at": now(),
                "finished_at": None,
                "exit_code": None
            })
            save()

        while True:
            for process, entry in zip(processes, state["clients"]):
                code = process.poll()
                if code is not None and entry["finished_at"] is None:
                    entry["exit_code"] = code
                    entry["finished_at"] = now()
                    save()

            if all(process.poll() is not None for process in processes):
                break
            time.sleep(5)

        state["finished_at"] = now()
        save()
    finally:
        for log in logs:
            log.close()

    if any(entry["exit_code"] != 0 for entry in state["clients"]):
        raise SystemExit("At least one client failed.")

    print("Both clients finished successfully.", flush=True)


if __name__ == "__main__":
    main()
