"""Turn a finished debrief session in the ledger into a history file.

After a live debrief the browser page POSTs every tool call to /api/ledger,
leaving data/ledger.json shaped like:

    {"sessions": {"<id>": {"started_at": "...", "events": [
        {"at_seconds": 42, "tool": "log_evidence", "dimension": "team_integrity",
         "quote": "...", "signal": "CFO left, finance unmanaged", "escalation": true},
        {"at_seconds": 61, "tool": "add_action_item", "owner": "Ben",
         "deadline": "next Monday", "task": "send the written approval"}
    ]}}}

The cross-debrief commitment check reads data/history/<company>.json, which
wants `commitments` (owner/deadline/task) and `signals` (strings). The agent's
add_action_item arguments already use the commitment field names, so this is a
pick-and-repack, not a translation.

    COMPANY=project-8 python history_from_ledger.py

Environment:
  COMPANY    the company name, also the filename (default: Project 8)
  SESSION    which ledger session to read (default: the most recent one)
  FORCE=1    overwrite an existing history file
  DRY_RUN=1  print the file instead of writing it
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from lib import atomic_write_text

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "data" / "ledger.json"
HISTORY_DIR = ROOT / "data" / "history"


def load_ledger() -> dict:
    if not LEDGER.exists():
        return {"sessions": {}}
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"sessions": {}}


def pick_session(ledger: dict, session_id: str) -> tuple[str, dict]:
    """Return (session_id, session). With no session_id, the most recent one
    by started_at; sessions missing started_at sort last, and the key breaks
    the tie so the choice is stable between runs."""
    sessions = ledger.get("sessions") or {}
    if not sessions:
        raise SystemExit(
            "ledger.json has no sessions yet. Run a live debrief, or check "
            "that the browser page reached /api/ledger."
        )
    if session_id:
        if session_id not in sessions:
            raise SystemExit(
                f"session {session_id!r} is not in the ledger. Known: "
                + ", ".join(sorted(sessions))
            )
        return session_id, sessions[session_id]
    chosen = max(sessions.items(),
                 key=lambda kv: (kv[1].get("started_at") or "", kv[0]))
    return chosen


def slugify(company: str) -> str:
    chars = [c.lower() if c.isalnum() else "-" for c in company.strip()]
    slug = "".join(chars)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "company"


def build_history(session: dict, company: str) -> dict:
    """Repack one session's tool calls into the history file shape."""
    commitments: list[dict] = []
    signals: list[str] = []
    for event in session.get("events") or []:
        tool = event.get("tool")
        if tool == "add_action_item":
            commitments.append({
                "task": event.get("task", ""),
                "owner": event.get("owner", ""),
                "deadline": event.get("deadline", ""),
            })
        elif tool == "log_evidence":
            signal = (event.get("signal") or "").strip()
            if signal and signal not in signals:
                signals.append(signal)
    return {
        "company": company,
        "last_debrief_at": session.get("started_at") or "",
        "commitments": commitments,
        "signals": signals,
    }


def main() -> int:
    company = os.environ.get("COMPANY", "").strip() or "Project 8"
    want_session = os.environ.get("SESSION", "").strip()
    force = os.environ.get("FORCE") == "1"
    dry_run = os.environ.get("DRY_RUN") == "1"

    session_id, session = pick_session(load_ledger(), want_session)
    history = build_history(session, company)

    commitments = history["commitments"]
    signals = history["signals"]
    print(f"session  {session_id}")
    print(f"company  {company}")
    print(f"read     {len(session.get('events') or [])} tool calls "
          f"-> {len(commitments)} commitment(s), {len(signals)} signal(s)")

    if not commitments:
        # apply_history() is a no-op without commitments, so say so plainly
        # instead of writing a file that silently does nothing.
        print("\nwarning  no add_action_item calls in this session, so the "
              "commitment check will not fire.\n"
              "         The agent only logs an action item when you agree to "
              "a follow-up during the call.")

    body = json.dumps(history, ensure_ascii=False, indent=2)
    if dry_run:
        print("\n" + body)
        return 0

    path = HISTORY_DIR / f"{slugify(company)}.json"
    if path.exists() and not force:
        print(f"\n{path} already exists. Re-run with FORCE=1 to overwrite, or "
              "pick another COMPANY name to keep this one.")
        return 1

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, body + "\n")
    print(f"\nwrote    {path}")
    print(f"next     COMPANY={slugify(company)} python publish.py")
    print("         then start a new call: the agent opens by checking "
          "each commitment above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
