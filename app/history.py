"""Cross-debrief commitment tracking (a history file, no vector store).

The roadmap's "memory" milestone: the second debrief for the same company
opens with a commitment check. This is done by injecting a summary of the
previous session into the agent's greeting and system prompt at publish time,
so the same stored agent picks up the check on the next call.

The summary lives in one JSON file per company under data/history/:

    data/history/project-8.json
    {
      "company": "Project 8",
      "last_debrief_at": "2026-09-01T10:00:00Z",
      "commitments": [
        {"task": "submit written approval for the reallocated grant",
         "owner": "Ben", "deadline": "next Monday"}
      ],
      "signals": ["CFO left, finance unmanaged"]
    }

With no history file present, apply_history() is a no-op, so the mechanism
ships inert and activates the moment a file appears. Pick the file with
HISTORY_COMPANY=project-8, otherwise the most recently modified one is used.
"""

import json
import os
from pathlib import Path
from typing import Any, Optional

from lib import read_json
from history_from_ledger import slugify

ROOT = Path(__file__).resolve().parent
HISTORY_DIR = ROOT / "data" / "history"


def list_companies() -> list[str]:
    return sorted(p.stem for p in HISTORY_DIR.glob("*.json"))


def load_history(company: str) -> Optional[dict]:
    # read_json returns None for a missing OR corrupt file -- a half-written
    # history file must not kill the publish/boot path that reads it.
    return read_json(HISTORY_DIR / f"{slugify(company)}.json")


def latest_history() -> Optional[dict]:
    files = list(HISTORY_DIR.glob("*.json"))
    if not files:
        return None
    latest = max(files, key=lambda p: p.stat().st_mtime)
    return read_json(latest)


def _pick_history() -> Optional[dict]:
    company = (os.environ.get("HISTORY_COMPANY") or os.environ.get("COMPANY") or "").strip()
    return load_history(company) if company else None


def _commitment_greeting(history: dict) -> Optional[str]:
    commitments = history.get("commitments") or []
    if not commitments:
        return None
    company = history.get("company", "the company")
    first = commitments[0]
    task = first.get("task", "")
    owner = first.get("owner", "")
    deadline = first.get("deadline", "")
    tail = ""
    if owner:
        tail = f" — {owner}"
        if deadline:
            tail += f", due {deadline}"
    return (
        f"Welcome back. Before we cover anything new from {company}, "
        "let's close one prior follow-up at a time. "
        f"Let's start here: {task}{tail}. What is the current status?"
    )


def _commitment_prompt() -> str:
    return (
        "This is a repeat debrief for the same company. Prior follow-ups are "
        "working context, not a script to read aloud. Follow this exact sequence: "
        "(1) ask about only the first prior follow-up; (2) wait for the investor's "
        "answer; (3) ask one short clarification only if its status is still "
        "unclear; (4) once it is resolved, still open, or explicitly unclear, "
        "acknowledge it briefly and move to the next prior follow-up. Never list, "
        "preview, or ask multiple prior follow-ups in one turn. Keep going one at "
        "a time until every prior follow-up has a clear status. If one remains "
        "open, offer a new reminder only as a question and wait for explicit yes "
        "before calling add_action_item. Only after all prior follow-ups have a "
        "status should you ask what else changed in this visit and investigate "
        "new signals. Do not re-ask old signals unless the investor reports a "
        "new change or risk. Log evidence only when the outcome is itself a risk "
        "signal."
    )


def _summary_prompt(history: dict) -> str:
    parts = []
    signals = history.get("signals") or []
    if signals:
        listed = "; ".join(signals)
        parts.append(
            "Signals already recorded from the previous debrief: " + listed +
            ". Do not re-ask these unless there is something new."
        )
    parts.append(_commitment_prompt())
    return "\n\n".join(parts)


def apply_history(agent: dict, company: Optional[str] = None) -> bool:
    """Inject the previous session's summary into the agent, in place.

    Returns True when a history file was found and applied, False when there is
    nothing to inject (and the agent is left untouched).
    """
    history = load_history(company) if company else _pick_history()
    if not history or not history.get("commitments"):
        return False
    greeting = _commitment_greeting(history)
    if greeting:
        agent["greeting"] = greeting
    agent["system_prompt"] = (agent.get("system_prompt", "") +
                              "\n\n" + _summary_prompt(history))
    return True
