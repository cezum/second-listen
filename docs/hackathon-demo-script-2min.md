# Hackathon Demo Script — Second Listen (final cut, 2:44)

This is the narration script of the finished submission video. Project 8 is a
fictional portfolio company; the upload section uses Project 9, a second
fictional case, to show that the upload path is company-agnostic.

Everything on screen is a real run: the live path is the AssemblyAI Voice Agent
WebSocket, and the upload path is a real Universal-2 transcription + analysis.
No scripted sample playback is used in the final cut.

Narration: AI voice (en-US-AndrewNeural) over the intro, transition, and upload
sections. The live and closure sections use the actual recorded conversation
(investor's voice + agent TTS), not a voiceover. Three on-screen callouts
highlight the key moments.

Two name cues in the recorded TTS are muted out: the "Mike?" cue that follows
the agent's opening question in Live A, and the "Luke" name cue in the closure
segment before the first follow-up question.

| Time | Screen | Audio |
|---|---|---|
| 0:00–0:20 | Entry screen (two doors: Start debrief / Upload a recording) | Narration: investment work, project work, customer success — most of it lives in conversations. Second Listen is built for one of the hardest: post-investment check-ins. Two modes — speak live with the partner, or upload a recording. This is Live. |
| 0:20–0:42 | Live A: Project 8 — agent greeting + first description | Real audio (investor + agent) with the "Mike?" cue muted. Callout "Signals filed, with the quote" fires as R-01 lands. |
| 0:42–1:02 | Live B: IPO slip → flagged REVIEW → buyback question → agreed action with owner and deadline | Real audio. Callout "Agreed action - owner and deadline" fires as A-01 and A-02 are created (Owner: Investor, Due: next week / as soon as possible, Agreed at: 00:41 / 01:22). |
| 1:02–1:33 | Closure: next check-in starts with "Welcome back... let's close one prior follow-up at a time." Right panel: 4-item Previous follow-ups list. Agent repeats the question when the user does not answer, then the user replies "I still need to check." | Real audio with the "Luke" name cue muted. Callout "Prior follow-ups" highlights the carryover. |
| 1:33–1:38 | Entry screen again (transition card) | Narration: If a recording already exists, drop it straight in — same review. |
| 1:38–1:58 | Upload: Project 9 — full report with 9 signals / 7 to review / 9 questions (compliance red line, key personnel loss, funds used outside agreed purpose) | Narration: The same review works from an uploaded recording. The partner listens, files every signal with the original quote, and lists what to verify before the next call. |
| 1:58–2:44 | Closing card | Silent. Text: Second Listen. — Remember what changed. Verify what matters. Same method — project · customer success · compliance reviews. Built for the lablab.ai x AssemblyAI hackathon — 2026. |

## Notes

- The live section runs at 1.0x with two contiguous stretches:
  - Live A: clip_p8_trial [10s, 32s] — greeting + customer delay + R-01.
  - Live B: clip_p8_trial [66s, 126s] — IPO slip → REVIEW flag → buyback
    question → agreed action A-01/A-02 with owner / due / agreed-at.
  - The break is intentional: it skips the customer's first answer to the
    buyback question (which is mid-sentence) and lands cleanly on the agreed
    action resolution.
- The closure shot is clip_p8_trial3 [18s, 30s] — the agent automatically opens
  the next check-in with last week's follow-ups already on the list, closing
  the loop with the agreed actions just created.
- The upload section is clip_p9 [0s, 20s] — the original clip is silent, so
  narration is overlaid.
- All three callouts are rendered with `drawtext` (Georgia, 26 px, dark on
  beige box) in the segment-local time base, so they appear exactly when the
  corresponding moment occurs.
- Earlier v1/v2 drafts used a full AI narration over every second of the
  recorded clips; v3 replaces that with real audio in the live and closure
  sections and reserves narration for the framing pieces only.