import base64
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

import google.auth
import psycopg
from google.auth.transport.requests import AuthorizedSession


def main():
    directory = Path(__file__).resolve().parent
    os.chdir(directory)

    required = (
        "PROJECT_ID",
        "BUCKET_NAME",
        "SQL_CONNECTION",
        "SQL_DATABASE",
        "SQL_USER",
        "SQL_SECRET",
        "OUTPUT_PREFIX"
    )

    for name in required:
        if not os.environ.get(name):
            raise RuntimeError(f"Missing configuration: {name}")

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    project = quote(os.environ["PROJECT_ID"], safe="")
    secret = quote(os.environ["SQL_SECRET"], safe="")

    url = (
        "https://secretmanager.googleapis.com/v1/projects/"
        f"{project}/secrets/{secret}/versions/latest:access"
    )

    with AuthorizedSession(credentials) as session:
        response = session.get(url, timeout=60)
        response.raise_for_status()
        password = base64.b64decode(
            response.json()["payload"]["data"]
        ).decode("utf-8")

    environment = os.environ.copy()
    environment.update({
        "PGHOST": "127.0.0.1",
        "PGPORT": "5432",
        "PGDATABASE": os.environ["SQL_DATABASE"],
        "PGUSER": os.environ["SQL_USER"],
        "PGPASSWORD": password,
        "PGSSLMODE": "disable",
        "PGCONNECT_TIMEOUT": "5",
        "PYTHONUNBUFFERED": "1",
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "2",
        "MKL_NUM_THREADS": "2"
    })

    output = directory / "results"
    output.mkdir(exist_ok=True)

    with (output / "sql-proxy.log").open("w") as proxy_log:
        proxy = subprocess.Popen(
            [
                "/usr/local/bin/cloud-sql-proxy",
                "--address=127.0.0.1",
                "--port=5432",
                os.environ["SQL_CONNECTION"]
            ],
            stdin=subprocess.DEVNULL,
            stdout=proxy_log,
            stderr=subprocess.STDOUT
        )

        try:
            for attempt in range(60):
                if proxy.poll() is not None:
                    raise RuntimeError(
                        "SQL Auth Proxy exited. Check results/sql-proxy.log."
                    )

                try:
                    with psycopg.connect(
                        host=environment["PGHOST"],
                        port=environment["PGPORT"],
                        dbname=environment["PGDATABASE"],
                        user=environment["PGUSER"],
                        password=password,
                        sslmode="disable",
                        connect_timeout=5
                    ) as connection:
                        connection.execute("SELECT 1")
                    break
                except psycopg.OperationalError:
                    if attempt == 59:
                        raise RuntimeError(
                            "Database connection did not become ready."
                        ) from None
                    time.sleep(2)

            print("VM database connection verified.", flush=True)

            subprocess.run(
                [
                    sys.executable,
                    str(directory / "main.py"),
                    "--project", os.environ["PROJECT_ID"],
                    "--bucket", os.environ["BUCKET_NAME"],
                    "--prefix", os.environ["OUTPUT_PREFIX"],
                    "--output-directory", str(output)
                ],
                env=environment,
                check=True
            )
        finally:
            if proxy.poll() is None:
                proxy.terminate()
                try:
                    proxy.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proxy.kill()
                    proxy.wait()

    print("VM model execution completed successfully.", flush=True)


if __name__ == "__main__":
    main()
