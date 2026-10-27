import threading

import psycopg

_local = threading.local()


def get_connection():
    connection = getattr(_local, "connection", None)
    if connection is None or connection.closed:
        connection = psycopg.connect(
            connect_timeout=15,
            autocommit=True,
            application_name="hw5-web-server",
            options="-c statement_timeout=15000 -c timezone=UTC"
        )
        _local.connection = connection
    return connection


def save_request(record):
    connection = get_connection()
    try:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO requests (
                        request_id, run_id, received_at, country,
                        client_ip, gender, age_group, income_group,
                        is_banned, client_time, requested_file, status_code
                    )
                    VALUES (
                        %(request_id)s, %(run_id)s, %(received_at)s,
                        %(country)s, %(client_ip)s, %(gender)s,
                        %(age_group)s, %(income_group)s, %(is_banned)s,
                        %(client_time)s, %(requested_file)s, %(status_code)s
                    )
                    """,
                    record
                )
                if record["status_code"] != 200:
                    cursor.execute(
                        """
                        INSERT INTO request_errors (
                            request_time, requested_file, error_code
                        )
                        VALUES (%s, %s, %s)
                        """,
                        (
                            record["received_at"],
                            record["requested_file"],
                            record["status_code"]
                        )
                    )
    except Exception:
        close_connection()
        raise


def close_connection():
    connection = getattr(_local, "connection", None)
    try:
        if connection is not None:
            connection.close()
    finally:
        _local.connection = None
