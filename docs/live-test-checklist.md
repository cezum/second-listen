# Live test checklist

Live voice time is the expensive resource here: every round you forget to
check is another session you have to schedule. This compresses everything that
needs a voice into **one boot and three calls**, plus one Chinese round that
needs no speaking at all.

Run Round 0 to 3 in order. Each round says what to do, what "passed" looks
like, and what to do when it does not.

All commands run from `app/`.

---

## Round 0 — before you speak (~3 min, no microphone)

The point is to keep cloud and local breakage out of your speaking time.

### 0.1 The agent must be alive and carry its tools

This is the one that has bitten twice. `.env` can point at an id that no
longer exists, and a stale agent can still answer calls — just without ever
calling `log_evidence` or `add_action_item`, which leaves the ledger empty and
wastes the whole round.

```sh
AGENT=second-listen python publish.py
```

Then confirm what actually landed:

```sh
python -c "from lib import aai,load_env,stored_agent_id; load_env(); d=aai('/agents/'+stored_agent_id('second-listen')); print(d['name']); print([t['name'] for t in d.get('tools') or []])"
```

| Pass | Fail |
|---|---|
| Prints the name, then `['log_evidence', 'add_action_item']` | `agent_not_found` → publish again; it detects the 404 and creates a fresh one, then re-run this check |
| Publish says `Created` or `Updated` | Prints `[]` → `agents/second-listen.jsonc` lost its `tools` block, restore it before calling |

A warning about tools having no `http` block is expected and harmless: these
are client-side tools, handled by the browser page, so they do not work on a
phone call.

### 0.2 The session service must agree — no microphone needed

REST and the websocket are two different services and they do not always agree.
REST will return the agent happily while the session service answers
`agent_not_found`, and you only find out after you have pressed Start and
started talking. This checks the service the call actually uses.

```sh
AGENT=second-listen python probe_session.py
```

It mints a short token, opens the websocket, sends one `session.update`, and
prints what comes back. No audio is sent, so no speaking time is spent.

| Pass | Fail |
|---|---|
| `session.ready` for the mode you intend to use | `session.error: agent_not_found` → publish again and re-run; if it fails twice, use inline mode below |

`python probe_session.py stored` and `python probe_session.py inline` run a
single mode each.

### 0.2b When the stored agent keeps vanishing: serve it inline

If 0.2 fails more than once in a sitting, stop re-publishing and take the
stored agent out of the loop:

```sh
MODE=inline AGENT=second-listen python deployment/browser/server.py
```

The page then sends `agents/second-listen.jsonc` as the session config, so no
id on the account has to resolve. Tools ride along inside that config —
`app.js` sends `tools: AGENT.config.tools`, and the service echoes them back
under `config.tools` in `session.updated`. That line is the one thing to watch
in inline mode: without it the agent has no tools and the ledger stays empty.

Inline also settles the voice, since the config's `voice.voice_id` is what you
hear. On a stored agent, `output.voice` can end up disagreeing with it.

### 0.3 Start the server

```sh
AGENT=second-listen python deployment/browser/server.py
```

`AGENT` is passed explicitly because the code default is `minimal`, the
starter's example agent — without it the page would serve the wrong agent and
the trial recordings would land under the wrong name. (`app/.env` also sets
`AGENT=second-listen`, but `.env` is gitignored, so a fresh clone has no such
default and the command has to carry it.)

Open <http://localhost:3000>. The banner should read "Second Listen - Debrief
Partner"; if it says anything else you are on the wrong agent — stop and fix
that before speaking. Confirm the Ledger tab says "No records yet" — that is
the clean baseline you want before Round 1.

---

## Round 1 — first debrief, English (~2 min)

**Do:** press Start, then read the monologue from
[`demo-script.md`](demo-script.md) at a natural pace. It is 45 seconds and
buries three signals. Keep talking; let the agent interrupt you.

**Then stop and read the Ledger tab.**

| # | Check | Pass | If it fails |
|---|---|---|---|
| 1 | Checklist-driven questions | It asks who is covering finance since Sarah left, and whether the grant move had written approval | Generic questions ("tell me more") → the playbook is being ignored; tighten `system_prompt` in `agents/second-listen.jsonc` |
| 2 | Evidence rows | 3 rows, each with a quote in your own words | 0 rows → the agent never called the tool; re-check 0.1 |
| 3 | Timestamped citations | Rows read `00:42 · log_evidence`, not `42s` | Wrong format → `stamp()` in `deployment/browser/app.js` |
| 4 | Escalation banner | Red banner names the CFO departure and the grant diversion | No banner → `escalation` stayed false; check the checklist wording in the prompt |
| 5 | Action items with owner + deadline | Each shows both, e.g. `Ben · next Monday` | Missing → the prompt does not insist on both fields |

**Human feel** (the judgement call only a real call can make):

- Does it interrupt at the right moment, or talk over you?
- Are its turns short enough to feel like a colleague, not a report?
- Turn-taking is `min_latency`. If it cuts you off mid-sentence, switch
  `input.transcription_mode` in the agent file to `balanced`.

**Save the result** — this is also your demo footage and your Round 2 input:

```sh
python -c "import json;print(json.dumps(json.load(open('data/ledger.json')),ensure_ascii=False,indent=2))" | head -60
```

---

## Round 2 — commitment check, English (~1 min)

The same call again for the same company. The agent should now open by working
through what was left open last time, which is the third line of the
[roadmap](roadmap.md) definition of done.

### 2.1 Turn Round 1 into a history file

```sh
COMPANY=greenleaf python history_from_ledger.py
```

It reads the most recent ledger session, repacks every `add_action_item` into
`commitments` and every `log_evidence` signal into `signals`, and writes
`data/history/greenleaf.json`.

| Pass | Fail |
|---|---|
| Prints `2 commitment(s), 3 signal(s)` and a `wrote` line | "no sessions" → Round 1 never reached `/api/ledger`, re-check 0.1 |
| | "no add_action_item calls" → you never agreed to a follow-up out loud; do that in Round 1, since the agent only logs actions you accept |

`SESSION=<id>` reads a specific session; `FORCE=1` overwrites; `DRY_RUN=1`
prints instead of writing.

### 2.2 Republish so the greeting picks it up

```sh
AGENT=second-listen COMPANY=greenleaf python publish.py
```

Same reason as above: a bare `python publish.py` would target `minimal` and,
with no `AGENT_ID_MINIMAL` in `.env`, create a throwaway cloud agent instead of
updating Second Listen.

The commitment check is injected at publish time, so publishing again is not
optional. Confirm it took:

```sh
python -c "from lib import aai,load_env,stored_agent_id; load_env(); print(aai('/agents/'+stored_agent_id('second-listen'))['greeting'])"
```

### 2.3 Call again

**Do:** start a new call and say nothing until it finishes greeting you.

| Pass | Fail |
|---|---|
| Opens with "Welcome back… we left N commitments open", lists them with owner and deadline, and asks how the first one went | Still says "Hi, I'm your debrief partner" → the history file was not found at publish time; check `HISTORY_COMPANY` and re-publish |

Then answer one commitment and confirm the Commitments tab reflects it.

To get back to a clean agent, delete `data/history/greenleaf.json` and publish
again.

---

## Round 3 — Chinese comparison (~5 min, no speaking)

**This round needs no microphone.** It runs through file-upload mode, which is
how the Chinese gap gets covered at all: the realtime voice output does not
speak Chinese, but Universal-2 transcribes it.

**Do:** press **Analyze recording** in the header and pick a recorded Chinese
debrief. A previous session recording works — they land in
`app/data/trials/<session-id>/audio.ogg` after a call ends.

| Pass | Fail |
|---|---|
| Transcript comes back correct, `language: zh` | Wrong or empty → check the file has speech, and that `/v2/upload` got a real MIME type (not `application/octet-stream`) |
| Signals and questions render in Chinese | English questions → the `language` was not passed to `analyze.analyze_transcript` |
| Planted signals are caught | Missed → add the wording to `_KEYWORD_RULES` in `analyze.py` |

For the comparison itself, put the same recording through a Chinese voice
assistant and keep both outputs side by side. The claim to test is narrow and
worth being precise about: the assistant transcribes and chats, Second Listen
runs a checklist and hands back evidence, escalation flags, and actions with
owners and deadlines.

---

## Recording the video (≤5 min)

Beat sheet in [`demo-script.md`](demo-script.md). Capture Round 1 and Round 2
on screen — the evidence table, the banner, and the Commitments tab are the
shots that sell it, and they are hard to stage after the fact.

If a take goes badly, re-record just that beat; the ledger accumulates, so
reset it with the reset button on the Ledger tab before a clean full run.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `agent_not_found` | The account drops agents. Publish again — it detects the 404 and creates a new one. Then re-run the 0.1 check. |
| REST says the agent is fine, the call still says `agent_not_found` | The session service disagrees with REST. Run `probe_session.py` (0.2); if it fails twice, restart the server with `MODE=inline` (0.2b). |
| Call connects, tools never fire | In inline mode, `app.js` is not sending `tools` in `session.update` — check `AGENT.config.tools` is populated. In stored mode, re-check 0.1. |
| Call connects, ledger stays empty | The agent has no tools, or the page is not POSTing them. Confirm 0.1 shows both tool names. |
| Upload returns `Transcoding failed` | The upload was sent with the wrong content type. `X-Filename` must carry a real audio extension so the MIME type can be derived. |
| Upload returns `Invalid API key` | `transcribe.py` uses the transcription endpoint, which wants a bare key. A `Bearer` prefix returns 401. |
| Everything works but feels slow | Turn-taking is `min_latency`. Switch to `balanced` in the agent file. |

The account should hold exactly one agent, the one `.env` points at. If
`GET /agents` shows more, the id drifted again and a duplicate was created —
delete the ones with no tools, since the tool-less ones are the stale builds
that silently swallow the ledger. Never delete the id `stored_agent_id()`
returns.
