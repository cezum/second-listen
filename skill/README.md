# Playbook Skill

The agent's brain: a post-investment risk grading framework — three-level grading, five evidence dimensions, and an executable escalation checklist.

## Contents

- `SKILL.md` — the playbook itself, ported from the author's separately published open template `postinvestment-risk-grading` (v1.0.0, Chinese). The template is published for any PE/VC or state-backed investment institution to copy and customize; this repo uses it as the first "slot".
- `LICENSE` — MIT license of the ported template (Copyright (c) 2026 cezum), retained as required for redistribution.

## How the agent uses it

The English adaptation of this playbook is inlined in the agent's system prompt (`app/agents/second-listen.jsonc`, documented in `docs/system-prompt.md`). The principle carried over from the template: **the AI surfaces evidence and suggestions; humans assign the grade.**

## Pluggable by design

The playbook is a slot, not a fixture. The same agent skeleton works with other checklist-style playbooks — legal case checklists, credit due-diligence lists, safety inspection routines — by swapping the system prompt. Post-investment monitoring is slot #1.
