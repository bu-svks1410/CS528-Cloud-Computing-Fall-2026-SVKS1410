import json
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from google.api_core.exceptions import NotFound
from google.cloud import logging as cloud_logging
from google.cloud import pubsub_v1, storage


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


def country_name(value):
    value = " ".join(value.strip().casefold().replace("_", " ").split())
    return COUNTRY_ALIASES.get(value, value)


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


@lru_cache(maxsize=1)
def storage_client():
    return storage.Client(project=os.environ["PROJECT_ID"])


@lru_cache(maxsize=1)
def publisher_client():
    return pubsub_v1.PublisherClient()


@lru_cache(maxsize=1)
def cloud_logger():
    client = cloud_logging.Client(project=os.environ["PROJECT_ID"])
    return client.logger("hw4-web-server")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "HW4HTTP/1.0"
    sys_version = ""
    timeout = 30

    def log_message(self, format, *args):
        return

    def log_event(self, event, message, status, **details):
        severity = {404: "WARNING", 400: "CRITICAL"}.get(status, "ERROR")
        record = {
            "event": event,
            "message": message,
            "status": status,
            "method": self.command,
            "path": self.path,
            "request_id": self.request_id,
            **details
        }
        print(json.dumps({**record, "severity": severity}), flush=True)
        cloud_logger().log_struct(record, severity=severity)

    def reply(self, status, body, content_type="text/plain; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Request-ID", self.request_id)
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
            self.wfile.flush()
        print(json.dumps({
            "event": "http_response",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": self.request_id,
            "method": self.command,
            "status": status,
            "body_bytes": 0 if self.command == "HEAD" else len(body)
        }), flush=True)

    def requested_file(self):
        if self.command == "GET":
            return unquote(urlsplit(self.path).path).lstrip("/")
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Transfer-Encoding is not supported")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Invalid Content-Length") from None
        if not 0 <= length <= 65536:
            raise ValueError("POST payload must be at most 65536 bytes")
        body = self.rfile.read(length)
        if len(body) != length:
            raise ValueError("Incomplete POST payload")
        text = body.decode("utf-8")
        content_type = self.headers.get_content_type()
        if content_type == "application/json":
            payload = json.loads(text)
            return payload.get("file") if isinstance(payload, dict) else None
        if content_type == "application/x-www-form-urlencoded":
            return parse_qs(text).get("file", [None])[0]
        return text.strip()

    def serve(self):
        if self.command not in ("GET", "POST"):
            self.log_event(
                "unsupported_method", "HTTP method is not implemented", 501
            )
            self.reply(501, "501 Not Implemented\n")
            return

        country = country_name(self.headers.get("X-country", ""))
        if country in FORBIDDEN_COUNTRIES:
            event = {
                "event": "forbidden_request",
                "request_id": self.request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "country": country,
                "method": self.command,
                "path": self.path,
                "status": 400,
                "message": f"Permission denied: request from forbidden country {country}"
            }
            self.log_event(
                "forbidden_request", event["message"], 400, country=country
            )
            try:
                publisher = publisher_client()
                topic = publisher.topic_path(
                    os.environ["PROJECT_ID"], os.environ["TOPIC_ID"]
                )
                publisher.publish(
                    topic, json.dumps(event).encode("utf-8")
                ).result(timeout=30)
            except Exception as error:
                self.log_event(
                    "publish_failed", "Could not publish notification",
                    503, error=str(error)
                )
                self.reply(503, "503 Notification service unavailable\n")
                return
            self.reply(400, "400 Permission denied: forbidden country\n")
            return

        bucket = os.environ["BUCKET_NAME"]
        try:
            name = object_name(self.requested_file(), bucket)
        except (ValueError, UnicodeError) as error:
            self.log_event("invalid_request", str(error), 400)
            self.reply(400, "400 Invalid request\n")
            return

        if name is None:
            self.log_event("file_not_found", "No matching file in data/", 404)
            self.reply(404, "404 Not Found\n")
            return

        try:
            blob = storage_client().bucket(bucket).blob(name)
            contents = blob.download_as_bytes(timeout=30)
        except NotFound:
            self.log_event(
                "file_not_found", "Requested file does not exist",
                404, object=name
            )
            self.reply(404, "404 Not Found\n")
            return
        except Exception as error:
            self.log_event(
                "storage_failed", "Could not read storage object",
                503, object=name, error=str(error)
            )
            self.reply(503, "503 Storage unavailable\n")
            return

        self.reply(200, contents, blob.content_type or "text/html")

    def dispatch(self):
        self.request_id = str(uuid.uuid4())
        try:
            self.serve()
        except (BrokenPipeError, ConnectionResetError, TimeoutError) as error:
            self.close_connection = True
            print(json.dumps({
                "event": "client_connection_error",
                "request_id": self.request_id,
                "error": str(error)
            }), flush=True)

    do_GET = dispatch
    do_POST = dispatch
    do_PUT = dispatch
    do_DELETE = dispatch
    do_HEAD = dispatch
    do_CONNECT = dispatch
    do_OPTIONS = dispatch
    do_TRACE = dispatch
    do_PATCH = dispatch


class Server(HTTPServer):
    request_queue_size = 5
    allow_reuse_address = True


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    with Server(("0.0.0.0", port), Handler) as server:
        print(json.dumps({
            "event": "server_started",
            "port": port,
            "request_queue_size": server.request_queue_size,
            "server_type": "HTTPServer",
            "concurrent_handlers": 1
        }), flush=True)
        server.serve_forever()
