import json

import psycopg
from psycopg.rows import dict_row

queries = {
    "columns": """
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name IN ('requests', 'request_errors')
        ORDER BY table_name, ordinal_position
    """,
    "request_totals": """
        SELECT COUNT(*) AS total_requests,
               COUNT(DISTINCT request_id) AS unique_request_ids,
               COUNT(DISTINCT client_ip) AS unique_ips,
               COUNT(DISTINCT country) AS unique_countries,
               MIN(received_at) AS first_received,
               MAX(received_at) AS last_received
        FROM public.requests
    """,
    "error_totals": """
        SELECT COUNT(*) AS total_errors
        FROM public.request_errors
    """,
    "missing_model_fields": """
        SELECT
            COUNT(*) FILTER (
                WHERE client_ip IS NULL OR BTRIM(client_ip) = ''
            ) AS missing_ip,
            COUNT(*) FILTER (
                WHERE country IS NULL OR BTRIM(country) = ''
            ) AS missing_country,
            COUNT(*) FILTER (
                WHERE gender IS NULL OR BTRIM(gender) = ''
            ) AS missing_gender,
            COUNT(*) FILTER (
                WHERE age_group IS NULL OR BTRIM(age_group) = ''
            ) AS missing_age,
            COUNT(*) FILTER (
                WHERE income_group IS NULL OR BTRIM(income_group) = ''
            ) AS missing_income,
            COUNT(*) FILTER (
                WHERE client_time IS NULL
            ) AS missing_client_time
        FROM public.requests
    """,
    "ip_country_conflicts": """
        SELECT COUNT(*) AS conflicting_ips
        FROM (
            SELECT client_ip
            FROM public.requests
            WHERE client_ip IS NOT NULL
              AND BTRIM(client_ip) <> ''
              AND country IS NOT NULL
            GROUP BY client_ip
            HAVING COUNT(DISTINCT country) > 1
        ) AS conflicts
    """,
    "country_banned_conflicts": """
        SELECT COUNT(*) AS conflicting_countries
        FROM (
            SELECT country
            FROM public.requests
            WHERE country IS NOT NULL
            GROUP BY country
            HAVING COUNT(DISTINCT is_banned) > 1
        ) AS conflicts
    """,
    "income_counts": """
        SELECT income_group, COUNT(*) AS requests
        FROM public.requests
        GROUP BY income_group
        ORDER BY income_group
    """,
    "run_counts": """
        SELECT run_id, COUNT(*) AS requests
        FROM public.requests
        GROUP BY run_id
        ORDER BY run_id
    """
}

with psycopg.connect(
    row_factory=dict_row,
    options="-c default_transaction_read_only=on -c statement_timeout=60000"
) as connection:
    results = {
        name: connection.execute(query).fetchall()
        for name, query in queries.items()
    }

print(json.dumps(results, indent=2, default=str))
