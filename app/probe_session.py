"""Zero-voice probe: can a realtime session actually start?

`docs/live-test-checklist.md` Round 0 verifies the agent over REST, but the
browser talks to a different service: the websocket at
wss://agents.assemblyai.com/v1/ws. Those two disagree more often than you would
like -- REST can answer 200 for an id the session service calls
`agent_not_found`, which is exactly how a speaking round gets wasted.

This script mints a 60-second token, opens the websocket, sends one
`session.update`, and prints what comes back. No microphone, no audio frames:
`session.ready` means the round will start.

Usage (from app/):

    python probe_session.py            # both modes
    python probe_session.py stored     # the published agent id
    python probe_session.py inline     # the local agents/<name>.jsonc
"""

import base64
import json
import os
import socket
import ssl
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import aai, load_env, read_agent, stored_agent_id  # noqa: E402

HOST = "agents.assemblyai.com"
PATH = "/v1/ws"
AGENT_NAME = os.environ.get("AGENT", "second-listen")


def mint_token() -> str:
    return aai("/token?product=voice_agent&expires_in_seconds=60")["token"]


def connect(token: str) -> ssl.SSLSocket:
    raw = socket.create_connection((HOST, 443), timeout=10)
    sock = ssl.create_default_context().wrap_socket(raw, server_hostname=HOST)
    key = base64.b64encode(os.urandom(16)).decode()
    sock.sendall(
        f"GET {PATH}?token={token} HTTP/1.1\r\n"
        f"Host: {HOST}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n".encode()
    )
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("connection closed during handshake")
        buf += chunk
    status = buf.split(b"\r\n", 1)[0].decode(errors="replace")
    if "101" not in status:
        raise RuntimeError(f"handshake refused: {status}")
    return sock


def send_text(sock: ssl.SSLSocket, text: str) -> None:
    payload = text.encode()
    mask = os.urandom(4)
    n = len(payload)
    if n < 126:
        header = struct.pack("!BB", 0x81, 0x80 | n)
    elif n < 65536:
        header = struct.pack("!BBH", 0x81, 0x80 | 126, n)
    else:
        header = struct.pack("!BBQ", 0x81, 0x80 | 127, n)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    sock.sendall(header + mask + masked)


def read_messages(sock: ssl.SSLSocket, seconds: float = 8.0) -> list:
    buf = b""
    out = []
    deadline = time.time() + seconds
    sock.settimeout(1.0)
    while time.time() < deadline:
        try:
            data = sock.recv(65536)
        except socket.timeout:
            continue
        if not data:
            break
        buf += data
        while True:
            if len(buf) < 2:
                break
            opcode = buf[0] & 0x0F
            length = buf[1] & 0x7F
            offset = 2
            if length == 126:
                if len(buf) < 4:
                    break
                length = struct.unpack("!H", buf[2:4])[0]
                offset = 4
            elif length == 127:
                if len(buf) < 10:
                    break
                length = struct.unpack("!Q", buf[2:10])[0]
                offset = 10
            if len(buf) < offset + length:
                break
            payload = buf[offset:offset + length]
            buf = buf[offset + length:]
            if opcode == 0x1:
                try:
                    out.append(json.loads(payload.decode()))
                except ValueError:
                    out.append({"type": "?unparsed", "raw": payload[:200].decode("replace")})
            elif opcode == 0x8:
                return out
    return out


def stored_session() -> dict:
    return {"type": "session.update",
            "session": {"agent_id": stored_agent_id(AGENT_NAME)}}


def inline_session() -> dict:
    agent = read_agent(AGENT_NAME)
    return {"type": "session.update",
            "session": {
                "system_prompt": agent["system_prompt"],
                "greeting": agent["greeting"],
                "output": {"voice": agent["voice"]["voice_id"]},
                "tools": agent.get("tools", []),
                **({"input": agent["input"]} if agent.get("input") else {}),
            }}


def probe(mode: str) -> None:
    session = stored_session() if mode == "stored" else inline_session()
    label = f"{mode}: " + (
        session["session"].get("agent_id", "inline config"))
    tools = session["session"].get("tools")
    if tools is not None:
        label += f" (tools: {[t['name'] for t in tools]})"
    print(f"\n=== {label} ===")
    sock = connect(mint_token())
    try:
        send_text(sock, json.dumps(session))
        messages = read_messages(sock)
    finally:
        try:
            sock.close()
        except OSError:
            pass
    if not messages:
        print("  no messages -- session service said nothing")
        return
    for msg in messages[:8]:
        kind = msg.get("type")
        if kind in ("session.error", "error"):
            print(f"  {kind}: {json.dumps(msg, ensure_ascii=False)[:300]}")
        elif kind == "session.ready":
            print("  session.ready  <-- this mode will start a call")
        else:
            print(f"  {kind}")
    types = {m.get("type") for m in messages}
    print("  VERDICT:", "OK" if "session.ready" in types else "FAILED")


def main() -> None:
    load_env()
    modes = sys.argv[1:] or ["stored", "inline"]
    for mode in modes:
        if mode not in ("stored", "inline"):
            sys.exit(f"unknown mode {mode!r}, expected stored or inline")
        probe(mode)


if __name__ == "__main__":
    main()
