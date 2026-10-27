import json
import os
import time

from database import close_connection, save_request
from http_core import Handler as BaseHandler
from http_core import Server, storage_client
from request_data import extract_request


class Handler(BaseHandler):
    server_version = "HW5HTTP/1.0"

    def measure(self, name, function, *args):
        started = time.perf_counter_ns()
        try:
            return function(*args)
        finally:
            self.timings[name] = (
                self.timings.get(name, 0)
                + time.perf_counter_ns() - started
            )

    def read_file(self, name):
        return self.measure("storage_ns", self.download_file, name)

    def download_file(self, name):
        blob = storage_client().bucket(
            os.environ["BUCKET_NAME"]
        ).blob(name)
        contents = blob.download_as_bytes(timeout=30)
        return contents, blob.content_type or "text/html"

    def requested_file(self):
        value = self.measure(
            "processing_ns", super().requested_file
        )
        if isinstance(value, str):
            self.record["requested_file"] = value
        return value

    def log_event(self, event, message, status, **details):
        try:
            super().log_event(event, message, status, **details)
        except Exception as error:
            print(json.dumps({
                "event": "cloud_logging_failed",
                "request_id": self.request_id,
                "error": str(error)
            }), flush=True)

    def reply(self, status, body, content_type="text/plain; charset=utf-8"):
        self.record["status_code"] = status
        self.response_status = status

        try:
            self.measure("database_ns", save_request, self.record)
            self.database_saved = True
        except Exception as error:
            self.response_status = 503
            status = 503
            body = "503 Database unavailable\n"
            content_type = "text/plain; charset=utf-8"
            print(json.dumps({
                "event": "database_write_failed",
                "request_id": self.request_id,
                "intended_status": self.record["status_code"],
                "error": str(error)
            }), flush=True)

        self.measure(
            "response_ns",
            self.send_reply,
            status,
            body,
            content_type
        )
        self.response_completed = True

    def send_reply(self, status, body, content_type):
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

    def dispatch(self):
        started = time.perf_counter_ns()
        self.timings = {}
        self.database_saved = False
        self.response_completed = False
        self.response_status = None
        self.record = self.measure(
            "processing_ns",
            extract_request,
            self.headers,
            self.path,
            os.environ.get("RUN_ID", "demonstration")
        )
        self.request_id = str(self.record["request_id"])

        try:
            self.serve()
        except (BrokenPipeError, ConnectionResetError, TimeoutError) as error:
            self.close_connection = True
            print(json.dumps({
                "event": "client_connection_error",
                "request_id": self.request_id,
                "error": str(error)
            }), flush=True)
        except Exception as error:
            self.close_connection = True
            print(json.dumps({
                "event": "unexpected_request_error",
                "request_id": self.request_id,
                "error": str(error)
            }), flush=True)
            if self.response_status is None:
                try:
                    self.reply(500, "500 Internal Server Error\n")
                except Exception as reply_error:
                    print(json.dumps({
                        "event": "error_response_failed",
                        "request_id": self.request_id,
                        "error": str(reply_error)
                    }), flush=True)
        finally:
            print(json.dumps({
                "event": "request_metrics",
                "request_id": self.request_id,
                "run_id": self.record["run_id"],
                "received_at": self.record["received_at"].isoformat(),
                "method": self.command,
                "requested_file": self.record["requested_file"],
                "status": self.response_status,
                "database_saved": self.database_saved,
                "response_completed": self.response_completed,
                "processing_ns": self.timings.get("processing_ns", 0),
                "storage_ns": self.timings.get("storage_ns"),
                "database_ns": self.timings.get("database_ns"),
                "response_ns": self.timings.get("response_ns"),
                "total_ns": time.perf_counter_ns() - started
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


def main():
    port = int(os.environ.get("PORT", "8080"))
    try:
        with Server(("0.0.0.0", port), Handler) as server:
            print(json.dumps({
                "event": "server_started",
                "port": port,
                "run_id": os.environ.get("RUN_ID", "demonstration"),
                "server_type": "HTTPServer",
                "concurrent_handlers": 1
            }), flush=True)
            server.serve_forever()
    finally:
        close_connection()


if __name__ == "__main__":
    main()
