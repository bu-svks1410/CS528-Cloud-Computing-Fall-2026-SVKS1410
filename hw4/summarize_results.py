import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean


root = Path(__file__).resolve().parent / "results/httpserver/stress"
summaries = []

fields = [
    "cpu_busy_percent",
    "cpu_steal_percent",
    "memory_used_mib",
    "memory_used_percent",
    "network_rx_mbps",
    "network_tx_mbps"
]

for clients in range(1, 5):
    run = json.loads((root / f"stress-{clients}.json").read_text())
    start = datetime.fromisoformat(run["started_at"])
    end = datetime.fromisoformat(run["stop_requested_at"])

    with (root / f"metrics-{clients}.csv").open() as handle:
        rows = list(csv.DictReader(handle))

    times = [
        datetime.fromisoformat(row["timestamp_utc"])
        for row in rows
    ]
    assert times and times[0] <= start and times[-1] >= end, (
        f"Run {clients}: incomplete monitoring coverage"
    )

    samples = [
        row for row, timestamp in zip(rows, times)
        if start <= timestamp <= end
    ]
    assert samples, f"Run {clients}: no measurements"

    text = (root / f"server-{clients}.jsonl").read_text()
    assert text.strip(), f"Run {clients}: empty server log"
    assert "suppressed" not in text.lower(), (
        f"Run {clients}: inspect possible journal suppression"
    )

    responses = []
    for line in text.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        if record.get("event") == "http_response":
            timestamp = datetime.fromisoformat(record["timestamp"])
            if start <= timestamp <= end:
                responses.append(record)

    assert responses, f"Run {clients}: no response records"
    counts = Counter(str(record["status"]) for record in responses)

    summary = {
        "clients": clients,
        "duration_seconds": run["elapsed_seconds"],
        "samples": len(samples),
        "responses": len(responses),
        "http_200": counts.get("200", 0),
        "http_400": counts.get("400", 0),
        "unexpected_http_responses": sum(
            count for status, count in counts.items()
            if status not in {"200", "400"}
        ),
        "responses_per_second": round(
            len(responses) / run["elapsed_seconds"], 3
        ),
        "early_client_exits": sum(
            item["exited_before_stop"] for item in run["client_results"]
        ),
        "client_output_bytes": sum(
            item["output_bytes"] for item in run["client_results"]
        )
    }

    for field in fields:
        values = [float(row[field]) for row in samples]
        summary[f"{field}_average"] = round(mean(values), 3)
        summary[f"{field}_peak"] = round(max(values), 3)

    summaries.append(summary)
    print(json.dumps(summary, indent=2))

with (root / "stress-summary.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
    writer.writeheader()
    writer.writerows(summaries)

(root / "stress-summary.json").write_text(
    json.dumps(summaries, indent=2) + "\n"
)

print("Verified all four monitoring windows and saved summaries.")
