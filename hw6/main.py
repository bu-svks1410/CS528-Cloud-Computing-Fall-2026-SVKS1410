import argparse
import json
import platform
import uuid
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from google.cloud import storage

from country_model import train_country
from data import WORKLOAD_END, WORKLOAD_START, load_data
from income_model import train_income


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", default="hw6")
    parser.add_argument("--output-directory", default="results")
    args = parser.parse_args()

    prefix = args.prefix.strip("/")
    if not prefix:
        parser.error("--prefix must not be empty")

    started = datetime.now(timezone.utc)
    run_id = (
        started.strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )

    output = Path(args.output_directory) / run_id
    output.mkdir(parents=True, exist_ok=False)

    bucket_prefix = f"{prefix}/runs/{run_id}"
    bucket_location = f"gs://{args.bucket}/{bucket_prefix}"

    print(f"Run ID: {run_id}", flush=True)
    print(f"Output location: {bucket_location}", flush=True)

    frame = load_data()

    country_metrics = train_country(frame, output)
    income_metrics = train_income(frame, output)

    metrics = {
        "run_id": run_id,
        "started_at": started.isoformat(),
        "training_finished_at": datetime.now(timezone.utc).isoformat(),
        "hostname": platform.node(),
        "python_version": platform.python_version(),
        "package_versions": {
            name: version(name)
            for name in (
                "pandas",
                "numpy",
                "scikit-learn",
                "psycopg",
                "google-cloud-storage"
            )
        },
        "source": {
            "database_view": "hw6.request_details",
            "workload_start": WORKLOAD_START,
            "workload_end": WORKLOAD_END,
            "rows": len(frame)
        },
        "bucket_location": bucket_location,
        "country": country_metrics,
        "income": income_metrics
    }

    (output / "metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n"
    )

    client = storage.Client(project=args.project)

    try:
        bucket = client.bucket(args.bucket)
        uploaded_files = []

        for path in sorted(output.iterdir()):
            object_name = f"{bucket_prefix}/{path.name}"

            content_type = {
                ".csv": "text/csv",
                ".json": "application/json",
                ".joblib": "application/octet-stream"
            }.get(path.suffix, "application/octet-stream")

            bucket.blob(object_name).upload_from_filename(
                str(path),
                content_type=content_type,
                if_generation_match=0,
                timeout=300
            )

            location = f"gs://{args.bucket}/{object_name}"
            uploaded_files.append(location)
            print(f"Uploaded: {location}", flush=True)

        completion = {
            "run_id": run_id,
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "bucket_location": bucket_location,
            "files": uploaded_files,
            "country_test_accuracy": country_metrics["test_accuracy"],
            "income_test_accuracy": income_metrics["test_accuracy"]
        }

        completion_text = json.dumps(completion, indent=2) + "\n"

        bucket.blob(f"{bucket_prefix}/completed.json").upload_from_string(
            completion_text,
            content_type="application/json",
            if_generation_match=0,
            timeout=120
        )

        (output / "completed.json").write_text(completion_text)
    finally:
        client.close()

    print(json.dumps(metrics, indent=2), flush=True)
    print("Both models finished and all output files were uploaded.", flush=True)


if __name__ == "__main__":
    main()
