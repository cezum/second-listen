# Working on this repo

A standard-library Python starter for the AssemblyAI Voice Agent API. An agent is one file in `agents/`; `publish.py` pushes it to the account; the two front doors in `deployment/` decide where it answers.

```
agents/<name>.jsonc        the agent, as the body of POST /v1/agents
lib.py                     env loading, JSONC parsing, AssemblyAI + Twilio calls
publish.py                 python publish.py
import_agent.py            python import_agent.py <id>, playground agent into a file
deployment/browser/        server.py, serves a page and mints session tokens
deployment/telephony/      connect.py, Twilio SIP trunk and number binding
```

## Run

```sh
cp .env.example .env    # ASSEMBLYAI_API_KEY
AGENT=second-listen python publish.py
python deployment/browser/server.py
```

Python 3.9+, no installs. The hackathon agent is `second-listen`; reusable examples include `minimal`, `keyterms`, `turn-taking`, `byo-llm`, `http-tools`, `exa-search`, `airtable-crm`, `cal-booking`, and `dtmf`.

## How it fits together

Agent files are API request bodies. If a field isn't in the [create-agent reference](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/create-agent), it doesn't belong in the file. They use `.jsonc` so each field can carry a comment and a doc link. `parse_jsonc` in `lib.py` strips comments and trailing commas before the file is sent.

`${VAR}` in an agent file is substituted from the environment, the root `.env`, or `agents/<name>.env`, in that order of precedence. Secrets never live in the JSON, and an unresolved variable stops the publish with a message naming it.

Each agent file owns an id, stored as `AGENT_ID_<NAME>`: `agents/http-tools.jsonc` uses `AGENT_ID_HTTP_TOOLS`. Unset, `publish_agent` sends `POST /v1/agents` and writes the returned id under that key. Set, it sends `PUT /v1/agents/{id}`, falling back to a create if that returns 404. A bare `AGENT_ID` overrides every per-file key and is never written to.

The browser defaults to inline mode and sends the reviewed local agent configuration with each session. Stored browser mode and telephony resolve a published id through `stored_agent_id(name)`. Behaviour changes still belong in the agent file rather than in a deployment.

## Rules

- Standard library only. No pip install, no virtualenv, no requirements to keep current.
- Behaviour goes in `agents/*.jsonc`. Runtime changes go in the deployment that owns them. Anything shared goes in `lib.py`, the only module both deployments import.
- `deployment/browser/app.js` is copied from the [JS starter](https://github.com/AssemblyAI/voice-agent-starter-js) and should stay identical to it. Audio and transcript fixes belong there first, then here.
- Prefer `http` tools. Client-executed tools can't be answered on a phone call, and `publish.py` warns about them.
- Voices: only IDs from the documented catalog at https://www.assemblyai.com/docs/voice-agents/voice-agent-api/voices. Never invent one.
- Never move the API key into client code, commit it, or log it. `.env` and `agents/*.env` are gitignored; keep them that way.
- Only use documented endpoints, and keep the doc links in the agent files accurate, since they are how anyone reading the repo finds the reference.
- Voice-first prompt style: short spoken sentences, no visual formatting, no exclamation marks.
- New agent file: name it after the parameter or integration it demonstrates, not the persona. Comment every non-obvious field with a link to the page that defines it, and add a row to `README.md` and `agents/README.md`. Add it to the JS starter too, so the two stay in step.

## Reference

- [Create an agent](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/create-agent) · [Manage agents](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/manage-agents)
- [Tools overview](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/tools/overview) · [HTTP tools](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/tools/http-tools)
- [Turn detection and interruptions](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/turn-detection-and-interruptions)
- [Connect your own LLM](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/connect-your-own-llm)
- [Connect to Twilio](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/connect-to-twilio) · [Use your own number](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/twilio-own-number)

## Deploying

The repository-level `render.yaml` runs the browser deployment in inline mode. Render sets `PORT` and prompts for `ASSEMBLYAI_API_KEY` plus `APP_PASSWORD`. Anyone with both the deployed URL and password, or the phone number, can run sessions billed to that key.
