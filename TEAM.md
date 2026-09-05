# TEAM.md — Second Listen

## Team

- **Team name**: Second Listen
- **Members**: cezum *(TODO: replace with real member names before submission)*
- **Contact**: via GitHub profile

## API paths used

| Path | API | Where |
|------|-----|-------|
| Live debrief | **AssemblyAI Voice Agent API** — one WebSocket (`wss://agents.assemblyai.com/v1/ws`) carrying STT + LLM + TTS, turn detection, barge-in | `app/deployment/browser/` (browser direct), `app/agents/second-listen.jsonc` (agent definition) |
| Upload analysis | **AssemblyAI Universal-2** (v2 async transcription API) + pluggable OpenAI-compatible LLM | `app/transcribe.py`, `app/analyze.py` |

## Project intro

Second Listen is a voice agent for post-investment risk management. After a founder call, the investor debriefs it for two minutes; a structured risk-grading playbook drives follow-up questions, and the session becomes evidence tables, ledger updates, escalation flags, and a downloadable follow-up note. A dual-engine design: live voice for the debrief itself, Universal-2 file-upload analysis (Chinese works) for pre-recorded debriefs — same playbook, two paths.

## Run locally

Requirements: Python 3.9+, no pip install (stdlib only).

```sh
cd app
cp .env.example .env        # add your ASSEMBLYAI_API_KEY
AGENT=second-listen python publish.py   # publish the agent, writes its id to .env
python deployment/browser/server.py     # open http://localhost:3000
```

Optional: `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` in `.env` switch upload-mode analysis from the built-in keyword fallback to an LLM.

## Lowest-friction private trial

For a no-install trial, deploy `app/` to Render using `app/render.yaml`. Set
`ASSEMBLYAI_API_KEY` and a strong `APP_PASSWORD` when Render asks for the
secrets, then share the generated HTTPS URL and password with invited testers.
The page opens in a browser; no GitHub account, Python, or local setup is
needed. The Sample Debrief is available without spending API credits. Live
voice and recording upload consume the configured AssemblyAI/LLM quotas, so
keep the link private and tell testers before they start either mode.

## Zero third-party dependencies

The entire backend is **Python standard library only** — `requirements.txt` installs nothing, all HTTP calls use `urllib`, all audio transport happens in the browser (`AudioContext` + `AudioWorklet`) directly against the AssemblyAI WebSocket. The local server is a thin `ThreadingHTTPServer` that mints 60-second tokens and persists tool calls.
