import json
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache

import functions_framework
from flask import Response
from google.api_core.exceptions import NotFound
from google.cloud import pubsub_v1, storage


FORBIDDEN_COUNTRIES = {
    "north korea", "iran", "cuba", "myanmar", "iraq", "libya", "sudan",
    "zimbabwe", "syria",
}
COUNTRY_ALIASES = {
    "kp": "north korea", "prk": "north korea", "dprk": "north korea",
    "ir": "iran", "irn": "iran", "cu": "cuba", "cub": "cuba",
    "mm": "myanmar", "mmr": "myanmar", "burma": "myanmar",
    "iq": "iraq", "irq": "iraq", "ly": "libya", "lby": "libya",
    "sd": "sudan", "sdn": "sudan", "zw": "zimbabwe", "zwe": "zimbabwe",
    "sy": "syria", "syr": "syria",
}


def country_name(value):
    value = " ".join(value.strip().casefold().replace("_", " ").split())
    return COUNTRY_ALIASES.get(value, value)


@lru_cache(maxsize=1)
def storage_client():

    return storage.Client(project=os.environ["PROJECT_ID"])


@lru_cache(maxsize=1)
def publisher_client():
    return pubsub_v1.PublisherClient()


def log_error(event, message, status, request, request_id, **details):
    record = {
        "severity": "ERROR", "event": event, "message": message,
        "status": status, "method": request.method, "path": request.path,
        "request_id": request_id, **details,
    }
    print(json.dumps(record, ensure_ascii=True), flush=True)
    print(f"ERROR {event}: {message} status={status} request_id={request_id}",
          flush=True)


def reply(body, status, request_id, content_type="text/plain; charset=utf-8"):
    return Response(body, status=status, content_type=content_type, headers={
        "Cache-Control": "no-store", "X-Request-ID": request_id,
    })


def requested_file(request):
    if request.method == "GET":
        return request.path.lstrip("/")
    if request.is_json:
        payload = request.get_json(silent=True)
        return payload.get("file") if isinstance(payload, dict) else None
    if request.mimetype in ("application/x-www-form-urlencoded", "multipart/form-data"):
        return request.form.get("file")
    return request.get_data(as_text=True).strip()


def object_name(value, bucket):
    if not isinstance(value, str) or not value.strip():
        return None
    name = value.strip().lstrip("/")
    if name.startswith(bucket + "/"):
        name = name[len(bucket) + 1:]
    if "/" not in name:
        name = "data/" + name
    if not name.startswith("data/"):
        return None
    if any(part in ("", ".", "..") for part in name.split("/")):
        return None
    if "\\" in name or "\x00" in name:
        return None
    return name


@functions_framework.http
def serve_file(request):
    request_id = str(uuid.uuid4())


    if request.method not in ("GET", "POST"):
        log_error("unsupported_method", "HTTP method is not implemented", 501,
                  request, request_id)
        return reply("501 Not Implemented\n", 501, request_id)

    country = country_name(request.headers.get("X-country", ""))
    if country in FORBIDDEN_COUNTRIES:
        event = {
            "event": "forbidden_request", "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "country": country, "method": request.method, "path": request.path,
            "status": 400,
            "message": f"Permission denied: request from forbidden country {country}",
        }
        log_error("forbidden_request", event["message"], 400, request, request_id,
                  country=country)
        try:
            publisher = publisher_client()
            topic = publisher.topic_path(os.environ["PROJECT_ID"], os.environ["TOPIC_ID"])

            publisher.publish(topic, json.dumps(event).encode("utf-8")).result(timeout=30)
        except Exception as exc:
            log_error("publish_failed", "Could not publish forbidden request", 503,
                      request, request_id, error=str(exc))
            return reply("503 Notification service unavailable; retry later\n", 503,
                         request_id)
        return reply("400 Permission denied: forbidden country\n", 400, request_id)

    bucket = os.environ["BUCKET_NAME"]
    name = object_name(requested_file(request), bucket)
    if name is None:
        log_error("file_not_found", "No matching file in data/", 404, request, request_id)
        return reply("404 Not Found\n", 404, request_id)
    try:
        blob = storage_client().bucket(bucket).blob(name)
        contents = blob.download_as_bytes(timeout=30)
    except NotFound:
        log_error("file_not_found", "Requested file does not exist", 404,
                  request, request_id, object=name)
        return reply("404 Not Found\n", 404, request_id)
    except Exception as exc:
        log_error("storage_failed", "Could not read storage object", 503,
                  request, request_id, object=name, error=str(exc))
        return reply("503 Storage unavailable; retry later\n", 503, request_id)
    return reply(contents, 200, request_id,
                 blob.content_type or "text/html; charset=utf-8")
