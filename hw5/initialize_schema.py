import os

import psycopg
from psycopg import sql

import setup_schema


def main():
    with psycopg.connect(connect_timeout=15) as connection:
        row = connection.execute(
            """
            SELECT
                to_regclass('public.requests'),
                to_regclass('public.request_errors')
            """
        ).fetchone()

    if all(value is not None for value in row):
        print("Both tables already exist. Existing data is preserved.")
    else:
        setup_schema.main()

    application_user = sql.Identifier(os.environ["SQL_USER"])

    with psycopg.connect(connect_timeout=15) as connection:
        connection.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                application_user
            )
        )
        connection.execute(
            sql.SQL(
                "GRANT SELECT, INSERT ON TABLE "
                "public.requests, public.request_errors TO {}"
            ).format(application_user)
        )
        rows = connection.execute(
            """
            SELECT table_name, constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'public'
              AND table_name IN ('requests', 'request_errors')
              AND constraint_type = 'PRIMARY KEY'
            ORDER BY table_name
            """
        ).fetchall()

        if len(rows) != 2:
            raise RuntimeError("Both tables must have a primary key.")

    for table_name, constraint_name in rows:
        print(f"{table_name}: primary key {constraint_name}")
    print("Schema initialization and application grants completed.")


if __name__ == "__main__":
    main()
