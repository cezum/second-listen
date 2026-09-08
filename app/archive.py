"""Archive a completed voice-agent session to a local trials directory.

The AssemblyAI Sessions API publishes artifacts (audio, timeline, metadata)
only after a session ends, so archive_session() returns ok:False when they are
not ready yet. archive_async() retries on a short schedule and gives up; the
manual trials_fetch.py script still catches anything it missed.

TRIALS_DIR (default: app/data/trials) points where recordings land. Keep it
outside any public repo if the recordings are private.
"""

import json
import os
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional

from lib import aai, atomic_write_text, read_json  # noqa: E402

DEFAULT_TRIALS_DIR = Path(__file__).resolve().parent / "data" / "trials"


def _download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=120) as res, dest.open("wb") as f:
        while True:
            chunk = res.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)


def _write_transcript(session_dir: Path, timeline: dict) -> None:
    lines = []
    for turn in timeline.get("turns", []):
        if turn.get("user_transcript"):
            lines.append(f"### 用户\n{turn['user_transcript']}\n")
        for call in turn.get("tool_calls", []):
            args = json.dumps(call.get("arguments"), ensure_ascii=False)
            err = " [ERROR]" if call.get("is_error") else ""
            lines.append(f"### 工具 {call.get('name')}{err}\n{args} -> {call.get('result')}\n")
        if turn.get("agent_text"):
            lines.append(f"### Agent\n{turn['agent_text']}\n")
    (session_dir / "transcript.md").write_text("\n".join(lines), encoding="utf-8")


def _update_index(trials_dir: Path, session: dict) -> None:
    index_path = trials_dir / "index.json"
    index = read_json(index_path, [])
    if not isinstance(index, list):
        index = []
    entry = {
        "id": session.get("id"),
        "status": session.get("status"),
        "created_at": session.get("created_at"),
        "duration_seconds": session.get("duration_seconds"),
    }
    index = [e for e in index if e.get("id") != session.get("id")] + [entry]
    atomic_write_text(index_path,
                      json.dumps(index, ensure_ascii=False, indent=2))


def archive_session(session_id: str, trials_dir: Optional[Path] = None) -> dict:
    """Fetch one session and save it under trials_dir/<session_id>/. Returns
    ok:True once saved (or skipped because it already exists)."""
    trials_dir = Path(trials_dir) if trials_dir else DEFAULT_TRIALS_DIR
    session_dir = trials_dir / session_id
    required_files = {"timeline.json", "metadata.json", "audio.ogg", "summary.json", "transcript.md"}
    if session_dir.is_dir() and required_files.issubset(
            {path.name for path in session_dir.iterdir()}):
        return {"ok": True, "skipped": True}

    detail = aai(f"/sessions/{session_id}")
    if not detail.get("id"):
        return {"ok": False, "reason": "session not found"}
    if detail.get("status") != "completed":
        return {"ok": False, "reason": f"status={detail.get('status')}"}

    artifacts = {a["type"]: a["url"] for a in detail.get("artifacts", [])}
    if not artifacts:
        return {"ok": False, "reason": "artifacts not ready"}

    trials_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{session_id}.", dir=trials_dir) as staging:
        staging_dir = Path(staging)
        timeline = {}
        for kind, filename in (("timeline", "timeline.json"),
                               ("metadata", "metadata.json"),
                               ("audio", "audio.ogg")):
            url = artifacts.get(kind)
            if not url:
                continue
            _download(url, staging_dir / filename)
            if kind == "timeline":
                timeline = json.loads((staging_dir / filename).read_text(encoding="utf-8"))

        if not {"timeline", "metadata", "audio"}.issubset(artifacts):
            return {"ok": False, "reason": "required artifacts missing"}
        _write_transcript(staging_dir, timeline)
        summary = {
            "id": session_id,
            "agent_id": detail.get("agent_id"),
            "status": detail.get("status"),
            "created_at": detail.get("created_at"),
            "ended_at": detail.get("ended_at"),
            "duration_seconds": detail.get("duration_seconds"),
            "public_close_reason": detail.get("public_close_reason"),
        }
        (staging_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        if session_dir.exists():
            # A prior interrupted run may have left a partial directory. It is
            # safe to replace only after the staging directory is complete.
            for child in session_dir.iterdir():
                if child.is_file():
                    child.unlink()
            session_dir.rmdir()
        os.replace(staging_dir, session_dir)
    _update_index(trials_dir, detail)
    return {"ok": True, "session_id": session_id}


def archive_async(session_id: str, trials_dir: Optional[Path] = None,
                  attempts: int = 10, delay: float = 3.0) -> None:
    """Archive in the background, retrying while AssemblyAI still prepares the
    artifacts. Never blocks the request that scheduled it."""

    def run() -> None:
        for i in range(attempts):
            try:
                result = archive_session(session_id, trials_dir)
            except Exception as err:  # keep trying; API hiccups are transient
                result = {"ok": False, "reason": str(err)}
            if result.get("ok"):
                return
            if i + 1 < attempts:
                time.sleep(delay)

    threading.Thread(target=run, daemon=True).start()
