"""Spoken narration for the live page: a clip from a local Kokoro server (reel serve), passed through by this server."""

from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request

VOICE_ENV = "ELEVATOR_SIM_VOICE_URL"
DEFAULT_VOICE_URL = "http://127.0.0.1:8350"
MAX_TEXT = 400


def voice_url() -> str:
    """The narration server's base URL; it must be on this machine, so text never leaves it."""
    url = os.environ.get(VOICE_ENV, DEFAULT_VOICE_URL).rstrip("/")
    host = urllib.parse.urlsplit(url).hostname
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError(f"{VOICE_ENV} must point at 127.0.0.1 or localhost, got {host!r}")
    return url


def clip(text: str, voice: str = "af_heart", speed: float = 1.0) -> tuple[bytes, str]:
    """The spoken clip and its content type; ValueError for bad input, OSError when no narration server answers."""
    text = text.strip()
    if not text:
        raise ValueError("text required")
    if len(text) > MAX_TEXT:
        raise ValueError(f"text is {len(text)} characters; the limit is {MAX_TEXT}")
    query = urllib.parse.urlencode({"text": text, "voice": voice, "speed": max(0.5, min(2.0, speed))})
    try:
        with urllib.request.urlopen(f"{voice_url()}/tts?{query}", timeout=60) as response:
            return response.read(), response.headers.get("Content-Type", "audio/wav")
    except urllib.error.HTTPError as error:
        raise ValueError(error.read().decode(errors="replace") or f"the narration server answered {error.code}") from None
