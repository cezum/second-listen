# Roadmap — hackathon month (Sep 1–30, 2026)

| Week | Milestone | Deliverables |
|---|---|---|
| W1 (9/1–7) | Skeleton + questioning quality | official starter running; system prompt v0.2; questioning-quality test log (text-first: test prompt against the demo transcript in plain chat before wiring voice) |
| W2 (9/8–14) | Act loop | evidence table with timestamped citations; risk ledger persisted to a single JSON file (no DB); escalation banner; drafted follow-up note; Action Items extraction as the one client tool; **file-upload mode**: pre-recorded audio → Universal-2 transcript → same playbook produces signal list + follow-up question list (covers Chinese recordings; no live dialogue for recorded files) |
| W3 (9/15–21) | Memory + polish | cross-debrief commitment tracking via injecting a summary of previous sessions (history file, no vector store); *optional stretch: keyterms hot-update, PII redaction*; demo rehearsal |
| W4 (9/22–30) | Record + submit | ≤5 min video, slides PDF, public repo finalized, buffer ≥3 days |

## Definition of done (MVP)

- Talk 2 minutes → get: evidence table (5 dimensions, timestamped citations), ledger update, escalation flags, action items with owner + deadline.
- Agent follows checklist-driven questioning (not generic chatbot questions).
- Second debrief for the same mock company opens with a commitment check.

## Cross-debrief history file

The commitment check (Definition of done, item 3) reads a per-company summary
from `app/data/history/<company>.json` at publish time — no vector store, no DB
(implemented ahead of W3). Format:

```json
{
  "company": "GreenLeaf",
  "last_debrief_at": "2026-09-01T10:00:00Z",
  "commitments": [
    { "task": "submit written approval for the reallocated grant",
      "owner": "Ben", "deadline": "next Monday" }
  ],
  "signals": ["CFO left, finance unmanaged"]
}
```

- `commitments` → injected into the agent's greeting so the next debrief opens by checking each one (owner + deadline included).
- `signals` → injected into the system prompt so the agent does not re-ask what was already recorded.
- `HISTORY_COMPANY=<company>` selects the file; otherwise the most recently modified one is used. With no file the agent keeps its default greeting (inert until a file appears).
