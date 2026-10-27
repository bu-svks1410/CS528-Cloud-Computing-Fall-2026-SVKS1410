import json

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


def main():
    with psycopg.connect(row_factory=dict_row) as connection:
        for table, time_column in (
            ("requests", "received_at"),
            ("request_errors", "request_time")
        ):
            count = connection.execute(
                sql.SQL("SELECT COUNT(*) AS total FROM {}").format(
                    sql.Identifier(table)
                )
            ).fetchone()["total"]

            rows = connection.execute(
                sql.SQL(
                    "SELECT * FROM {} ORDER BY {} DESC LIMIT 10"
                ).format(
                    sql.Identifier(table),
                    sql.Identifier(time_column)
                )
            ).fetchall()

            print(json.dumps({
                "table": table,
                "total_rows": count,
                "latest_rows": rows
            }, indent=2, default=str))


if __name__ == "__main__":
    main()
