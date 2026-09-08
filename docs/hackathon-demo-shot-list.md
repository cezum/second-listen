# Hackathon Demo Shot List

Use this checklist with [`hackathon-demo-script-2min.md`](hackathon-demo-script-2min.md).
v7 keeps v5's one-long-live-segment spine, drops the litigation follow-up
to land at 3:44, and rebuilds the outro to mirror the intro's typewriter
card so the video has a matching bookend.

## Before recording

- Start from the blank workspace state.
- Confirm the company field uses a fictional name (`Project 8` / `Project 9`).
- Close developer tools, terminals, API dashboards, and unrelated browser tabs.
- Do not use real company names, real recordings, or real investment information.
- Keep the API key only in the server environment; never show it on screen.

## What was captured (final cut sources)

| Source | Length | Used for |
|---|---|---|
| Live debrief, next-day session (`Project 8`) | 3:09 | Live part 1 [9.5, 135.8] (126.3 s) + Live part 2 [157.7, 186.5] (28.8 s) |
| Upload analysis (`Project 9`) | 1:05 | Upload frame (static, 11.7 s) |
| Live debrief, full session (`Project 8`) | 3:38 | Unused; available as a fallback |
| Two aborted takes | ~30s | Unused |

## Final cut structure (v7)

| Time | Section | Audio | Callout |
|---|---|---|---|
| 0:00–0:17 | Intro A: typewriter card on beige (4 lines, sequential fade-in) | AI narration (NARR_A): problem statement, transcription is solved, judgment is not | — |
| 0:17–0:42 | Intro B: entry screen (static, "two doors") | AI narration (NARR_B): playbook compiled into skills, what the partner does, what is about to happen | — |
| 0:42–2:49 | Live part 1: trial3 [9.5, 135.8] (126.3 s) — natural pacing, no internal cuts. Walks through follow-ups #1, #2, #3. | Real audio. 3 Luke mutes in this segment. | (1) "Prior follow-ups, reopened" @ 0:43–0:53<br>(2) "Reminder set" @ 1:37–1:45<br>Persistent: "LIVE DEBRIEF · PROJECT 8 · SECOND CHECK-IN" bottom-left |
| 2:49–3:18 | Live part 2: trial3 [157.7, 186.5] (28.8 s) — "Since all follow-ups are still in progress, let's move on" / "Was there anything else new..." / "I've set two reminders for you" | Real audio | (3) "Two reminders set" @ 3:02–3:14 |
| 3:18–3:29 | Upload: Project 9 static report frame | AI narration (NARR_UPLOAD): same skills run on a recording — drop in, get the same list | — |
| 3:29–3:44 | Outro: typewriter card on beige (5 lines + footer, sequential fade-in) | AI narration (NARR_OUT): everything is on the record, next week the partner opens with them, Second Listen | — |

Total: 225 s = 3:44.

## Why the structure is what it is

- **Live is the spine.** Both halves of the live section are trial3; nothing
  else is mixed in. v3/v4's multi-segment stitching read as "edited
  highlights" and was rejected. The litigation follow-up in the middle of
  trial3 ("no new developments" / "nothing further right now") is the only
  cut — it is dead air that the agent follows with "Since all follow-ups
  are still in progress, let's move on", so the visual cut is invisible.
- **Three Luke mutes in a single pause.** The agent addresses the investor by
  name twice while waiting for an answer on the first follow-up, and the
  investor's discarded half-answer falls in the same pause. All three are
  muted because none carries information; the agent says "I'm sorry, I
  didn't catch that" anyway.
- **Outro mirrors intro.** Same beige ground, same Georgia headline + italic
  body, lines revealed at 0.4 / 3.0 / 6.2 / 9.6 s. The intro names the gap
  ("that is not solved"); the outro names the artifact ("everything is on
  the record"). Together they are a single argument.
- **Persistent corner label.** A small `LIVE DEBRIEF · PROJECT 8 · SECOND
  CHECK-IN` tag at the bottom-left keeps the viewer oriented through the
  long static-looking section.

## Editing rules that were applied

- Browser chrome is cropped out (`crop=1920:884:0:124`); the page is centered
  on a beige canvas (`pad=1920:1080:0:98:color=0xF6F4EF`).
- The live section runs at 1.0x — no speed ramps.
- Audio is the original recorded conversation in the live section (the
  investor's voice + agent TTS). AI narration is used only for the intro
  A/B, the upload, and the outro.
- The litigation follow-up (trial3 abs [135.8, 157.7]) is dropped; the two
  halves are stitched at agent prompts followed by silence, so the cut is
  invisible.
- The three Luke mutes (trial3 abs [23.48, 23.95], [29.02, 29.62],
  [31.18, 31.82]) are audio-only. The product's own UI transcript of these
  moments ("Investor · due next week", "Keep that reminder for next week
  underneath me") is still visible; redrawing it would obscure real
  product text.
- Three on-screen callouts use `drawtext` (Georgia 26 px, dark text, beige
  box) with `enable='between(t,start,end)'` in segment-local time.
- No music.

## Total runtime is 3:44 — this is a tradeoff, not an oversight

- v5 was 3:57. v6 had a bug that let the live segment run 11 s over and
  ended at 3:47. v7 fixes the bug and adds the closing-card narration, and
  lands at 3:44.
- If a hard 3-minute cap is required, the next step is to drop the live
  part 2 entirely (loses the "two reminders set" callout — not recommended)
  or to compress intro B / upload / outro by ~45 s combined.
- If a fully uncut 4:01 version is preferred, set `TRIM_LITIGATION = False`
  at the top of `build_demo_v7.py` and re-run.
- v3 / v4 / v5 still exist on disk for shorter-length fallbacks.

## Final quality check (verified on the finished v7 video)

- Value proposition is on screen and spoken in the first 17 seconds
  (transcription is solved, judgment is not, playbook compiled into skills).
- Live segment runs continuously for 155 s (in two parts, stitch invisible).
- The first risk never appears before its supporting sentence is spoken.
- The words `Project 8` and `fictional` are visible and spoken.
- The video includes a real live result and a real upload result.
- The agreed actions are created on camera with owner, due, and agreed-at
  meta visible.
- The follow-up carryover is on camera: the live segment's "Previous
  follow-ups" panel is exactly the agreed actions the next-day session
  needs to close.
- All three "Luke" name cues and the investor's half-answer are inaudible.
  The product's own UI transcript of them is still visible (product
  rendering, not editable).
- No API key, real recording, local path, browser chrome, or private data
  appears.
- The transferable industries are listed on the closing card.
- Intro and outro share the same visual grammar (beige / Georgia / line
  reveal cadence).

## Build pipeline

- Script: the v7 build script (kept locally with the source clips, not in this repo; Python 3.13 + edge-tts).
- 6 video segments (intro A, intro B, live part 1, live part 2, upload,
  outro), all forced 30 fps, video-only.
- 5 audio segments (TTS for intro A/B/upload/outro, original trial3
  audio with 3 Luke mutes for the live section), joined by ffmpeg concat.
- Final mux adds fade in / fade out.
- One switch at the top of the script — `TRIM_LITIGATION` — toggles
  between the 3:44 cut and the 4:01 uncut cut.
