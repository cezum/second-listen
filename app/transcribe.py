"""Pre-recorded transcription via AssemblyAI Universal-2 (the v2 API).

The live voice agent streams through the agents API (wss://agents...). File
upload mode goes through the separate transcription API instead, which costs
$0.45/hr (not realtime pricing) and handles Chinese and other languages well —
this is what closes the "real-time voice can't speak Chinese" gap: we turn a
Chinese recording into a transcript, then apply the same evidence framework over the text.

Standard library only, matching lib.py.
"""

import json
import http.client
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_BASE = "https://api.assemblyai.com/v2"


class TranscribeError(Exception):
    # transient marks failures worth retrying: dead connection, timeout, 5xx.
    def __init__(self, message: str, transient: bool = False):
        super().__init__(message)
        self.transient = transient


# The upload endpoint takes the raw audio bytes as the request body (not
# multipart) and derives the format from the Content-Type header. A generic
# application/octet-stream makes the transcoder reject the file ("Transcoding
# failed"). Voice-agent artifacts are Ogg Opus; user uploads are usually
# mp3/m4a/wav.
_MIME = {
    ".ogg": "audio/ogg", ".oga": "audio/ogg", ".opus": "audio/ogg",
    ".mp3": "audio/mpeg", ".mpga": "audio/mpeg",
    ".wav": "audio/wav", ".flac": "audio/flac", ".aac": "audio/aac",
    ".m4a": "audio/mp4", ".mp4": "video/mp4", ".webm": "audio/webm",
}


def _mime_for(filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    return _MIME.get(ext, "application/octet-stream")


def _auth() -> dict:
    # The transcription API (api.assemblyai.com/v2) takes the key raw, without
    # the "Bearer " prefix the agents API (agents.assemblyai.com) uses. Accept
    # either form in .env by normalizing here, matching lib.aai().
    api_key = os.environ.get("ASSEMBLYAI_API_KEY", "").strip()
    if api_key.lower().startswith("bearer "):
        api_key = api_key[7:].strip()
    return {"Authorization": api_key}


_RETRY_CODES = (408, 500, 502, 503, 504)


def _request(url: str, method: str = "GET", headers: dict = None,
             data: bytes = None, timeout: float = 60.0) -> bytes:
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.read()
    except urllib.error.HTTPError as err:
        raise TranscribeError(
            f"{method} {url} failed ({err.code}): {err.read().decode()}",
            transient=err.code in _RETRY_CODES,
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        # URLError covers refused/unreachable connections and DNS; TimeoutError
        # is a socket that never answered. Both may be gone on the next try.
        raise TranscribeError(
            f"{method} {url} failed: {err}", transient=True) from None


def _request_retry(url: str, attempts: int = 3, **kwargs) -> bytes:
    """Retry transient failures with exponential backoff (1s, 2s)."""
    delay = 1.0
    for attempt in range(attempts):
        try:
            return _request(url, **kwargs)
        except TranscribeError as err:
            if attempt + 1 == attempts or not err.transient:
                raise
            time.sleep(delay)
            delay *= 2


def _request_file(url: str, method: str, headers: dict, path: Path,
                  timeout: float = 300.0) -> bytes:
    """Send a file body in chunks so upload size does not multiply in memory."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.query or parsed.fragment:
        raise TranscribeError('unsupported upload URL')
    conn = http.client.HTTPSConnection(parsed.netloc, timeout=timeout)
    try:
        conn.putrequest(method, parsed.path or '/')
        for key, value in headers.items():
            conn.putheader(key, value)
        conn.putheader('Content-Length', str(path.stat().st_size))
        conn.endheaders()
        with path.open('rb') as source:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                conn.send(chunk)
        response = conn.getresponse()
        body = response.read()
        if not 200 <= response.status < 300:
            raise TranscribeError(
                f"{method} {url} failed ({response.status}): {body.decode(errors='replace')}",
                transient=response.status in _RETRY_CODES)
        return body
    except TranscribeError:
        raise
    except (OSError, TimeoutError) as err:
        raise TranscribeError(f"{method} {url} failed: {err}", transient=True) from None
    finally:
        conn.close()


def _request_file_retry(url: str, path: Path, attempts: int = 3, **kwargs) -> bytes:
    delay = 1.0
    for attempt in range(attempts):
        try:
            return _request_file(url, path=path, **kwargs)
        except TranscribeError as err:
            if attempt + 1 == attempts or not err.transient:
                raise
            time.sleep(delay)
            delay *= 2


def _transcribe_uploaded(upload_url: str, timeout: float) -> dict:
    payload = json.dumps({
        "audio_url": upload_url,
        "speech_models": ["universal-2"],
        "language_detection": True,
    }).encode()
    sub = _request_retry(f"{API_BASE}/transcript", method="POST",
                         headers={**_auth(), "Content-Type": "application/json"},
                         data=payload)
    transcript_id = json.loads(sub).get("id")
    if not transcript_id:
        raise TranscribeError(f"transcript submit failed: {sub.decode()}")

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2)
        res = json.loads(_request(f"{API_BASE}/transcript/{transcript_id}",
                                  "GET", _auth(), timeout=30.0))
        status = res.get("status")
        if status == "completed":
            return {
                "text": res.get("text", ""),
                "language": res.get("language_code"),
                "duration": res.get("audio_duration"),
                "confidence": res.get("confidence"),
            }
        if status == "error":
            raise TranscribeError(f"transcription error: {res.get('error')}")
    raise TranscribeError("transcription timed out")
def transcribe(audio_bytes: bytes, filename: str, timeout: float = 300.0) -> dict:
    """Transcribe a pre-recorded audio file to text.

    Returns {"text", "language", "duration", "confidence"}.
    """
    # 1. Upload the raw audio as the request body to get a short-lived URL.
    #    Upload gets the longest socket timeout — it moves the whole file.
    up = _request_retry(f"{API_BASE}/upload", method="POST",
                        headers={**_auth(), "Content-Type": _mime_for(filename)},
                        data=audio_bytes, timeout=300.0)
    upload_url = json.loads(up).get("upload_url")
    if not upload_url:
        raise TranscribeError(f"upload failed: {up.decode()}")

    return _transcribe_uploaded(upload_url, timeout)


def transcribe_file(path: Path, filename: str, timeout: float = 300.0) -> dict:
    """Transcribe a temporary file without copying its full bytes in memory."""
    upload = _request_file_retry(
        f"{API_BASE}/upload", path=Path(path), method="POST",
        headers={**_auth(), "Content-Type": _mime_for(filename)}, timeout=300.0)
    upload_url = json.loads(upload).get("upload_url")
    if not upload_url:
        raise TranscribeError(f"upload failed: {upload.decode()}")
    return _transcribe_uploaded(upload_url, timeout)
