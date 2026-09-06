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

## Progress log

- 2026-09-01/02 — W1 done (skeleton, prompt v0.1→v0.2 text-first, voice
  re-test pass); W2 delivered ahead of plan: evidence table, ledger,
  escalation banner, Action Items, auto-archive, file-upload mode.
- 2026-09-03 — W3 mechanisms live: cross-debrief history file + commitment
  check (injection verified end-to-end on 衡远医疗, 2 commitments);
  conversation quality rounds W2–W8 archived; prompt v0.3→v0.4 (short quotes,
  action-item discipline, single reply after batch logs, plain English);
  min_silence tuned 1000→650→800; front-end semantic gate retired as the
  default turn-taking approach (inline mode is the browser baseline).
- 2026-09-04 — Follow-up note delivered (GET /api/note → downloadable
  Markdown per company); Ledger is the default side pane; file-upload mode
  re-verified end-to-end on a Chinese recording and the no-LLM fallback now
  covers the demo script's signals in Chinese. Remaining: voice pass of v0.4
  and of the commitment check (Round 2), demo rehearsal/video, slides,
  public-repo finalization (frozen until the project is finished).
- 2026-09-06 — Live follow-up replies no longer get mistaken for duplicate
  burst replies after a client-side tool result; fixed VAD thresholds were
  removed so `min_latency` can use the service's adaptive turn pacing. Upload
  analysis now replaces the right-side risk note in place, reusing the same
  card shell and section hierarchy while the left input card stays visible.
