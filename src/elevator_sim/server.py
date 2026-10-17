"""The live page's server: standard library only, bound to 127.0.0.1, running simulations on demand."""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .scenarios import scenarios
from .scheduler import NAMES
from .trace import DEFAULTS, LIMITS, MAX_PASSENGERS, MAX_SCHEDULERS, MAX_TIME_UNITS, PRESETS, trace_runs
from .traffic import PATTERNS

HOST = "127.0.0.1"
PAGE = Path(__file__).parent / "ui" / "index.html"
MAX_BODY = 200_000
LOG_ENV = "ELEVATOR_SIM_LOG"
LOG_ALLOWED = ("local", "dev", "test")
RUNS_AT_ONCE = 2


def logging_allowed(flag: bool) -> bool:
    """Request logging needs both the --log-requests flag and an allowed ELEVATOR_SIM_LOG value."""
    return flag and os.environ.get(LOG_ENV, "") in LOG_ALLOWED


def catalog() -> dict:
    """What GET /api/scenarios returns: scenarios, schedulers, presets, patterns and the parameter limits."""
    listed = [{"name": s.name, "floors": s.config.floors, "elevators": s.config.elevators, "capacity": s.config.capacity}
              for s in scenarios().values()]
    return {"scenarios": listed, "schedulers": list(NAMES), "presets": PRESETS, "patterns": list(PATTERNS),
            "defaults": DEFAULTS, "limits": {k: list(v) for k, v in LIMITS.items()},
            "max_schedulers": MAX_SCHEDULERS, "max_passengers": MAX_PASSENGERS, "max_time_units": MAX_TIME_UNITS}


class Handler(BaseHTTPRequestHandler):
    server_version = "elevator-sim"
    log_requests = False
    runs = threading.BoundedSemaphore(RUNS_AT_ONCE)

    def log_message(self, format: str, *args) -> None:
        """Silent; send() writes one line with no request content when logging is allowed."""

    def send(self, status: int, body: bytes, content_type: str) -> None:
        """Write the response, and the method, route and status if logging is allowed."""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        if logging_allowed(self.log_requests):
            route = self.path.split("?", 1)[0]
            print(f"{self.command} {route} {status}", file=sys.stderr)

    def send_json(self, status: int, data: dict) -> None:
        self.send(status, json.dumps(data, separators=(",", ":"), allow_nan=False).encode(), "application/json")

    def do_GET(self) -> None:
        route = self.path.split("?", 1)[0]
        if route in ("/", "/index.html"):
            self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif route == "/api/scenarios":
            self.send_json(200, catalog())
        else:
            self.send_json(404, {"error": f"no route {route}"})

    def do_POST(self) -> None:
        route = self.path.split("?", 1)[0]
        if route != "/api/run":
            self.send_json(404, {"error": f"no route {route}"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self.send_json(413, {"error": f"the body is {length} bytes; the limit is {MAX_BODY}"})
            return
        try:
            params = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self.send_json(400, {"error": "the body must be JSON"})
            return
        if not self.runs.acquire(blocking=False):
            self.send_json(429, {"error": f"{RUNS_AT_ONCE} runs are already going; try again when one ends"})
            return
        try:
            self.send_json(200, trace_runs(params))
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        finally:
            self.runs.release()


def make_server(port: int, log_requests: bool = False) -> ThreadingHTTPServer:
    """A server on 127.0.0.1 at the port (0 picks a free one), not yet serving."""
    handler = type("LiveHandler", (Handler,), {"log_requests": log_requests})
    return ThreadingHTTPServer((HOST, port), handler)


def serve(port: int, log_requests: bool = False) -> None:
    """Serve until interrupted."""
    httpd = make_server(port, log_requests)
    print(f"Serving the live page at http://{HOST}:{httpd.server_address[1]}/ (Ctrl+C stops it)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
