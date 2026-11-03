import json
import os
from pathlib import Path

import psycopg
from psycopg import sql


def require_zero(connection, name, query):
    count = connection.execute(query).fetchone()[0]
    if count != 0:
        raise RuntimeError(f"{name}: {count} conflicting or unmatched records")
    print(f"PASS: {name}", flush=True)


def main():
    directory = Path(__file__).resolve().parent

    with psycopg.connect(
        connect_timeout=15,
        options="-c statement_timeout=180000 -c lock_timeout=15000"
    ) as connection:
        connection.execute(
            "LOCK TABLE public.requests, public.request_errors IN SHARE MODE"
        )

        require_zero(
            connection,
            "Country determines banned status",
            """
            SELECT COUNT(*)
            FROM (
                SELECT country
                FROM (
                    SELECT DISTINCT country, is_banned
                    FROM public.requests
                ) AS combinations
                GROUP BY country
                HAVING COUNT(*) > 1
            ) AS conflicts
            """
        )

        require_zero(
            connection,
            "Client IP determines country, including missing values",
            """
            SELECT COUNT(*)
            FROM (
                SELECT client_ip
                FROM (
                    SELECT DISTINCT client_ip, country
                    FROM public.requests
                ) AS combinations
                GROUP BY client_ip
                HAVING COUNT(*) > 1
            ) AS conflicts
            """
        )

        require_zero(
            connection,
            "Each error matches exactly one request",
            """
            SELECT COUNT(*)
            FROM (
                SELECT e.request_time, e.requested_file, e.error_code
                FROM public.request_errors AS e
                LEFT JOIN public.requests AS r
                    ON r.received_at = e.request_time
                   AND r.requested_file = e.requested_file
                   AND r.status_code = e.error_code
                GROUP BY e.request_time, e.requested_file, e.error_code
                HAVING COUNT(r.request_id) <> 1
            ) AS mismatches
            """
        )

        for filename in ("schema.sql", "migration.sql"):
            connection.execute((directory / filename).read_text())
            print(f"Executed {filename}", flush=True)

        request_columns = """
            request_id, run_id, received_at, country, client_ip,
            gender, age_group, income_group, is_banned,
            client_time, requested_file, status_code
        """

        comparisons = (
            (
                "requests",
                "public.requests",
                "hw6.request_details",
                request_columns
            ),
            (
                "errors",
                "public.request_errors",
                "hw6.error_details",
                "request_time, requested_file, error_code"
            )
        )

        for label, original, migrated, columns in comparisons:
            require_zero(
                connection,
                f"All original {label} preserved",
                f"""
                SELECT COUNT(*)
                FROM (
                    SELECT {columns} FROM {original}
                    EXCEPT ALL
                    SELECT {columns} FROM {migrated}
                ) AS differences
                """
            )

            require_zero(
                connection,
                f"No extra or changed {label}",
                f"""
                SELECT COUNT(*)
                FROM (
                    SELECT {columns} FROM {migrated}
                    EXCEPT ALL
                    SELECT {columns} FROM {original}
                ) AS differences
                """
            )

        application_user = sql.Identifier(os.environ["SQL_USER"])

        connection.execute(
            sql.SQL("GRANT USAGE ON SCHEMA hw6 TO {}").format(
                application_user
            )
        )

        connection.execute(
            sql.SQL(
                "GRANT SELECT ON ALL TABLES IN SCHEMA hw6 TO {}"
            ).format(application_user)
        )

        counts = {}
        for table in ("countries", "clients", "requests", "request_errors"):
            counts[table] = connection.execute(
                sql.SQL("SELECT COUNT(*) FROM hw6.{}").format(
                    sql.Identifier(table)
                )
            ).fetchone()[0]

    print("Migration committed successfully.", flush=True)
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
