INSERT INTO hw6.countries (country, is_banned)
SELECT DISTINCT country, is_banned
FROM public.requests
ON CONFLICT (country) DO NOTHING;

ANALYZE hw6.countries;

INSERT INTO hw6.clients (client_ip, country_id)
SELECT DISTINCT r.client_ip, c.country_id
FROM public.requests AS r
JOIN hw6.countries AS c ON c.country = r.country
UNION ALL
SELECT DISTINCT r.client_ip, c.country_id
FROM public.requests AS r
CROSS JOIN hw6.countries AS c
WHERE r.country IS NULL AND c.country IS NULL
ON CONFLICT (client_ip) DO NOTHING;

ANALYZE hw6.clients;

WITH matched_requests AS (
    SELECT r.*, i.client_id
    FROM public.requests AS r
    JOIN hw6.clients AS i ON i.client_ip = r.client_ip
    UNION ALL
    SELECT r.*, i.client_id
    FROM public.requests AS r
    CROSS JOIN hw6.clients AS i
    WHERE r.client_ip IS NULL AND i.client_ip IS NULL
)
INSERT INTO hw6.requests (
    request_id,
    run_id,
    received_at,
    client_id,
    gender,
    age_group,
    income_group,
    client_time,
    requested_file,
    status_code
)
SELECT
    request_id,
    run_id,
    received_at,
    client_id,
    gender,
    age_group,
    income_group,
    client_time,
    requested_file,
    status_code
FROM matched_requests
WHERE TRUE
ON CONFLICT (request_id) DO NOTHING;

ANALYZE hw6.requests;

INSERT INTO hw6.request_errors (request_id)
SELECT r.request_id
FROM public.request_errors AS e
JOIN hw6.requests AS r
    ON r.received_at = e.request_time
   AND r.requested_file = e.requested_file
   AND r.status_code = e.error_code
ON CONFLICT (request_id) DO NOTHING;

ANALYZE hw6.request_errors;
