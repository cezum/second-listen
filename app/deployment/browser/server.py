#!/usr/bin/env python3
"""Talk to your agent from a browser tab.

    python deployment/browser/server.py

The API key stays in this process; the page only gets 60-second tokens.
"""

import copy
import hashlib
import json
import os
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
LEDGER = HERE.parents[1] / "data" / "ledger.json"
GATE_LOG = HERE.parents[1] / "data" / "gate_log.json"

from lib import (ApiError, aai, atomic_write_text, ensure_agent, load_env,
                 read_agent, read_json, required)
from archive import DEFAULT_TRIALS_DIR, archive_async  # noqa: E402
import transcribe  # noqa: E402
import analyze  # noqa: E402
from history import apply_history, latest_history  # noqa: E402
from note import note_for_session  # noqa: E402

# The page flushes every tool call of a turn at once, so several POSTs land in
# parallel. Reading, appending and writing without a lock loses whichever
# events were still in flight -- two evidence rows went in, one came out.
LEDGER_LOCK = threading.Lock()


def resolve_agent() -> dict:
    """Publish the file, then serve whatever id comes back.

    This used to trust an id in .env as it stood and exit on a 404, so an agent
    deleted in the dashboard read as a mystery failure on every later start.
    The file is the source of truth, so publish it and let ensure_agent repair
    a stale id or reuse one already on the account.
    """
    name = os.environ.get("AGENT", "minimal")
    agent = read_agent(name)
    apply_history(agent)
    try:
        result = ensure_agent(agent, name=name)
    except ApiError as err:
        sys.exit(f"Could not publish agents/{name}.jsonc: {err}")
    verb = "Created" if result["created"] else "Updated"
    print(f'{verb} "{agent["name"]}" from agents/{name}.jsonc')
    return {"id": result["id"], "name": agent["name"]}


def public_agent(agent: dict) -> dict:
    """Read-only view of the stored agent. The API keeps header values and llm
    keys write-only; these deletes hold even if that changes. The system prompt
    is in here, so a public deployment shows it to anyone who opens the page."""
    copied = copy.deepcopy(agent)
    for tool in copied.get("tools", []):
        # Function (client-side) tools have no http block; only HTTP tools
        # carry headers worth hiding.
        for header in (tool.get("http") or {}).get("headers", []):
            header["value"] = "<hidden>"
    for llm in copied.get("llm", []):
        llm.pop("api_key", None)
    return copied


AGENT = None
PAGE = ""
TRIALS_DIR = Path(os.environ.get("TRIALS_DIR") or DEFAULT_TRIALS_DIR)
# Universal-2 bills per upload ($0.45/hr), so repeat analyses of the same
# recording would bill twice. Cache transcripts by audio hash -- the analysis
# itself is re-run every request, only transcription results are cached.
TRANSCRIPT_CACHE = Path(os.environ.get("TRANSCRIPT_CACHE_DIR")
                        or HERE.parents[1] / "data" / "transcript_cache")


def debug_log(*args) -> None:
    """Runtime request errors go nowhere unless DEBUG is set; the default
    server stays quiet (startup and publish messages still print)."""
    if os.environ.get("DEBUG"):
        print(*args, file=sys.stderr)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/api/ledger":
            self._send(200, read_ledger_bytes(), "application/json")
            return
        if path == "/api/history":
            history = latest_history() or {}
            self._send(200, json.dumps(history, ensure_ascii=False).encode(),
                       "application/json")
            return
        if path == "/api/note":
            query = parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
            session_id = (query.get("session") or [""])[0] or None
            company = (query.get("company") or [""])[0]
            try:
                sid, markdown = note_for_session(session_id, company)
            except SystemExit as err:
                self._send(404,
                           json.dumps({"error": str(err)}).encode(),
                           "application/json")
                return
            self._send(200, markdown.encode("utf-8"),
                       "text/markdown; charset=utf-8")
            return
        if path == "/token":
            try:
                token = aai("/token?product=voice_agent&expires_in_seconds=60")
                self._send(200, json.dumps(token).encode(), "application/json")
            except ApiError as err:
                debug_log(err)
                self._send(502, b'{"error":"token request failed"}', "application/json")
            return
        if path == "/agent":
            if AGENT.get("config"):
                # Inline mode: the agent lives in the local file, not the API.
                self._send(200, json.dumps(AGENT["config"]).encode(), "application/json")
                return
            try:
                agent = aai(f"/agents/{AGENT['id']}")
                self._send(200, json.dumps(public_agent(agent)).encode(), "application/json")
            except ApiError as err:
                debug_log(err)
                self._send(502, b'{"error":"could not load the agent"}', "application/json")
            return
        if path == "/app.js":
            self._send(200, (HERE / "app.js").read_bytes(), "text/javascript")
            return
        # Unknown /api/* paths are bugs, not navigation: answer 404 instead of
        # serving the page, which made a mistyped fetch look like success.
        if path.startswith("/api/"):
            self._send(404, b'{"error":"not found"}', "application/json")
            return
        self._send(200, PAGE.encode(), "text/html")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/api/upload":
            try:
                length = int(self.headers.get("Content-Length", 0))
                # The cap bounds the 2x memory spike of buffering the whole
                # body and then POSTing it on to /v2/upload. 50MB is plenty
                # for hours of debrief audio; chunked upload would be the
                # fix if this ever needs to grow.
                if length <= 0 or length > 50 * 1024 * 1024:
                    self._send(400, b'{"error":"empty or oversized file"}',
                               "application/json")
                    return
                audio = self.rfile.read(length)
                filename = self.headers.get("X-Filename") or "recording.ogg"
                cache_file = TRANSCRIPT_CACHE / (
                    hashlib.sha256(audio).hexdigest() + ".json")
                cached = read_json(cache_file)
                if cached is not None:
                    result = cached
                else:
                    result = transcribe.transcribe(audio, filename)
                    atomic_write_text(
                        cache_file, json.dumps(result, ensure_ascii=False))
                result["analysis"] = analyze.analyze_transcript(
                    result.get("text", ""), result.get("language"))
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"),
                           "application/json")
            except transcribe.TranscribeError as err:
                debug_log(err)
                self._send(502, json.dumps({"error": str(err)}).encode(),
                           "application/json")
            except (ValueError, OSError) as err:
                self._send(400, json.dumps({"error": str(err)}).encode(),
                           "application/json")
            return
        if path == "/api/archive":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                session_id = body.get("session_id")
                if not session_id:
                    self._send(400, b'{"error":"session_id required"}', "application/json")
                    return
                archive_async(session_id, TRIALS_DIR)
                self._send(200, b'{"ok":true,"status":"queued"}', "application/json")
            except (ValueError, OSError) as err:
                self._send(400, json.dumps({"error": str(err)}).encode(), "application/json")
            return
        if path == "/api/gate":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                with LEDGER_LOCK:
                    log = read_json(GATE_LOG, []) or []
                    log.append({
                        "at": datetime.now(timezone.utc).isoformat(),
                        "session_id": body.get("session_id"),
                        "at_seconds": body.get("at_seconds"),
                        "kind": body.get("kind", "fire"),
                    })
                    atomic_write_text(
                        GATE_LOG, json.dumps(log, ensure_ascii=False, indent=2))
                self._send(200, b'{"ok":true}', "application/json")
            except (ValueError, OSError) as err:
                self._send(400, json.dumps({"error": str(err)}).encode(),
                           "application/json")
            return
        if path != "/api/ledger":
            self._send(404, b'{"error":"not found"}', "application/json")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            with LEDGER_LOCK:
                ledger = read_ledger()
                session_id = body.get("session_id") or "session"
                entry = ledger["sessions"].setdefault(
                    session_id,
                    {"started_at": datetime.now(timezone.utc).isoformat(), "events": []},
                )
                event = {
                    "at_seconds": body.get("elapsed_seconds"),
                    "tool": body.get("name"),
                    **body.get("arguments", {}),
                }
                entry["events"].append(event)
                write_ledger(ledger)
            self._send(200, json.dumps({
                "ok": True,
                "event_count": len(entry["events"]),
                "escalation": bool(body.get("arguments", {}).get("escalation")),
            }).encode(), "application/json")
        except (ValueError, OSError) as err:
            self._send(400, json.dumps({"error": str(err)}).encode(), "application/json")

    def do_DELETE(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/api/ledger":
            with LEDGER_LOCK:
                write_ledger({"sessions": {}})
            self._send(200, b'{"ok":true}', "application/json")
            return
        self._send(404, b'{"error":"not found"}', "application/json")

    def log_message(self, *args) -> None:  # quiet; errors are printed above
        pass


def read_ledger() -> dict:
    if not LEDGER.exists():
        return {"sessions": {}}
    return read_json(LEDGER, {"sessions": {}})


def read_ledger_bytes() -> bytes:
    if not LEDGER.exists():
        return b'{"sessions":{}}'
    return LEDGER.read_bytes()


def write_ledger(ledger: dict) -> None:
    atomic_write_text(LEDGER, json.dumps(ledger, ensure_ascii=False, indent=2))


def main() -> None:
    global AGENT, PAGE
    load_env()
    required("ASSEMBLYAI_API_KEY", "get one at https://www.assemblyai.com/dashboard/api-keys")

    # MODE=inline serves the agent's config from the local file and builds the
    # session inline, so the page works even when stored agents on the account
    # cannot be resolved by the session service. Default stays stored.
    mode = os.environ.get("MODE", "stored")
    if mode == "inline":
        agent = read_agent(os.environ.get("AGENT", "minimal"))
        apply_history(agent)
        AGENT = {"id": "", "name": agent["name"], "config": agent}
        print("Inline mode: session config from the local agent file")
    else:
        AGENT = resolve_agent()
    print(f"Agent: {AGENT['id'] or AGENT['name']}")
    PAGE = ((HERE / "index.html").read_text(encoding="utf-8")
            .replace("{{AGENT_NAME}}", AGENT["name"])
            .replace("{{AGENT_JSON}}", json.dumps(AGENT).replace("<", "\\u003c")))

    # PORT when set, otherwise 3000 and up until one is free.
    fixed = os.environ.get("PORT")
    port = int(fixed) if fixed else 3000
    # Loopback unless a deployment explicitly asks to be reachable. The
    # ledger, note and history endpoints carry real debrief content and have
    # no auth, so binding every interface is a decision, not a default.
    host = os.environ.get("HOST", "127.0.0.1")
    while True:
        try:
            server = ThreadingHTTPServer((host, port), Handler)
            break
        except OSError:
            if fixed or port >= 3010:
                raise
            port += 1

    print(f"Talk to it: http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
