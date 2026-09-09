# lablab submission copy — Second Listen

> Copy-paste source for the lablab "Submit project" form. Verified against the
> official guidelines on 2026-09-08: title ≤50 chars, short description ≤255
> chars, long description ≥100 words.

## Title (≤50 chars)

```
Second Listen
```

## Short description (≤255 chars — 251 used)

```
Second Listen turns spoken post-investment debriefs into structured evidence. Powered by AssemblyAI Voice Agents and Universal-2, it captures risk signals, asks focused follow-ups, records agreed actions, and carries open items into the next check-in.
```

## Long description (≥100 words — 235 used)

```
Every fund tracks metrics. Nobody captures what they hear. Post-investment risk arrives through two channels: dashboard signals, which monitoring tools already cover, and conversation signals - a CFO leaving, grant money quietly moved to payroll, a lawsuit mentioned in passing - which exist only in conversation and decay with memory before any form captures them.

Second Listen closes that gap. After a founder call, board meeting or site visit, the investor talks to the agent at a natural pace, casually retelling what happened. A post-investment risk playbook - evidence dimensions and an escalation checklist - guides the live agent: it listens for risk signals hidden in small talk, asks focused follow-up questions one at a time, and files each confirmed signal with a short quote and session-relative capture time. Checklist triggers are flagged for human review. When the investor explicitly agrees to follow up, the agent records an action with an owner and a due date. Each company keeps one JSON history file, so the next debrief opens by reopening the previous session's open actions. The submission video shows a real second check-in, with one quiet section removed for length.

A second engine covers recordings. Universal-2 transcribes the file (Chinese works today), then the same evidence dimensions produce candidate signals, escalation flags and follow-up questions. A configured OpenAI-compatible LLM performs the full upload review; without one, a deterministic keyword fallback marks candidates for human review. The backend is Python standard library only - requirements.txt installs nothing. The playbook is MIT-licensed; post-investment is the first domain slot.
```

## Tracks & technologies (suggested picks)

- **Tracks**: Voice Agents · Fintech (or "Enterprise / Productivity")
- **Technologies**: AssemblyAI · Voice Agent API · Realtime STT · Python · WebSocket · JavaScript

## Media assets (ready)

- Cover image 16:9 → `slides/cover_16x9.png` (1920×1080)
- Slide deck PDF → `slides/SecondListen_slides.pdf` (11 pages, 16:9)
- Demo video → `demo/SecondListen_demo_v8.mp4` (3:44, 1080p)

## Submission links (verified)

- GitHub repository: `https://github.com/cezum/second-listen`
- Video presentation (YouTube Unlisted): `https://youtu.be/51TKhR5Vg48`
- Demo application (Render): `https://second-listen-wcap.onrender.com`

The YouTube video is 3:45, under the LabLab five-minute limit. The repository is
public and the Render health check is passing anonymously.
