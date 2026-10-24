import json
import threading
import urllib.error
import urllib.request

import pytest

from elevator_sim.app import server
from elevator_sim.app.trace import Q_EXAMPLE


@pytest.fixture
def base():
    httpd = server.make_server(0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def call(url, body=None, method=None, raw=None):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()


def test_it_binds_to_localhost_only():
    httpd = server.make_server(0)
    assert httpd.server_address[0] == "127.0.0.1"
    httpd.server_close()


def test_the_page_is_served(base):
    status, headers, body = call(base + "/")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert b"<title>" in body


def test_scenarios_lists_scenarios_schedulers_and_presets(base):
    status, _, body = call(base + "/api/scenarios")
    data = json.loads(body)
    assert status == 200
    assert "20f-4x10-demand100-up-peak" in [s["name"] for s in data["scenarios"]]
    assert data["schedulers"] == ["round-robin", "nearest-car", "lowest-cost", "lowest-cost-nocap", "zoned"]
    assert "Rush hour" in data["presets"]
    assert data["limits"]["floors"] == [2, 60]


def test_code_returns_the_core_views(base):
    status, _, body = call(base + "/api/code")
    views = json.loads(body)["views"]
    assert status == 200
    assert views["floors"]["file"] == "core/scheduler.py"
    assert views["floors"]["lines"][0].startswith("def floors_to_reach(")


def test_run_returns_one_trace_per_scheduler_on_the_same_passengers(base):
    body = {"requests": Q_EXAMPLE, "elevators": 2, "schedulers": ["nearest-car", "lowest-cost"]}
    status, _, raw = call(base + "/api/run", body)
    data = json.loads(raw)
    assert status == 200
    assert [t["scheduler"] for t in data["traces"]] == ["nearest-car", "lowest-cost"]
    picks = [next(a["pick"] for a in t["assignments"] if a["passenger"] == "Q") for t in data["traces"]]
    assert picks == [0, 1]


def test_run_takes_generated_parameters(base):
    body = {"floors": 10, "elevators": 2, "demand": 50, "pattern": "up-peak", "run_length": 40, "schedulers": ["zoned"]}
    status, _, raw = call(base + "/api/run", body)
    assert status == 200
    assert json.loads(raw)["traces"][0]["config"]["floors"] == 10


@pytest.mark.parametrize("body, message", [
    ({"floors": 500}, "floors"),
    ({"schedulers": ["fastest"]}, "fastest"),
    ({"requests": "time,id,source,dest\n0,a,1,1\n"}, "line 2"),
    ({"color": "red"}, "unknown parameter"),
    ([1, 2], "JSON object"),
])
def test_bad_input_returns_400_with_the_message(base, body, message):
    status, headers, raw = call(base + "/api/run", body)
    assert status == 400
    assert headers["Content-Type"].startswith("application/json")
    assert message in json.loads(raw)["error"]


def test_a_body_that_is_not_json_returns_400(base):
    status, _, raw = call(base + "/api/run", raw=b"{not json", method="POST")
    assert status == 400
    assert "JSON" in json.loads(raw)["error"]


def test_a_body_that_is_too_large_returns_413(base):
    status, _, raw = call(base + "/api/run", raw=b" " * (server.MAX_BODY + 1), method="POST")
    assert status == 413
    assert "bytes" in json.loads(raw)["error"]


def test_an_unknown_route_returns_404(base):
    assert call(base + "/api/nothing")[0] == 404
    assert call(base + "/api/scenarios", {}, method="POST")[0] == 404


# Request logging: off unless both the flag and the environment variable allow it


def test_logging_is_off_by_default(monkeypatch):
    monkeypatch.delenv(server.LOG_ENV, raising=False)
    assert not server.logging_allowed(False)
    assert not server.logging_allowed(True)


def test_logging_needs_both_the_flag_and_the_environment(monkeypatch):
    monkeypatch.setenv(server.LOG_ENV, "local")
    assert not server.logging_allowed(False)
    assert server.logging_allowed(True)
    monkeypatch.setenv(server.LOG_ENV, "production")
    assert not server.logging_allowed(True)


def test_a_default_server_writes_nothing_about_requests(base, capsys):
    call(base + "/api/run", {"requests": Q_EXAMPLE, "elevators": 2})
    call(base + "/api/run", {"floors": 500})
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_an_allowed_server_logs_the_route_but_never_the_body(monkeypatch, capsys):
    monkeypatch.setenv(server.LOG_ENV, "local")
    httpd = server.make_server(0, log_requests=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/api/run"
    call(url, {"requests": "time,id,source,dest\n0,body-marker,1,5\n", "elevators": 2})
    httpd.shutdown()
    httpd.server_close()
    err = capsys.readouterr().err
    assert "POST /api/run 200" in err
    assert "body-marker" not in err
