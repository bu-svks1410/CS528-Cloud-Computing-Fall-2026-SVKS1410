import threading
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlsplit

FORBIDDEN_COUNTRIES = {
    "north korea", "iran", "cuba", "myanmar", "iraq",
    "libya", "sudan", "zimbabwe", "syria"
}

COUNTRY_ALIASES = {
    "kp": "north korea", "prk": "north korea", "dprk": "north korea",
    "ir": "iran", "irn": "iran", "cu": "cuba", "cub": "cuba",
    "mm": "myanmar", "mmr": "myanmar", "burma": "myanmar",
    "iq": "iraq", "irq": "iraq", "ly": "libya", "lby": "libya",
    "sd": "sudan", "sdn": "sudan", "zw": "zimbabwe",
    "zwe": "zimbabwe", "sy": "syria", "syr": "syria"
}

_timestamp_lock = threading.Lock()
_last_timestamp = None


def country_name(value):
    value = " ".join(
        value.strip().casefold().replace("_", " ").split()
    )
    return COUNTRY_ALIASES.get(value, value)


def receipt_time():
    global _last_timestamp
    with _timestamp_lock:
        current = datetime.now(timezone.utc)
        if _last_timestamp is not None and current <= _last_timestamp:
            current = _last_timestamp + timedelta(microseconds=1)
        _last_timestamp = current
        return current


def extract_request(headers, path, run_id):
    country = country_name(headers.get("X-country", ""))
    time_text = headers.get("X-time", "").strip()
    client_time = None
    if time_text:
        try:
            client_time = datetime.strptime(
                time_text, "%Y-%m-%d %H:%M:%S"
            )
        except ValueError:
            pass

    return {
        "request_id": uuid.uuid4(),
        "run_id": run_id,
        "received_at": receipt_time(),
        "country": country or None,
        "client_ip": headers.get("X-client-IP", "").strip() or None,
        "gender": headers.get("X-gender", "").strip() or None,
        "age_group": headers.get("X-age", "").strip() or None,
        "income_group": headers.get("X-income", "").strip() or None,
        "is_banned": country in FORBIDDEN_COUNTRIES,
        "client_time": client_time,
        "requested_file": unquote(urlsplit(path).path),
        "status_code": None
    }
