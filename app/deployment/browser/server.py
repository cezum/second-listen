#!/usr/bin/env python3
"""Talk to your agent from a browser tab.

    python deployment/browser/server.py

The API key stays in this process; the page only gets 60-second tokens.
"""

import copy
import json
import os
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
LEDGER = HERE.parents[1] / "data" / "ledger.json"
GATE_LOG = HERE.parents[1] / "data" / "gate_log.json"

from lib import (ApiError, aai, load_env, publish_agent, read_agent,  # noqa: E402
                 required, stored_agent_id)
from archive import DEFAULT_TRIALS_DIR, archive_async  # noqa: E402
import transcribe  # noqa: E402
import analyze  # noqa: E402
from history import apply_history, latest_history  # noqa: E402

# The page flushes every tool call of a turn at once, so several POSTs land in
# parallel. Reading, appending and writing without a lock loses whichever
# events were still in flight -- two evidence rows went in, one came out.
LEDGER_LOCK = threading.Lock()


def resolve_agent() -> dict:
    """A published id means the agent is managed elsewhere, so use it as it is."""
    name = os.environ.get("AGENT", "minimal")
    known = stored_agent_id(name)
    if known:
        try:
            agent = aai(f"/agents/{known}")
        except ApiError as err:
            sys.exit(f"Could not load agent {known}: {err}")
        return {"id": known, "name": agent.get("name") or "Your agent"}
    agent = read_agent(name)
    apply_history(agent)
    try:
        result = publish_agent(agent, name=name, reuse_by_name=True)
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
        if path == "/token":
            try:
                token = aai("/token?product=voice_agent&expires_in_seconds=60")
                self._send(200, json.dumps(token).encode(), "application/json")
            except ApiError as err:
                print(err)
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
                print(err)
                self._send(502, b'{"error":"could not load the agent"}', "application/json")
            return
        if path == "/app.js":
            self._send(200, (HERE / "app.js").read_bytes(), "text/javascript")
            return
        self._send(200, PAGE.encode(), "text/html")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/api/upload":
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length <= 0 or length > 50 * 1024 * 1024:
                    self._send(400, b'{"error":"empty or oversized file"}',
                               "application/json")
                    return
                audio = self.rfile.read(length)
                filename = self.headers.get("X-Filename") or "recording.ogg"
                result = transcribe.transcribe(audio, filename)
                result["analysis"] = analyze.analyze_transcript(
                    result.get("text", ""), result.get("language"))
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"),
                           "application/json")
            except transcribe.TranscribeError as err:
                print(err)
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
                    log = []
                    if GATE_LOG.exists():
                        log = json.loads(GATE_LOG.read_text(encoding="utf-8"))
                    log.append({
                        "at": datetime.now(timezone.utc).isoformat(),
                        "session_id": body.get("session_id"),
                        "at_seconds": body.get("at_seconds"),
                        "kind": body.get("kind", "fire"),
                    })
                    GATE_LOG.write_text(
                        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
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
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def read_ledger_bytes() -> bytes:
    if not LEDGER.exists():
        return b'{"sessions":{}}'
    return LEDGER.read_bytes()


def write_ledger(ledger: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2),
                      encoding="utf-8")


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
    while True:
        try:
            server = ThreadingHTTPServer(("", port), Handler)
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
