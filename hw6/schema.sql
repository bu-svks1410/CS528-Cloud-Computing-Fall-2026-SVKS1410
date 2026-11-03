CREATE SCHEMA IF NOT EXISTS hw6;

CREATE TABLE IF NOT EXISTS hw6.countries (
    country_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    country TEXT,
    is_banned BOOLEAN NOT NULL,
    UNIQUE NULLS NOT DISTINCT (country)
);

CREATE TABLE IF NOT EXISTS hw6.clients (
    client_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_ip TEXT,
    country_id BIGINT NOT NULL REFERENCES hw6.countries(country_id),
    UNIQUE NULLS NOT DISTINCT (client_ip)
);

CREATE TABLE IF NOT EXISTS hw6.requests (
    request_id UUID PRIMARY KEY,
    run_id TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    client_id BIGINT NOT NULL REFERENCES hw6.clients(client_id),
    gender TEXT,
    age_group TEXT,
    income_group TEXT,
    client_time TIMESTAMP WITHOUT TIME ZONE,
    requested_file TEXT NOT NULL,
    status_code INTEGER NOT NULL
        CHECK (status_code BETWEEN 100 AND 599)
);

CREATE TABLE IF NOT EXISTS hw6.request_errors (
    request_id UUID PRIMARY KEY REFERENCES hw6.requests(request_id)
);

CREATE INDEX IF NOT EXISTS hw6_requests_received_at_idx
    ON hw6.requests (received_at);

CREATE INDEX IF NOT EXISTS hw6_requests_client_id_idx
    ON hw6.requests (client_id);

CREATE OR REPLACE VIEW hw6.request_details AS
SELECT
    r.request_id,
    r.run_id,
    r.received_at,
    c.country,
    i.client_ip,
    r.gender,
    r.age_group,
    r.income_group,
    c.is_banned,
    r.client_time,
    r.requested_file,
    r.status_code
FROM hw6.requests AS r
JOIN hw6.clients AS i ON i.client_id = r.client_id
JOIN hw6.countries AS c ON c.country_id = i.country_id;

CREATE OR REPLACE VIEW hw6.error_details AS
SELECT
    r.received_at AS request_time,
    r.requested_file,
    r.status_code AS error_code
FROM hw6.request_errors AS e
JOIN hw6.requests AS r ON r.request_id = e.request_id;
