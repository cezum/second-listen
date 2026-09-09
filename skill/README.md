# Playbook Skill

The agent's brain: an evidence-led post-investment risk playbook with review dimensions, escalation triggers, and human confirmation.

## Contents

- `SKILL.md` — the English playbook template for evidence capture, exception review, and human-approved follow-up actions.
- `LICENSE` — MIT license of the ported template (Copyright (c) 2026 cezum), retained as required for redistribution.

## How the agent uses it

The operational subset is inlined in the agent's system prompt (`app/agents/second-listen.jsonc`, documented in `docs/system-prompt.md`). The governing principle is: **the AI surfaces evidence and suggestions; authorized people make the final risk decision.**

## Pluggable by design

The playbook is a slot, not a fixture. The same agent skeleton works with other checklist-style playbooks — legal case checklists, credit due-diligence lists, safety inspection routines — by swapping the system prompt. Post-investment monitoring is slot #1.
