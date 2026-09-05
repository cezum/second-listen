// Product UI; audio transport and AssemblyAI event handling remain in app.js.
let selectedSession = null
let lastLedger = { sessions: {} }
let sampleMode = false
let liveCompany = ''
let companyBeforeSample = ''
let offlineData = null
const SAMPLE_ID = 'sample-greenleaf'
const SAMPLE = {
  company: 'GreenLeaf', started_at: '2026-09-05T09:00:00Z', sample: true,
  events: [
    { tool: 'log_evidence', at_seconds: 12, dimension: 'team_integrity', quote: 'our CFO left last month', signal: 'Finance leadership changed; interim coverage is unclear.', escalation: true },
    { tool: 'log_evidence', at_seconds: 24, dimension: 'financial_health', quote: 'moved some of the R&D grant to cover payroll', signal: 'Grant spending may fall outside the approved purpose.', escalation: true },
    { tool: 'log_evidence', at_seconds: 36, dimension: 'operations', quote: 'revenue has been flat for two quarters', signal: 'Growth has stalled. The underlying cause needs checking.', escalation: false },
    { tool: 'add_action_item', at_seconds: 54, task: 'Request written approval for the grant reallocation', owner: 'Alex', deadline: 'Next Monday' },
  ],
}
const DIMENSION_LABELS = { operations: 'Operations', exit_potential: 'Exit outlook', self_funding: 'Cash generation', team_integrity: 'Team', financial_health: 'Financial health' }

function el(tag, cls, text) {
  const node = document.createElement(tag)
  if (cls) node.className = cls
  if (text != null) node.textContent = text
  return node
}
function badge(text, escalation = false) { return el('span', 'badge' + (escalation ? ' escalation' : ''), text) }
function feedback(message, error = false) {
  $('feedback').textContent = message
  $('feedback').className = 'notice' + (error ? ' error' : '')
  $('feedback').hidden = !message
}
async function responseJSON(res) {
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || 'The request failed. Please try again.')
  return data
}
function currentSessionId(ledger) {
  const ids = Object.keys(ledger.sessions || {})
  if (sampleMode) return SAMPLE_ID
  if (sessionId && ws?.readyState === 1) return sessionId
  if (selectedSession && ids.includes(selectedSession)) return selectedSession
  return ids.sort((a, b) => (ledger.sessions[b].started_at || '').localeCompare(ledger.sessions[a].started_at || ''))[0]
}
function stamp(seconds) {
  if (seconds == null) return '—'
  const total = Math.max(0, Math.floor(seconds))
  return String(Math.floor(total / 60)).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0')
}
function downloadText(text, filename) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown;charset=utf-8' }))
  const link = el('a')
  link.href = url; link.download = filename
  document.body.append(link); link.click(); link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
function noteFilename(company, id) {
  const slug = (company || '').trim().toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/g, '-').replace(/^-+|-+$/g, '')
  return (slug || 'session-' + id.slice(-8)) + '-follow-up.md'
}
async function downloadNote(id, company) {
  try {
    if (sampleMode) {
      downloadText('# Second Listen — fictional sample\n\nIllustrative walkthrough; not a live AI result.\n\n' + SAMPLE.events.map(e => e.tool === 'log_evidence'
        ? `- [${stamp(e.at_seconds)} illustrative] ${e.signal}\n  Quote: “${e.quote}”`
        : `- [ ] ${e.task} — ${e.owner}, ${e.deadline}`).join('\n\n') + '\n\nFlags require human review. Actions are recorded tasks; no notifications are scheduled.\n', 'greenleaf-sample.md')
    } else {
      const res = await fetch('/api/note?session=' + encodeURIComponent(id) + '&company=' + encodeURIComponent(company || ''))
      if (!res.ok) throw new Error('Could not export this debrief. Please retry.')
      downloadText(await res.text(), noteFilename(company, id))
    }
    feedback('Follow-up note downloaded.')
  } catch (error) { feedback(error.message, true) }
}
function refreshLedger() {
  if (sampleMode) return
  return fetch('/api/ledger').then(responseJSON).then(renderLedger).catch(error => feedback(error.message, true))
}
function renderLedger(ledger) {
  if (!sampleMode) lastLedger = ledger
  const body = $('ledger-body')
  body.replaceChildren()
  const ids = Object.keys(ledger.sessions || {})
  const current = currentSessionId(ledger)
  const session = ledger.sessions[current]
  if (!session) {
    const empty = el('div', 'evidence-empty')
    empty.append(el('h3', '', ws?.readyState === 1 ? 'Listening for the first signal.' : 'The signal, and the source.'))
    empty.append(el('p', 'empty', 'Each finding keeps the words behind it, so you can check the evidence before deciding what to do.'))
    for (const [num, text] of [['01', 'Exact quotes linked to risk signals'], ['02', 'Checklist triggers that need a closer look'], ['03', 'Agreed actions, with an owner and a deadline']]) {
      const row = el('div', 'empty-step'); row.append(el('span', '', num), el('div', '', text)); empty.append(row)
    }
    body.append(empty); hideBanner(); return
  }
  if (sampleMode) body.append(el('div', 'sample-note', 'FICTIONAL SAMPLE · Illustrative timing · Not a live AI result'))
  else {
    const picker = el('label', 'session-picker', 'Debrief')
    const select = el('select'); select.setAttribute('aria-label', 'Choose a debrief')
    for (const id of ids.sort((a, b) => (ledger.sessions[b].started_at || '').localeCompare(ledger.sessions[a].started_at || ''))) {
      const entry = ledger.sessions[id]
      const option = el('option', '', `${entry.company || 'Unassigned company'} · ${(entry.started_at || '').slice(0, 16).replace('T', ' ')} · ${id.slice(-6)}`)
      option.value = id; option.selected = id === current; select.append(option)
    }
    select.disabled = ws?.readyState === 1
    select.onchange = () => { selectedSession = select.value; renderLedger(lastLedger) }
    picker.append(select); body.append(picker)
  }
  const events = session.events || []
  const evidence = events.filter(e => e.tool === 'log_evidence')
  const actions = events.filter(e => e.tool === 'add_action_item')
  const escalations = evidence.filter(e => e.escalation)
  const summary = el('div', 'summary-grid')
  for (const [n, label] of [[evidence.length, 'Signals captured'], [escalations.length, 'Review flags'], [actions.length, 'Agreed actions']]) {
    const card = el('div'); card.append(el('strong', '', n), el('span', '', label)); summary.append(card)
  }
  body.append(summary)
  for (const event of [...evidence, ...actions]) {
    const row = el('article', 'ledger-event' + (event.escalation ? ' flagged' : ''))
    const meta = el('div', 'meta')
    meta.append(badge(event.tool === 'add_action_item' ? 'Agreed action' : DIMENSION_LABELS[event.dimension] || 'Evidence'))
    if (event.escalation) meta.append(badge('Review needed', true))
    const time = el('span', 'evidence-time', stamp(event.at_seconds))
    time.title = sampleMode ? 'Illustrative timestamp' : 'Time recorded in the live session, not a word-aligned audio citation'
    meta.append(time); row.append(meta)
    if (event.tool === 'log_evidence') {
      row.append(el('div', 'signal', event.signal))
      const quote = el(sampleMode ? 'button' : 'div', sampleMode ? 'quote quote-button' : 'quote', '“' + event.quote + '”')
      if (sampleMode) { quote.title = 'Locate this quote in the sample conversation'; quote.onclick = () => highlightQuote(event.quote) }
      row.append(quote)
    } else {
      row.append(el('div', 'signal', event.task), el('div', 'action-meta', `${event.owner} · Due ${event.deadline}`))
    }
    body.append(row)
  }
  const bar = el('div', 'note-bar')
  const download = el('button', '', 'Download follow-up note ↓')
  download.onclick = () => downloadNote(current, session.company)
  bar.append(download)
  if (actions.length && !sampleMode && session.company) {
    const save = el('button', 'secondary', 'Save for next debrief')
    save.disabled = ws?.readyState === 1
    save.title = save.disabled ? 'End the debrief before saving its agreed actions' : 'Carry agreed actions into the next call for this company'
    save.onclick = async () => {
      save.disabled = true
      try {
        const result = await fetch('/api/history', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({session_id: current, company: session.company}) }).then(responseJSON)
        $('company').value = session.company
        feedback(`${result.commitments} follow-up(s) saved for ${session.company}. Start the next inline debrief with this company to check them. These are recorded tasks, not scheduled notifications.`)
        refreshCommitments()
      } catch(error) { feedback(error.message, true) }
      finally { save.disabled = false }
    }
    bar.append(save)
  }
  body.append(bar)
  if (escalations.length) showBanner(escalations.map(e => e.signal))
  else hideBanner()
}
function showBanner(signals) {
  $('escalation-text').textContent = `${signals.length} checklist trigger${signals.length === 1 ? '' : 's'} to verify. Review the quotes before escalating.`
  $('escalation-banner').hidden = false
}
function hideBanner() { $('escalation-banner').hidden = true }
function refreshCommitments() {
  if (sampleMode) return renderCommitments({ company:'GreenLeaf', last_debrief_at:'2026-08-28', commitments:[{ task:'Confirm who is covering finance after the CFO departure', owner:'Alex', deadline:'This debrief' }] })
  const company = $('company').value.trim()
  if (!company) return renderCommitments({})
  return fetch('/api/history?company=' + encodeURIComponent(company)).then(responseJSON).then(renderCommitments).catch(error => feedback(error.message, true))
}
function renderCommitments(value) {
  const body = $('commitments-body'); body.replaceChildren()
  const commitments = value.commitments || []
  if (sampleMode) body.append(el('div', 'sample-note', 'FICTIONAL PREVIOUS DEBRIEF · Shows how a commitment check works'))
  if (!commitments.length) {
    body.append(el('div', 'evidence-empty', 'No saved follow-ups for this company. After a debrief, save its agreed actions here. Your next inline call for the same company opens by checking them.'))
    return
  }
  body.append(el('div', 'commitments-head', `${value.company} · Previous debrief ${(value.last_debrief_at || '').slice(0,10)}`))
  for (const c of commitments) {
    const card = el('div', 'commitment')
    card.append(el('div', 'commitment-task', c.task), el('div', 'commitment-meta', `${c.owner} · Due ${c.deadline}`))
    body.append(card)
  }
  body.append(el('p','empty', 'Recorded follow-ups. No email or calendar reminders are sent.'))
}
function highlightQuote(quote) {
  document.querySelectorAll('#transcript .line').forEach(line => {
    const match = line.textContent.toLowerCase().includes(quote.toLowerCase())
    line.classList.toggle('highlight', match)
    if (match) line.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  })
}
function exitSample() {
  if (!sampleMode) return
  sampleMode = false; $('company').value = companyBeforeSample
  $('sample-btn').textContent = 'Explore a sample debrief ↗'
  $('conversation-label').textContent = 'LIVE DEBRIEF'
  $('transcript').replaceChildren(el('div', 'empty', 'Ready for a new debrief. Tell your partner what happened on the call.'))
  feedback(''); renderLedger(lastLedger); refreshCommitments()
}
$('sample-btn').onclick = () => {
  if (sampleMode) { exitSample(); return }
  if (ws?.readyState <= 1) { feedback('End the current debrief before opening the sample.', true); return }
  companyBeforeSample = $('company').value
  sampleMode = true; $('company').value = 'GreenLeaf'
  $('sample-btn').textContent = 'Close sample debrief ×'
  $('conversation-label').textContent = 'FICTIONAL WALKTHROUGH'
  $('transcript').replaceChildren(el('div', 'sample-note', 'ILLUSTRATIVE CONVERSATION · Click an evidence quote to locate it here'))
  const lines = [
    ['you', 'The founder seemed upbeat. They have a new office, but our CFO left last month. Nobody has formally taken over finance.'],
    ['partner', 'Who is covering finance, and since when?'],
    ['you', 'I need to check. They also moved some of the R&D grant to cover payroll. Revenue has been flat for two quarters.'],
    ['partner', 'Was there written approval to use the grant for payroll?'],
    ['you', "I'm not sure."],
    ['partner', 'Shall we add a follow-up to request the written approval?'],
    ['you', 'Yes. Assign it to Alex, due next Monday.'],
    ['partner', 'The follow-up is recorded for Alex, due next Monday.'],
  ]
  for (const [who, text] of lines) {
    const row = el('div','line' + (who === 'partner' ? ' agent' : ' sample-user'))
    row.append(el('span','who',who),el('span','said',text)); $('transcript').append(row)
  }
  renderLedger({ sessions: { [SAMPLE_ID]: SAMPLE } }); refreshCommitments(); showTab('ledger')
  feedback('Sample walkthrough: 3 signals, 2 review flags, 1 explicitly agreed action. Nothing is written to your workspace.')
}
$('company').addEventListener('change', () => { if (!sampleMode) refreshCommitments() })

$('analyze-btn').onclick = () => { if (sampleMode) exitSample(); $('file').click() }
$('file').onchange = async () => {
  const file = $('file').files[0]; $('file').value = ''
  if (!file) return
  if (!file.size || file.size > 50 * 1024 * 1024) { feedback('Choose an audio file between 1 byte and 50 MB.', true); return }
  const button = $('analyze-btn'); button.disabled = true; button.textContent = 'Transcribing & analyzing…'
  feedback('Processing ' + file.name + '. Longer recordings can take several minutes. Keep this page open.')
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 15 * 60 * 1000)
  try {
    const data = await fetch('/api/upload', { method:'POST', headers:{'X-Filename':encodeURIComponent(file.name)}, body:file, signal:controller.signal }).then(responseJSON)
    offlineData = { ...data, filename:file.name }
    renderOffline(data,file.name)
    feedback('Analysis ready. Review the candidates, then download the recording note.')
  } catch(error) { renderOfflineError(error.name === 'AbortError' ? 'The request timed out. Try a shorter recording.' : error.message) }
  finally { clearTimeout(timeout); button.disabled = false; button.textContent = 'Analyze recording ↑' }
}
$('offline-close').onclick = () => { $('offline-result').hidden = true }
function renderOfflineError(message) {
  $('offline-title').textContent = 'Recording analysis'
  $('offline-body').replaceChildren(el('p', 'empty', message))
  $('offline-result').hidden = false; feedback(message,true)
}
function renderOffline(data, name) {
  $('offline-title').textContent = `Recording analysis · ${name}${data.language ? ' · ' + data.language.toUpperCase() : ''}`
  const body = $('offline-body'); body.replaceChildren()
  const analysis = data.analysis || {}; const signals = analysis.signals || []; const questions = analysis.questions || []
  body.append(el('div', 'notice', `${analysis.method === 'llm' ? 'AI analysis' : 'Keyword screening'} · ${analysis.notice || 'Verify every candidate against the recording.'}`))
  if (data.cached) body.append(el('p', 'empty', 'Saved transcription reused; analysis rerun.'))
  body.append(el('h3','',signals.length + ' candidates to verify'))
  if (!signals.length) body.append(el('p','empty', 'No candidates matched. This does not establish that the company has no risks. Check the transcript for missed context.'))
  for (const s of signals) {
    const row = el('div','offline-signal')
    row.append(badge(DIMENSION_LABELS[s.dimension] || s.dimension), el('div','signal',s.signal),el('div','quote','“' + s.quote + '”'))
    if (s.escalation) row.append(badge('Potential checklist trigger',true))
    body.append(row)
  }
  if (questions.length) {
    body.append(el('h3','','Questions for the next conversation'))
    for (const q of questions) { const row = el('div','offline-question'); row.append(el('span','q','↗'),el('span','',q.question)); body.append(row) }
  }
  const details = el('details'); details.append(el('summary','','Read the full transcript'),el('div','offline-transcript',data.text || 'No speech was transcribed.')); body.append(details)
  const bar = el('div','note-bar'); const download = el('button','','Download recording note ↓')
  download.onclick = () => {
    const text = [`# Recording review — ${name}`, '', `Analysis method: ${analysis.method || 'keyword'}`, analysis.notice || '', '', '## Candidates (not final grades)', ...signals.map(s=>`\n- ${s.signal}\n  Quote: “${s.quote}”\n  Checklist review: ${s.escalation ? 'needed' : 'not flagged'}`), '', '## Suggested questions (not agreed actions)', ...questions.map(q=>'- '+q.question), '', '## Transcript',data.text || '', '', 'Generated by Second Listen. Verify quotes against the audio.']
    downloadText(text.join('\n'),name.replace(/\.[^.]+$/,'')+'-review.md'); feedback('Recording note downloaded.')
  }
  bar.append(download); body.append(bar); $('offline-result').hidden = false
  $('offline-result').scrollIntoView({behavior:'smooth',block:'start'})
}
// Keyboard navigation for the tab group.
document.querySelectorAll('[role="tab"]').forEach((button,index,buttons) => {
  button.addEventListener('keydown', event => {
    if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return
    event.preventDefault()
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length-1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length
    buttons[next].focus(); buttons[next].click()
  })
})
if (AGENT.preview) {
  $('preview-notice').hidden = false
  $('btn').disabled = true; $('analyze-btn').disabled = true; $('mic').disabled = true
}
showTab('ledger')
