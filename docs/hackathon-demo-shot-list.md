# Hackathon Demo Shot List

Use this checklist with [`hackathon-demo-script-2min.md`](hackathon-demo-script-2min.md).
The v5 cut is built around one long, uncut live debrief — the user's call
that trial3's natural pacing is the strongest piece of evidence the product
has, so it should run nearly in full. v3/v4's Live A + Live B + Closure
construction was the wrong shape.

## Before recording

- Start from the blank workspace state.
- Confirm the company field uses a fictional name (`Project 8` / `Project 9`).
- Close developer tools, terminals, API dashboards, and unrelated browser tabs.
- Do not use real company names, real recordings, or real investment information.
- Keep the API key only in the server environment; never show it on screen.

## What was captured (final cut sources)

| Source | Length | Used for |
|---|---|---|
| Live debrief, next-day session (`Project 8`) | 3:09 | Live [9.5, 186.5] (177 s) — played almost in full |
| Upload analysis (`Project 9`) | 1:05 | Upload frame (static, 11.7 s) |
| Live debrief, full session (`Project 8`) | 3:38 | Unused in v5; available as a fallback |
| Two aborted takes | ~30s | Unused |

## Final cut structure (v5)

| Time | Section | Audio | Callout |
|---|---|---|---|
| 0:00–0:17 | Intro A: typewriter card on beige (4 lines, sequential fade-in) | AI narration (NARR_A): problem statement, transcription is solved, judgment is not | — |
| 0:17–0:42 | Intro B: entry screen (static, "two doors") | AI narration (NARR_B): playbook compiled into skills, what the partner does, what is about to happen | — |
| 0:42–2:59 | Live: uncut trial3 [9.5, 186.5] with original audio, natural pauses preserved | Real audio (investor + agent TTS); 'Luke' name cue muted | (1) "Prior follow-ups, reopened" @ 0:43–0:53<br>(2) "Reminder set" @ 1:37–1:45<br>(3) "Two reminders set" @ 3:24–3:36<br>Persistent: "LIVE DEBRIEF · PROJECT 8 · SECOND CHECK-IN" bottom-left |
| 2:59–3:51 | Upload: Project 9 static report frame | AI narration (NARR_UPLOAD): same skills run on a recording — drop in, get the same list | — |
| 3:51–3:57 | Closing card | Silent | — |

Total: 237 s = 3:57.

## Why the structure is what it is

- **No Live A / Live B split.** v3 used trial (`Project 8`, full session) for the
  intro to live dynamics and trial3 (next-day) for the follow-up closure.
  Stitching three segments together reads as "edited highlights" — busy, no
  single thread. v5 uses trial3 only. The whole second check-in is one
  continuous experience, and the lead-in narration already told the viewer what
  it is.
- **No transition card.** The upload mode is mentioned once, in one sentence,
  over one static frame. It is not the story; it does not get a transition.
- **Live segment runs at 1.0x, pauses preserved.** The user explicitly asked
  to keep the natural rhythm. The first 9.5 s of dead air and the tail after
  186.5 s are trimmed; everything in between is original pace, including the
  5-second waits for "I'm sorry, I didn't catch that" type re-prompts.
- **Three on-screen callouts instead of two.** v3/v4 had two; v5 adds
  "Prior follow-ups, reopened" at the very top of the live segment so the
  viewer knows what they is watching in the first 10 seconds.
- **Persistent corner label.** A small `LIVE DEBRIEF · PROJECT 8 · SECOND
  CHECK-IN` tag at the bottom-left keeps the viewer oriented through the
  long static-looking section.

## Editing rules that were applied

- Browser chrome is cropped out (`crop=1920:884:0:124`); the page is centered
  on a beige canvas (`pad=1920:1080:0:98:color=0xF6F4EF`).
- The live section runs at 1.0x — no speed ramps.
- Audio is the original recorded conversation in the live section (the
  investor's voice + agent TTS). AI narration is used only for the intro
  A/B, the upload, and is silent on the closing card.
- Only the leading and trailing dead air of trial3 is trimmed (absolute
  [0, 9.5] and [186.5, end]). All inner pauses are preserved.
- The 'Luke' name cue (trial3 absolute [23.5, 23.94] s — the agent's way of
  addressing the investor at the start of the first follow-up) is muted.
  Audio only; the product UI's transcript still shows the name. That is the
  product's own rendering and cannot be removed without drawbox masking,
  which the user has not asked for.
- Three on-screen callouts use `drawtext` (Georgia 26 px, dark text, beige
  box) with `enable='between(t,start,end)'` in segment-local time.
- No music.

## Total runtime is 3:57 — this is a tradeoff, not an oversight

- v3 was 2:25. The user's feedback was "feels edited, busy, no flow".
  v4 went to 2:44. v5 goes to 3:57 because the live segment is now 177 s.
- This is the cost of "play trial3 complete". If the submission has a hard
  2- or 3-minute cap, the v5 cut will not fit; the next step is to trim the
  middle of trial3 (e.g. drop the litigation follow-up around absolute
  135.8–157.7 s — "no new developments" / "nothing further right now" —
  and stitch the two halves). That would cut ~22 s, landing at 3:35.
  Cutting more (e.g. ending live after the second follow-up) loses the
  "two reminders set" callout and is not recommended.
- v3 still exists at `SecondListen_demo_v3.mp4` (2:25, narrated-heavy) for
  situations where 3 minutes is the absolute ceiling.

## Final quality check (verified on the finished v5 video)

- Value proposition is on screen and spoken in the first 17 seconds
  (transcription is solved, judgment is not, playbook is compiled into skills).
- Live segment runs continuously for 177 s with no internal cuts.
- The first risk never appears before its supporting sentence is spoken.
- The words `Project 8` and `fictional` are visible and spoken.
- The video includes a real live result and a real upload result.
- The agreed actions are created on camera with owner, due, and agreed-at
  meta visible (the core "voice-in, quotes-kept" promise).
- The follow-up carryover is on camera: the live segment's "Previous
  follow-ups" panel is exactly the agreed actions the next-day session
  needs to close.
- The 'Luke' name cue is inaudible. The product's own transcript of it
  remains visible on screen (product rendering, not editable).
- No API key, real recording, local path, browser chrome, or private data
  appears.
- The transferable industries are listed on the closing card.

## Build pipeline

- Script: `私有库/_demo_build/build_demo_v5.py` (Python 3.13 + edge-tts).
- 5 video segments (intro A text card, intro B entry screen, live trial3,
  upload Project 9 frame, outro card), all forced 30 fps, video-only.
- 5 audio segments (TTS for intro A/B/upload, original trial3 audio with
  'Luke' muted for live, silence for outro), joined by ffmpeg concat.
- Final mux adds fade in / fade out.