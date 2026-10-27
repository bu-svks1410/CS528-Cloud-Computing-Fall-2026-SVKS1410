import psycopg

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS requests (
        request_id UUID PRIMARY KEY,
        run_id TEXT NOT NULL,
        received_at TIMESTAMPTZ NOT NULL,
        country TEXT,
        client_ip TEXT,
        gender TEXT,
        age_group TEXT,
        income_group TEXT,
        is_banned BOOLEAN NOT NULL,
        client_time TIMESTAMP WITHOUT TIME ZONE,
        requested_file TEXT NOT NULL,
        status_code INTEGER NOT NULL
            CHECK (status_code BETWEEN 100 AND 599)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS request_errors (
        request_time TIMESTAMPTZ NOT NULL,
        requested_file TEXT NOT NULL,
        error_code INTEGER NOT NULL
            CHECK (error_code BETWEEN 100 AND 599 AND error_code <> 200),
        PRIMARY KEY (request_time, requested_file, error_code)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS requests_run_id_idx
    ON requests (run_id)
    """
]


def main():
    with psycopg.connect(connect_timeout=30) as connection:
        with connection.cursor() as cursor:
            for statement in STATEMENTS:
                cursor.execute(statement)
    print("Database tables and indexes are ready.")


if __name__ == "__main__":
    main()
