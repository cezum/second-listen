# Hackathon Demo Shot List

Use this checklist with [`hackathon-demo-script-2min.md`](hackathon-demo-script-2min.md).
The final cut is a 2:25 submission video built from real screen recordings —
no scripted sample playback. v3 replaced v1's full AI narration with the
actual recorded conversation in the live and closure sections.

## Before recording

- Start from the blank workspace state.
- Confirm the company field uses a fictional name (`Project 8` / `Project 9`).
- Close developer tools, terminals, API dashboards, and unrelated browser tabs.
- Do not use real company names, real recordings, or real investment information.
- Keep the API key only in the server environment; never show it on screen.

## What was captured (final cut sources)

| Source | Length | Used for |
|---|---|---|
| Live debrief, full session (`Project 8`) | 3:38 | Live A [10,32] + Live B [66,126] |
| Live debrief, next-day session (`Project 8`) | 3:09 | Closure [18,30] — previous follow-ups listed at open |
| Upload analysis (`Project 9`) | 1:05 | Upload [0,20] |
| Two aborted takes | ~30s | Unused |

## Final cut structure (v3)

| Time | Section | Audio | Callout |
|---|---|---|---|
| 0:00–0:20 | Intro: entry screen (two doors) | Narration | — |
| 0:20–0:42 | Live A: greeting + first description → R-01 filed | Real audio | "Signals filed, with the quote" @ 0:36–0:42 |
| 0:42–1:02 | Live B: IPO slip → REVIEW flag → buyback question → A-01/A-02 created | Real audio | "Agreed action - owner and deadline" @ 1:24–1:34 |
| 1:02–1:14 | Closure: Welcome back + 4-item previous follow-ups | Real audio | "Prior follow-ups" @ 1:03–1:12 |
| 1:14–1:19 | Transition: entry screen | Narration | — |
| 1:19–1:39 | Upload: Project 9 full report | Narration | — |
| 1:39–1:45 | Closing card | Silent | — |

Total: 145 s = 2:25.

## Editing rules that were applied

- Browser chrome is cropped out (`crop=1920:884:0:124`); the page is centered
  on a beige canvas (`pad=1920:1080:0:98:color=0xF6F4EF`).
- The live sections run at 1.0x — no speed ramps. The two stretch breaks are
  intentional (skip mid-sentence answer, land on agreed action).
- Audio is the original recorded conversation in the live and closure
  sections (the investor's voice + agent TTS). AI narration is used only for
  the intro, transition, upload, and closing.
- Three on-screen callouts use `drawtext` (Georgia 26 px, dark text, beige box)
  with `enable='between(t,start,end)'` in segment-local time, so they appear
  exactly when the corresponding mechanism fires.
- No music.

## Fallback (not needed in the final cut)

If a live run had been unstable, the plan was to use a successful
recording-upload result as the integration proof and the full labeled sample
for the product story. The live takes were stable, so the sample is unused.

## Final quality check (verified on the finished video)

- The first risk never appears before its supporting sentence is spoken.
- The words `Project 8` and `fictional` are visible and spoken.
- The video includes a real live result and a real upload result.
- The agreed action is created on camera with owner, due, and agreed-at meta
  visible (the core "voice-in, quotes-kept" promise).
- The follow-up carryover is on camera: the closure shot's "Previous
  follow-ups" list is exactly the agreed actions just created in live B.
- No API key, real recording, local path, browser chrome, or private data
  appears.
- The transferable industries are listed on the closing card.

## Build pipeline

- Script: `私有库/_demo_build/build_demo_v3.py` (Python 3.13 + edge-tts).
- Per-segment video encodes (all forced 30 fps, video-only). Per-segment
  audio (original for live/closure; TTS + silence for intro/trans/upload/outro).
- `ffmpeg -f concat -c copy` stitches the video segments; audio is built
  separately and `amix`-ed per segment before concat.
- Final mux adds fade in / fade out.