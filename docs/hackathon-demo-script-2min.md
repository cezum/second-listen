# Hackathon Demo Script — Second Listen (v8 cut, 3:44)

This is the narration script of the v8 submission video. Project 8 is a
fictional portfolio company; the upload section uses Project 9, a second
fictional case, to show that the upload path is company-agnostic.

Everything on screen is a real run: the live path is the AssemblyAI Voice Agent
WebSocket, and the upload path is a real Universal-2 transcription + analysis.
No scripted sample playback is used in the final cut.

Audio policy: AI narration (en-US-AndrewNeural) over intro A/B, the upload
section, and the closing card; the live section uses the actual recorded
conversation (investor's voice + agent TTS), not a voiceover. A small
persistent "live-debrief" tag anchors the viewer during the long live section.

Three on-screen callouts are bubbles, not captions: a filled rounded shape
with cream Georgia text, a drop shadow, and a tail. Each bubble's tail tip is
positioned so it lands on the thing being described (the follow-up list, the
follow-up action that was just recorded), never in the empty margin. Fill is `#2B2520` —
the product's own ink family, deliberately not the app red `#a42b2f`, so a
bubble sitting next to the red "Export note" button is never mistaken for
another control.

Three short audio regions in the live section are muted, all in the same
agent-prompting-the-investor pause around the first follow-up:
- trial3 abs [23.48, 23.95] "Luke, due next week." (owner label)
- trial3 abs [29.02, 29.62] "Luke?" (agent prompting for an answer)
- trial3 abs [31.18, 31.82] investor's discarded half-answer in the same pause

| Time | Screen | Audio |
|---|---|---|
| 0:00–0:17 | Intro A: typewriter card on beige. Four lines appear sequentially: "Every check-in ends the same way." / "The conversation happened." / "The judgment is still trapped inside it." / "Transcription is solved. Judgment is not." | Narration: Every check-in call ends the same way. The conversation happened — but the judgment is still trapped inside it. Transcription is solved. Knowing what matters, what needs follow-up, and what you are exposed to if nobody wrote it down — that is not. |
| 0:17–0:42 | Intro B: product entry (two doors: Start debrief / Upload a recording) | Narration: So we took a real post-investment playbook and compiled it into skills the partner runs live: file every signal with the quote it came from, escalate anything that crosses a red line, and turn each answer into an action with an owner and a deadline. This is Second Listen. What follows is a second check-in — the partner opens it by reopening last week's follow-ups, one at a time. |
| 0:42–2:48 | Live part 1: trial3 [9.5, 135.8] — natural pacing, no internal cuts. Walks through follow-ups #1, #2, #3. Right panel: four previous follow-ups with checkboxes. Two new AGREED ACTIONS (A-01, A-02) created with owner / due / agreed-at metadata. | Real audio. "Luke" name cues muted (3 regions). Bubble "Reminder set" @ 1:37–1:45 is legacy wording for the follow-up action just recorded; no external notification is scheduled. |
| 2:48–3:17 | Live part 2: trial3 [157.7, 186.5] — "Since all follow-ups are still in progress, let's move on" / "Was there anything else new or different..." / the recorded agent's legacy "two reminders" wording. Right panel updates to show 0 signals / 0 to review / 2 actions. | Real audio. Bubble "Two reminders set" @ 3:02–3:14 refers to the two actions just recorded; no external notifications are scheduled. |
| 3:17–3:29 | Upload: Project 9 static result frame — 9 signals / 7 to review / 9 questions, with R-01 (compliance red line), R-02 (team — key personnel loss), R-03 (financial health — funds used outside agreed purpose) | Narration: The same skills also run on an uploaded recording — drop in the file, get the same risk list, the same follow-ups, the same open questions. |
| 3:29–3:44 | Outro: typewriter card on beige. Five lines appear sequentially: "Everything is on the record." / "Signals, each with the quote behind it." / "Follow-ups, each with an owner and a due date." / "Next week, the partner opens with them." / "Second Listen." Footer: "Same method — project · customer success · compliance reviews" and "lablab.ai x AssemblyAI hackathon — 2026" | Narration: Everything from this call is now on the record: the signals, the quote behind each one, and the follow-ups, each with an owner and a due date. Next week, the partner opens with them. Second Listen. |

## Notes

- The live section is the spine of the video. trial3 was chosen for the natural
  internal drama: the agent asking for a status, the user saying "I still need
  to check", the second reminder being set on the same call. All are kept at
  the recorded pace.
- The litigation follow-up (trial3 abs [135.8, 157.7] — "no new developments"
  / "nothing further right now") is dropped to keep the cut under 3:45. The
  cut falls on agent prompts followed by silence, so it is visually invisible.
  To produce a fully uncut 3:58 version, set `TRIM_LITIGATION = False` at the
  top of `build_demo_v8.py` and re-run.
- The intro and outro share the same visual grammar (beige ground, Georgia
  Bold headline + Georgia Italic body, lines revealed sequentially at 0.4 /
  3.0 / 6.0 / 9.6 s). The bookend structure is intentional: the intro names
  the gap ("that is not solved"), the outro names the artifact ("everything
  is on the record"). Together they are a single argument.
- "that is not" in the intro is a deliberate ellipsis: it closes the prior
  sentence's "Transcription is solved" — i.e. "that is not [solved]". The
  omission makes the contrast hit harder when the listener's mind supplies
  the missing word.
- All three Luke mutes are audio-only. The product's own UI transcript
  ("Investor · due next week") is still visible on screen; redrawing it
  would obscure real product text and was not done.
- The live section runs at 1.0x throughout. No internal speed changes.
- In the recorded cut, "reminder" is legacy shorthand for a persisted follow-up
  action. The product records owner, deadline and agreed-at metadata but does
  not schedule an external notification.
- v1/v2/v3/v4/v5/v6/v7 cuts still exist on disk if a shorter fallback is
  needed.
- The three callouts are rendered as transparent PNG bubbles (HTML -> headless
  browser screenshot) and overlaid with ffmpeg, not drawn with `drawtext`, so
  they can have a tail, a drop shadow, and rounded corners. The tail tip is
  the anchor: moving a bubble is one coordinate in `LIVE_CALLOUTS_ABS` in
  `build_demo_v8.py`, and the fill colour is one constant in `make_bubbles.py`.
