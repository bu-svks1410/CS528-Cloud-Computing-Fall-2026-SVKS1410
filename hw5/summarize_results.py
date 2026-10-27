import json
import math
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path


def read_rows(path):
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def ranked_counts(rows, field):
    counts = Counter(row[field] for row in rows)
    return [
        {"value": value, "count": count}
        for value, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], str(item[0]))
        )
    ]


def timing_summary(rows, field):
    values = sorted(
        row[field] / 1_000_000
        for row in rows
        if row.get(field) is not None
    )
    if not values:
        return {"samples": 0}
    return {
        "samples": len(values),
        "mean_ms": statistics.mean(values),
        "median_ms": statistics.median(values),
        "min_ms": values[0],
        "max_ms": values[-1],
        "p95_ms": values[math.ceil(len(values) * 0.95) - 1]
    }


def main():
    results = Path("results")
    requests = read_rows(results / "load-requests.jsonl")
    metrics = read_rows(results / "load-metrics.jsonl")
    status = json.loads(
        (results / "hw5-load-results/status.json").read_text()
    )

    elapsed = (
        datetime.fromisoformat(status["finished_at"])
        - datetime.fromisoformat(status["started_at"])
    ).total_seconds()

    successful = sum(row["status_code"] == 200 for row in requests)
    ages = ranked_counts(requests, "age_group")
    incomes = ranked_counts(requests, "income_group")

    summary = {
        "total_requests": len(requests),
        "successful_requests": successful,
        "failed_requests": len(requests) - successful,
        "banned_requests": sum(row["is_banned"] for row in requests),
        "status_counts": ranked_counts(requests, "status_code"),
        "gender_counts": ranked_counts(requests, "gender"),
        "top_five_countries": ranked_counts(requests, "country")[:5],
        "age_group_counts": ages,
        "most_common_age_groups": [
            row for row in ages if row["count"] == ages[0]["count"]
        ],
        "income_group_counts": incomes,
        "most_common_income_groups": [
            row for row in incomes if row["count"] == incomes[0]["count"]
        ],
        "runner_elapsed_seconds": elapsed,
        "average_requests_per_second": len(requests) / elapsed,
        "timings": {}
    }

    for label, rows in (
        ("all_requests", metrics),
        ("successful_requests", [r for r in metrics if r["status"] == 200]),
        ("failed_requests", [r for r in metrics if r["status"] != 200])
    ):
        summary["timings"][label] = {
            field: timing_summary(rows, field)
            for field in (
                "processing_ns",
                "storage_ns",
                "database_ns",
                "response_ns",
                "total_ns"
            )
        }

    text = json.dumps(summary, indent=2)
    (results / "summary.json").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
