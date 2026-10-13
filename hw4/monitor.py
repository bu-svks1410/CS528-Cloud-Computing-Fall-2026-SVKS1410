import argparse
import csv
import time
from datetime import datetime, timezone
from pathlib import Path


def snapshot():
    cpu = [
        int(value)
        for value in Path("/proc/stat").read_text().splitlines()[0].split()[1:9]
    ]

    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        memory[key] = int(value.split()[0])

    received = 0
    sent = 0
    for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
        interface, values = line.split(":", 1)
        if interface.strip() == "lo":
            continue
        fields = values.split()
        received += int(fields[0])
        sent += int(fields[8])

    return cpu, memory, received, sent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=210)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.duration <= 0:
        parser.error("--duration must be positive")

    previous = snapshot()
    started = time.monotonic()
    previous_time = started

    with open(args.output, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "timestamp_utc", "elapsed_seconds", "cpu_busy_percent",
            "cpu_steal_percent", "memory_used_mib", "memory_used_percent",
            "network_rx_mbps", "network_tx_mbps"
        ])

        for sample in range(1, args.duration + 1):
            time.sleep(max(0, started + sample - time.monotonic()))
            current = snapshot()
            now = time.monotonic()
            interval = now - previous_time

            differences = [
                current[0][index] - previous[0][index]
                for index in range(8)
            ]
            total = sum(differences)
            busy = sum(differences[index] for index in (0, 1, 2, 5, 6))
            memory = current[1]
            used = memory["MemTotal"] - memory["MemAvailable"]

            writer.writerow([
                datetime.now(timezone.utc).isoformat(),
                round(now - started, 3),
                round(100 * busy / total, 3) if total else 0,
                round(100 * differences[7] / total, 3) if total else 0,
                round(used / 1024, 3),
                round(100 * used / memory["MemTotal"], 3),
                round((current[2] - previous[2]) * 8 / interval / 1000000, 6),
                round((current[3] - previous[3]) * 8 / interval / 1000000, 6)
            ])
            handle.flush()
            previous = current
            previous_time = now

    print(f"Saved {args.output}", flush=True)


if __name__ == "__main__":
    main()
