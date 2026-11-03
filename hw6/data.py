import ipaddress

import pandas as pd
import psycopg
from psycopg.rows import dict_row

WORKLOAD_START = "2026-10-26T09:59:58.513468+00:00"
WORKLOAD_END = "2026-10-26T11:37:58.808425+00:00"


def load_data():
    query = """
        SELECT
            request_id,
            received_at,
            country,
            client_ip,
            gender,
            age_group,
            income_group,
            client_time,
            requested_file,
            status_code,
            is_banned
        FROM hw6.request_details
        WHERE received_at BETWEEN %s::timestamptz AND %s::timestamptz
        ORDER BY received_at, request_id
    """

    with psycopg.connect(
        row_factory=dict_row,
        connect_timeout=30,
        options="-c default_transaction_read_only=on -c statement_timeout=180000"
    ) as connection:
        rows = connection.execute(
            query,
            (WORKLOAD_START, WORKLOAD_END)
        ).fetchall()

    frame = pd.DataFrame(rows)

    if len(frame) != 100000:
        raise ValueError(f"Expected 100000 workload rows, found {len(frame)}")

    if frame["request_id"].duplicated().any():
        raise ValueError("Duplicate request IDs found")

    required = (
        "client_ip",
        "country",
        "gender",
        "age_group",
        "income_group",
        "client_time"
    )

    for column in required:
        if frame[column].isna().any():
            raise ValueError(f"Missing values in {column}")
        if frame[column].astype(str).str.strip().eq("").any():
            raise ValueError(f"Empty values in {column}")

    for value in frame["client_ip"].unique():
        ipaddress.IPv4Address(value)

    countries_per_ip = frame.groupby("client_ip")["country"].nunique()
    if countries_per_ip.gt(1).any():
        raise ValueError("An IP address maps to multiple countries")

    frame["request_id"] = frame["request_id"].astype(str)
    frame["client_time"] = pd.to_datetime(frame["client_time"])

    print(
        f"Loaded {len(frame)} requests, "
        f"{frame['client_ip'].nunique()} distinct IPs, "
        f"{frame['country'].nunique()} countries, "
        f"{frame['income_group'].nunique()} income categories.",
        flush=True
    )

    return frame
