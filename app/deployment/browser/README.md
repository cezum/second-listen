# Browser

Serves a page with a call button. Useful for iterating on an agent before putting it on a phone number.

## 1. Publish an agent

```sh
AGENT=http-tools python publish.py
```

## 2. Run it

```sh
python deployment/browser/server.py
```

Open http://localhost:3000, enter the investee company name, and start a call
or upload a recording. Both paths use the same risk-review playbook; an upload
also checks that company's saved follow-ups when available.

## 3. Iterate

Edit the file in [agents/](../../agents/), run `python publish.py`, and start another call. When the agent behaves the way you want, see [deployment/telephony](../telephony/).

---

## What it does

By default the server runs inline: it reads `agents/<AGENT>.jsonc` and sends the prompt, voice and tools with each session, so a fresh clone works with only an API key. With `MODE=stored` it connects to an already published agent id instead.

`GET /token` proxies AssemblyAI's token endpoint using your key and returns a 60 second session token. The key is never sent to the page.

The page streams the microphone as 24 kHz PCM16 over `wss://agents.assemblyai.com/v1/ws`, plays the reply back, and discards queued audio when you interrupt. Capture and playback each run in their own AudioContext with a resampling worklet, so a browser that refuses to open a context at 24 kHz still sounds right.

An uploaded recording requires the same company field as a live debrief. The
report is scoped to that company and compares the transcript with saved prior
follow-ups, but recording candidates are not automatically written to the live
debrief ledger.

The side pane has two tabs. Events lists every websocket frame in both directions, with audio runs collapsed into counts. Agent shows the published agent as the API stored it, read only, served by `GET /agent`. Tool header values and LLM keys are stripped from that response, but the system prompt is in it, so on a public deployment anyone opening the page can read it.

In `MODE=stored` the session message contains only `{ agent_id }`; prompt, voice, tools and turn detection are read from the stored agent, which is why the browser and the phone behave the same. Inline mode sends the config from `agents/<AGENT>.jsonc` directly.

## Environment

| | |
| --- | --- |
| `ASSEMBLYAI_API_KEY` | Required. Stays in this process. |
| `AGENT` | Which file in `agents/` to serve. Defaults to `second-listen`. |
| `AGENT_ID_<NAME>` | The id `python publish.py` saved for that file. Connected to as it is. |
| `AGENT_ID` | Overrides the per-file keys, for serving one specific agent. |
| `MODE` | `inline` (default) sends the local `agents/<AGENT>.jsonc` with each session; `stored` connects to a published agent id. |
| `PORT` | Defaults to 3000. If the port is occupied, startup fails with the exact port and a process-conflict message. |
| `HOST` | Defaults to `127.0.0.1`. Set `0.0.0.0` when a container platform routes to the port. |
| `APP_PASSWORD` | Optional. When set, all application endpoints require HTTP Basic auth with this password. |
| `VOICE_SESSION_MAX_DURATION_SECONDS` | Defaults to 300. Limits a completed Voice Agent session to 60–300 seconds; larger or invalid values safely fall back to 300. |
| `DATA_DIR` | Root for ledger, history, archives and transcript cache. Use a mounted persistent path for durable hosted data. |
| `REQUIRE_HTTPS` | Set to `1` for remote deployments; requests without HTTPS forwarding are rejected. |

## Editing the page

The server is [server.py](server.py), the page is [index.html](index.html) and the client is [app.js](app.js), all served as they are. Save and refresh.

## Hosting

The repository-level [`render.yaml`](../../../render.yaml) is configured for one-click deploys. Render prompts only for `ASSEMBLYAI_API_KEY` during Blueprint creation and sets `PORT` itself. `HOST` is preset to `0.0.0.0` in the Blueprint — containers must listen on all interfaces — while local runs stay on loopback. `AGENT=second-listen` and `MODE=inline` are explicit defaults. For the public contest demo, token minting is limited to two per visitor and six total per 15 minutes; uploads are limited to one per visitor and three total per hour.

Inline mode sends the reviewed local agent configuration with every session and does not create a stored agent during deployment. If you intentionally switch to `MODE=stored`, set `AGENT_ID` to an agent you already published and tested.

The default `app/data/` directory is local to the process. A hosted deployment
must mount durable storage or use an external data store if ledger history,
follow-up status and archived recordings must survive restarts.

Anyone who has both the URL and the Basic Auth password can start sessions billed to your key.
