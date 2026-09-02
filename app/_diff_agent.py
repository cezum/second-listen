"""Compare the local second-listen.jsonc against the agent currently deployed.

Setting AGENT=second-listen makes a bare `python publish.py` PUT over the live
agent, so before flipping that default we must prove local == deployed. If they
differ, publishing would overwrite the working agent with the local copy.
"""
import sys

from lib import aai, load_env, read_agent, stored_agent_id

load_env()


def flatten(value, prefix=""):
    """Flatten nested dicts/lists into {path: leaf} for field-by-field compare."""
    out = {}
    if isinstance(value, dict):
        for key, item in value.items():
            out.update(flatten(item, f"{prefix}.{key}" if prefix else key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            out.update(flatten(item, f"{prefix}[{index}]"))
    else:
        out[prefix] = value
    return out


name = "second-listen"
local = read_agent(name)
agent_id = stored_agent_id(name)
if not agent_id:
    sys.exit(f"No AGENT_ID_{name.upper()} stored in .env")

deployed = aai(f"/agents/{agent_id}")

print(f"agent id : {agent_id}")
print(f"deployed : {deployed.get('name')}")
print(f"local    : {local.get('name')}")
print()

local_fields = flatten(local)
deployed_fields = flatten(deployed)

diffs = []
missing = []
same = []

for key in sorted(local_fields):
    want = local_fields[key]
    got = deployed_fields.get(key, "<<absent>>")
    if got == "<<absent>>":
        missing.append((key, want))
    elif got == want:
        same.append(key)
    else:
        diffs.append((key, want, got))

print(f"--- identical ({len(same)}) ---")
for key in same:
    print("  =", key)

if missing:
    print(f"\n--- in local but NOT deployed ({len(missing)}) ---")
    for key, want in missing:
        shown = str(want)
        print(f"  ? {key}: {shown[:90]}")

if diffs:
    print(f"\n--- DIFFERENT ({len(diffs)}) ---")
    for key, want, got in diffs:
        print(f"  ! {key}")
        print(f"      local    : {str(want)[:160]}")
        print(f"      deployed : {str(got)[:160]}")

print()
if diffs or missing:
    print("VERDICT: LOCAL != DEPLOYED -> publishing would change the live agent")
    sys.exit(1)
print("VERDICT: LOCAL == DEPLOYED -> flipping the default is a safe no-op")
