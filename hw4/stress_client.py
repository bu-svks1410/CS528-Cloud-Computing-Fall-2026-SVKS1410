import argparse
import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def stop_process(process):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--clients", type=int, choices=range(1, 5), required=True)
    parser.add_argument("--duration", type=int, default=180)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--start-at", type=float, default=0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.duration <= 0 or args.timeout <= 0:
        parser.error("Duration and timeout must be positive")

    executable = Path.home() / "http-client"
    if not executable.is_file():
        parser.error(f"Missing client: {executable}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    time.sleep(max(0, args.start_at - time.time()))
    started_at = timestamp()
    started = time.monotonic()
    workers = []

    try:
        for index in range(args.clients):
            log_path = output.with_name(
                f"{output.stem}-client-{index + 1}.log"
            )
            command = [
                str(executable),
                "-d", args.host,
                "-b", "none",
                "-w", "data",
                "-n", "1000000",
                "-i", "11999",
                "-p", "8080",
                "-r", str(528 + index),
                "-t", str(args.timeout)
            ]
            with log_path.open("wb") as handle:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True
                )
            record = {
                "client": index + 1,
                "command": command,
                "launched_at": timestamp(),
                "exited_before_stop": False,
                "log_file": str(log_path)
            }
            workers.append((process, record, log_path))

        deadline = started + args.duration
        while time.monotonic() < deadline:
            for process, record, log_path in workers:
                if process.poll() is not None:
                    if not record["exited_before_stop"]:
                        record["exited_before_stop"] = True
                        record["exit_observed_at"] = timestamp()
            time.sleep(min(0.2, max(0, deadline - time.monotonic())))

    finally:
        stop_requested_at = timestamp()
        elapsed = time.monotonic() - started

        for process, record, log_path in workers:
            if process.poll() is not None:
                record["exited_before_stop"] = True
            record["stopped_by_runner"] = process.poll() is None
            stop_process(process)
            record["exit_code"] = process.returncode
            record["output_bytes"] = log_path.stat().st_size
            record["output_preview"] = log_path.read_text(
                errors="replace"
            )[:2000]

        result = {
            "clients": args.clients,
            "duration_seconds": args.duration,
            "client_timeout_seconds": args.timeout,
            "verbose": False,
            "started_at": started_at,
            "stop_requested_at": stop_requested_at,
            "elapsed_seconds": round(elapsed, 3),
            "client_results": [record for _, record, _ in workers]
        }
        output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
