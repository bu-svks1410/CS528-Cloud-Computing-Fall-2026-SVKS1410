import json
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def main():
    results = Path("results")
    status = json.loads(
        (results / "hw5-load-results/status.json").read_text()
    )
    bounds = (status["started_at"], status["finished_at"])

    with psycopg.connect(row_factory=dict_row) as connection:
        requests = connection.execute(
            """
            SELECT *
            FROM requests
            WHERE received_at BETWEEN %s::timestamptz AND %s::timestamptz
            ORDER BY received_at
            """,
            bounds
        ).fetchall()

        errors = connection.execute(
            """
            SELECT *
            FROM request_errors
            WHERE request_time BETWEEN %s::timestamptz AND %s::timestamptz
            ORDER BY request_time
            """,
            bounds
        ).fetchall()

    for filename, rows in (
        ("load-requests.jsonl", requests),
        ("load-errors.jsonl", errors)
    ):
        with (results / filename).open("w") as output:
            for row in rows:
                output.write(json.dumps(row, default=str) + "\n")

    metrics = [
        json.loads(line)
        for line in (results / "load-metrics.jsonl").read_text().splitlines()
        if line.strip()
    ]
    database_ids = {str(row["request_id"]) for row in requests}
    timing_ids = {row["request_id"] for row in metrics}

    expected_errors = {
        (row["received_at"], row["requested_file"], row["status_code"])
        for row in requests
        if row["status_code"] != 200
    }
    actual_errors = {
        (row["request_time"], row["requested_file"], row["error_code"])
        for row in errors
    }

    if len(requests) != 100000 or len(database_ids) != 100000:
        raise SystemExit("Unexpected request count.")
    if database_ids != timing_ids:
        raise SystemExit("Database and timing request IDs differ.")
    if expected_errors != actual_errors:
        raise SystemExit("Error-table records do not match failed requests.")

    print(f"Exported request rows: {len(requests):,}")
    print(f"Exported error rows: {len(errors):,}")
    print("Database request IDs match timing request IDs.")
    print("Every failed request has the matching error-table record.")
    print("Results export and verification passed.")


if __name__ == "__main__":
    main()
