# Second Listen

> *You said it out loud. You didn't realize it was a signal.*
>
> Every VC tracks metrics. Nobody captures what they hear.

**Second Listen** is a voice agent for post-investment risk management. After a founder call, board meeting, or site visit, the investor talks to it for two minutes — casually retelling what happened. The agent, powered by a structured risk-grading playbook, listens for risk signals hidden in small talk, asks checklist-driven follow-up questions, and turns the debrief into evidence tables, ledger updates, and escalation flags.

Built for the [lablab.ai × AssemblyAI Voice Agent Hackathon](https://lablab.ai/ai-hackathons/assemblyai-voice-agent-hackathon) (Sep 1–30, 2026).

## Why voice

Post-investment risk signals come in two channels:

- **Dashboard signals** (revenue decline, runway < 6 months) — visible in KPI reports, already covered by portfolio monitoring tools.
- **Conversation signals** (key-person departure, funds used outside the agreed purpose, litigation) — they only surface in conversations. By the time quarterly review forms get filled, memory has eaten half the evidence.

Second Listen covers the second channel: the gap between "the conversation happened" and "the signal is in the ledger".

## How it works

1. **Debrief** — after a call, press and talk for ~2 minutes.
2. **Interrogate** — the agent follows the playbook's escalation checklist ("Who's covering finance since the CFO left? Was there written approval for moving the grant money?"), one question at a time.
3. **Record** — produces an evidence table with timestamps, a risk-ledger update, escalation flags per policy, and a downloadable Markdown follow-up note per company. The AI surfaces evidence and suggestions; **humans grade**.

Prefer not to talk? **Analyze recording** uploads a pre-recorded debrief (Chinese works too): Universal-2 transcribes it and the same playbook returns a signal list plus follow-up questions — no live dialogue needed.

## Tech

- [AssemblyAI Voice Agent API](https://www.assemblyai.com/docs/voice-agents/voice-agent-api) — one WebSocket for STT + LLM + TTS, turn detection, barge-in, tool calling
- Playbook skill: a structured risk-grading framework (three-level grading, five evidence dimensions, escalation checklist) injected as the agent's system prompt
- The agent is live in `app/` today: evidence tables, risk-ledger updates, Action Items, file-upload analysis, and cross-debrief commitment tracking (a per-company history file) are implemented and voice-tested across eight archived rounds. Keyterms hot-update and PII redaction remain optional — see [roadmap](docs/roadmap.md)

## Repo layout

```
docs/system-prompt.md   the agent's playbook prompt (v0.4, evolving)
docs/demo-script.md     the 45-second debrief monologue with buried signals
docs/demo-script-zh.md  the same monologue in Chinese, for the comparison round
docs/roadmap.md         build milestones for the hackathon month
docs/live-test-checklist.md
                        one boot, three calls: everything that needs a voice,
                        with pass/fail for each check
skill/                  the playbook skill (ported from the author's published MIT risk-grading template)
app/                    agent implementation — the AssemblyAI starter plus the Second Listen agent
```

## Cross-debrief memory

A second debrief for the same company opens with a commitment check. The previous session's summary lives in one JSON file per company under `app/data/history/` — no database, no vector store:

```json
{
  "company": "Project 8",
  "last_debrief_at": "2026-09-01T10:00:00Z",
  "commitments": [
    { "task": "submit written approval for the reallocated grant",
      "owner": "Ben", "deadline": "next Monday" }
  ],
  "signals": ["CFO left, finance unmanaged"]
}
```

`commitments` drive the opening check (owner + deadline included); `signals` stop the agent from re-asking what was already recorded. Publish with `HISTORY_COMPANY=project-8 python publish.py`, or let it pick the most recently modified file. With no file there is no check — the mechanism is inert until a file appears.

After a live debrief, build the file from the session's own tool calls instead of writing it by hand:

```sh
COMPANY=project-8 python history_from_ledger.py   # in app/
COMPANY=project-8 python publish.py               # the check is injected at publish time
```

It repacks the ledger's `add_action_item` calls into `commitments` and its `log_evidence` signals into `signals`, reading the most recent session unless `SESSION=<id>` says otherwise. `FORCE=1` overwrites, `DRY_RUN=1` prints instead of writing.

## Status

Core product complete: playbook-driven live debrief (evidence, ledger,
escalation, action items), file-upload mode for recorded/Chinese debriefs,
downloadable follow-up notes, and cross-debrief commitment checks all
implemented and verified (Round 2's check is verified at the publish/greeting
layer; a full voice pass is pending). Remaining: demo video + submission
materials (out of scope for the repo's core work).

## License

MIT — see [LICENSE](LICENSE). The playbook skill keeps the original template's MIT notice in `skill/LICENSE`.
