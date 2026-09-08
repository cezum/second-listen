# Hackathon Demo Script — Second Listen (v5 cut, 3:57)

This is the narration script of the v5 submission video. Project 8 is a
fictional portfolio company; the upload section uses Project 9, a second
fictional case, to show that the upload path is company-agnostic.

Everything on screen is a real run: the live path is the AssemblyAI Voice Agent
WebSocket, and the upload path is a real Universal-2 transcription + analysis.
No scripted sample playback is used in the final cut.

Audio policy: AI narration (en-US-AndrewNeural) over the intro A/B and the
upload section; the live section uses the actual recorded conversation
(investor's voice + agent TTS), not a voiceover; the closing card is silent.
Three on-screen callouts highlight the key moments, and a small persistent
"live-debrief" tag anchors the viewer during the long live section.

One name cue in the recorded TTS is muted: the "Luke" name cue that opens
the first follow-up in the live segment.

| Time | Screen | Audio |
|---|---|---|
| 0:00–0:17 | Intro A: typewriter card on beige. Four lines appear sequentially: "Every check-in ends the same way." / "The conversation happened." / "The judgment is still trapped inside it." / "Transcription is solved. Judgment is not." | Narration: Every check-in call ends the same way. The conversation happened — but the judgment is still trapped inside it. Transcription is solved. Knowing what matters, what needs follow-up, and what you are exposed to if nobody wrote it down — that is not. |
| 0:17–0:42 | Intro B: product entry (two doors: Start debrief / Upload a recording) | Narration: So we took a real post-investment playbook and compiled it into skills the partner runs live: file every signal with the quote it came from, escalate anything that crosses a red line, and turn each answer into an action with an owner and a deadline. This is Second Listen. What follows is a second check-in — the partner opens it by reopening last week's follow-ups, one at a time. |
| 0:42–2:59 | Live: trial3 next-day session [9.5 s, 186.5 s] — natural pacing, no internal cuts. Right panel shows the four previous follow-ups from the prior check-in. Conversation walks through them one by one; agent files signals and creates two new agreed actions with owner, due, and agreed-at metadata. | Real audio (investor + agent). "Luke" name cue is muted. Callout "Prior follow-ups, reopened" @ 0:43–0:53. Callout "Reminder set" @ 1:37–1:45. Callout "Two reminders set" @ 3:24–3:36. Persistent bottom-left tag: LIVE DEBRIEF · PROJECT 8 · SECOND CHECK-IN. |
| 2:59–3:51 | Upload: Project 9 static result frame — 9 signals / 7 to review / 9 questions, with R-01 (compliance red line — guaranteed return / insider info), R-02 (team — key personnel loss / core role vacancy), R-03 (financial health — funds used outside the agreed purpose) | Narration: The same skills also run on an uploaded recording — drop in the file, get the same risk list, the same follow-ups, the same open questions. |
| 3:51–3:57 | Closing card | Silent. Text: Second Listen. — Remember what changed. Verify what matters. Same method — project · customer success · compliance reviews. Built for the lablab.ai x AssemblyAI hackathon — 2026. |

## Notes

- The live segment runs at 1.0x for 177 seconds, no internal cuts. Only the
  leading 9.5 s of dead air and the trailing tail are trimmed. Natural pauses
  inside the conversation are preserved.
- Why the live segment is so long: the user explicitly rejected the v3/v4
  multi-segment stitching as feeling "edited, busy, no flow". trial3 has
  natural internal drama (the agent asking for a status, the user saying "I
  still need to check", the second reminder being set on the same call) that
  is the strongest evidence the product exists. Cutting it into pieces broke
  the experience.
- Total runtime is 3:57, which exceeds typical 2- or 3-minute submission
  caps. The user chose completeness over length. If a hard 3-minute cap is
  required, the next-best edit is to drop the litigation follow-up
  (trial3 absolute [135.8, 157.7] s — "no new developments" /
  "nothing further right now") and stitch the two halves, saving ~22 s.
  Cutting more (e.g. ending after the second follow-up) loses the
  "two reminders set" callout and is not recommended.
- The "Luke" name cue mute is audio-only. The product's own rendering of that
  line in the right-side transcript ("Investor · due next week") is still
  visible. That is the product's own UI text and was not redrawn; covering
  it with a drawbox mask is possible but the user has not asked for it.
- All three callouts are rendered with `drawtext` (Georgia, 26 px, dark on
  beige box) in the segment-local time base.
- v1/v2/v4 cuts still exist at `SecondListen_demo_v{1,2,4}.mp4` if needed
  for a shorter-length fallback.