"""Cross-debrief commitment tracking (a history file, no vector store).

The roadmap's "memory" milestone: the second debrief for the same company
opens with a commitment check. This is done by injecting a summary of the
previous session into the agent's greeting and system prompt at publish time,
so the same stored agent picks up the check on the next call.

The summary lives in one JSON file per company under data/history/:

    data/history/greenleaf.json
    {
      "company": "GreenLeaf",
      "last_debrief_at": "2026-09-01T10:00:00Z",
      "commitments": [
        {"task": "submit written approval for the reallocated grant",
         "owner": "Ben", "deadline": "next Monday"}
      ],
      "signals": ["CFO left, finance unmanaged"]
    }

With no history file present, apply_history() is a no-op, so the mechanism
ships inert and activates the moment a file appears. Pick the file with
HISTORY_COMPANY=greenleaf, otherwise the most recently modified one is used.
"""

import json
import os
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent
HISTORY_DIR = ROOT / "data" / "history"


def list_companies() -> list[str]:
    return sorted(p.stem for p in HISTORY_DIR.glob("*.json"))


def load_history(company: str) -> Optional[dict]:
    path = HISTORY_DIR / f"{company}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def latest_history() -> Optional[dict]:
    files = list(HISTORY_DIR.glob("*.json"))
    if not files:
        return None
    latest = max(files, key=lambda p: p.stat().st_mtime)
    return json.loads(latest.read_text(encoding="utf-8"))


def _pick_history() -> Optional[dict]:
    company = os.environ.get("HISTORY_COMPANY", "").strip()
    return load_history(company) if company else latest_history()


def _commitment_greeting(history: dict) -> Optional[str]:
    commitments = history.get("commitments") or []
    if not commitments:
        return None
    company = history.get("company", "the company")
    items = []
    for i, commit in enumerate(commitments, 1):
        task = commit.get("task", "")
        owner = commit.get("owner", "")
        deadline = commit.get("deadline", "")
        tail = ""
        if owner:
            tail = f" — {owner}"
            if deadline:
                tail += f", due {deadline}"
        items.append(f"{i}. {task}{tail}")
    body = "\n".join(items)
    plural = "s" if len(commitments) != 1 else ""
    return (
        f"Welcome back. Last time we debriefed {company}, we left "
        f"{len(commitments)} commitment{plural} open:\n{body}\n"
        "Let's check each one before anything new. How did the first one go?"
    )


def _commitment_prompt() -> str:
    return (
        "This may be a repeat debrief for the same company. If the greeting "
        "lists commitments from a previous session, your first task is to check "
        "them one at a time: ask what has happened since, whether each is done, "
        "and whether anything about it is a new risk signal. Only after the "
        "commitments are covered should you move on to listening for new "
        "signals. If a commitment is done, acknowledge it and move to the next "
        "one; log evidence only when its outcome is itself a risk signal."
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


def apply_history(agent: dict) -> bool:
    """Inject the previous session's summary into the agent, in place.

    Returns True when a history file was found and applied, False when there is
    nothing to inject (and the agent is left untouched).
    """
    history = _pick_history()
    if not history or not history.get("commitments"):
        return False
    greeting = _commitment_greeting(history)
    if greeting:
        agent["greeting"] = greeting
    agent["system_prompt"] = (agent.get("system_prompt", "") +
                              "\n\n" + _summary_prompt(history))
    return True
