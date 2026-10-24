import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from elevator_sim.app import narration


@pytest.fixture
def fake_voice(monkeypatch):
    seen = []

    class Voice(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            seen.append(self.path)
            body = b"RIFFfake"
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Voice)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv(narration.VOICE_ENV, f"http://127.0.0.1:{httpd.server_address[1]}")
    yield seen
    httpd.shutdown()
    httpd.server_close()


def test_a_clip_comes_from_the_local_voice_server(fake_voice):
    body, kind = narration.clip("Elevator A picks p1.", speed=3)
    assert (body, kind) == (b"RIFFfake", "audio/wav")
    assert fake_voice[0].startswith("/tts?text=Elevator+A+picks+p1.&voice=af_heart&speed=2.0")


def test_the_voice_server_must_be_on_this_machine(monkeypatch):
    monkeypatch.setenv(narration.VOICE_ENV, "https://voice.example.com")
    with pytest.raises(ValueError, match="127.0.0.1"):
        narration.clip("hello")


@pytest.mark.parametrize("text, message", [("  ", "text required"), ("x" * 401, "limit")])
def test_bad_text_is_refused(text, message):
    with pytest.raises(ValueError, match=message):
        narration.clip(text)


def test_no_voice_server_is_an_os_error(monkeypatch):
    monkeypatch.setenv(narration.VOICE_ENV, "http://127.0.0.1:9")
    with pytest.raises(OSError):
        narration.clip("hello")
