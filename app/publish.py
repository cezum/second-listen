#!/usr/bin/env python3
"""Push agents/<name>.jsonc to your AssemblyAI account.

    python publish.py
    AGENT=exa-search python publish.py

The first run creates the agent and writes AGENT_ID_<NAME> to .env. Later runs
update that same agent, so each file keeps its own agent and a browser tab or
phone number pointed at one picks up the change on the next call.
"""

import os
import sys

from lib import ApiError, aai, ensure_agent, load_env, read_agent, required
from history import apply_history


def self_check(agent_id: str, local: dict) -> bool:
    """Read the published agent back and compare it with the file.

    A 200 from PUT only means the write was accepted. Without this, a prompt
    that did not land looks like a successful publish and turns up later as an
    agent still answering in last week's wording.
    """
    remote = aai(f"/agents/{agent_id}")
    checks = (
        ("name", remote.get("name"), local.get("name")),
        ("system_prompt", remote.get("system_prompt"), local.get("system_prompt")),
        ("tools", [t.get("name") for t in remote.get("tools", [])],
         [t.get("name") for t in local.get("tools", [])]),
    )
    ok = True
    for label, got, want in checks:
        if got != want:
            if label == "system_prompt":
                print(f"  {label}: local {len(str(want))} chars, "
                      f"remote {len(str(got))} chars")
            else:
                print(f"  {label}: local {want!r}, remote {got!r}")
            ok = False
    print(f"Self-check {'passed' if ok else 'FAILED'} - agent {agent_id} read back")
    return ok


def main() -> None:
    load_env()
    required("ASSEMBLYAI_API_KEY", "get one at https://www.assemblyai.com/dashboard/api-keys")

    name = os.environ.get("AGENT", "minimal")
    agent = read_agent(name)
    if apply_history(agent):
        print("Injected commitment check from data/history/")
    result = ensure_agent(agent, name=name)

    verb = "Created" if result["created"] else "Updated"
    print(f'{verb} "{agent["name"]}" from agents/{name}.jsonc')
    print(f"{result['key']}={result['id']}")
    if not result["saved"]:
        print(f"Could not write .env. Set {result['key']}={result['id']} yourself, "
              "or the next run publishes another agent.")
    if not self_check(result["id"], agent):
        sys.exit(f"Published agent does not match agents/{name}.jsonc")

    # Tools with an http block are called by AssemblyAI, so they work in a
    # browser tab and on a phone call. Anything else needs whoever holds the
    # session to answer it, and a phone call has nobody.
    unanswered = [tool["name"] for tool in agent.get("tools", []) if not tool.get("http")]
    if unanswered:
        have = "have" if len(unanswered) > 1 else "has"
        print(f"\nWarning: {', '.join(unanswered)} {have} no http block, "
              "so nothing answers it on a phone call.")


if __name__ == "__main__":
    try:
        main()
    except ApiError as err:
        sys.exit(str(err))
