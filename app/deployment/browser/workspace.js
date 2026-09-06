// Product UI for the v2 layout: the recorder on the left, the risk note on
// the right. Audio transport and AssemblyAI event handling remain in app.js.
let selectedSession = null
let lastLedger = { sessions: {} }
let sampleMode = false
let liveCompany = ''
let companyBeforeSample = ''
let historyReadyForNextDebrief = true
const autoSavedFollowUps = new Set()
const seenEntries = new Set()
const SAMPLE_ID = 'sample-greenleaf'
let sampleRun = 0
let sampleTimer = null
const SAMPLE = {
  company: 'GreenLeaf', started_at: '2026-09-05T09:00:00Z', sample: true,
  events: [
    { tool: 'log_evidence', at_seconds: 12, dimension: 'team_integrity', quote: 'our CFO left last month', signal: 'Finance leadership changed; interim coverage is unclear.', escalation: true },
    { tool: 'log_evidence', at_seconds: 24, dimension: 'financial_health', quote: 'moved some of the R&D grant to cover payroll', signal: 'Grant spending may fall outside the approved purpose.', escalation: true },
    { tool: 'log_evidence', at_seconds: 36, dimension: 'operations', quote: 'revenue has been flat for two quarters', signal: 'Growth has stalled. The underlying cause needs checking.', escalation: false },
    { tool: 'add_action_item', at_seconds: 54, task: 'Request written approval for the grant reallocation', owner: 'Alex', deadline: 'Next Monday' },
  ],
}
const SAMPLE_HISTORY = {
  company: 'GreenLeaf', commitments: [],
}
const DIMENSION_LABELS = { operations: 'Operations', exit_potential: 'Exit outlook', self_funding: 'Cash generation', team_integrity: 'Team', financial_health: 'Financial health' }

function el(tag, cls, text) {
  const node = document.createElement(tag)
  if (cls) node.className = cls
  if (text != null) node.textContent = text
  return node
}
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
function pad(n) { return n < 10 ? '0' + n : '' + n }

// ---------- the note ----------

function noteStatus(escalations) {
  const node = $('lh-status')
  if (ws?.readyState === 1) { node.textContent = '● LIVE'; node.className = 'lh-status' }
  else if (escalations) { node.textContent = '● ' + escalations + ' TO REVIEW'; node.className = 'lh-status' }
  else { node.textContent = 'FILED'; node.className = 'lh-status filed' }
}

function ensureRecordingView() {
  const current = $('recording-view')
  if (current) return current

  // Older pages had a standalone report above the two-column workspace.
  // Move that node into the right sheet at runtime so an already-open tab
  // still gets the new presentation without exposing a second report card.
  const legacy = $('offline-result')
  const sheet = $('sheet')
  if (!legacy || !sheet) return legacy
  const legacyHeader = legacy.querySelector('.letterhead')
  const currentHeader = sheet.querySelector('.letterhead')
  const legacyClose = legacyHeader?.querySelector('#offline-close')
  const legacyStatus = legacyHeader?.querySelector('#offline-status')
  if (legacyClose && currentHeader) {
    legacyClose.id = 'recording-close'
    currentHeader.append(legacyClose)
  }
  if (legacyStatus && currentHeader) currentHeader.append(legacyStatus)
  legacyHeader?.remove()
  legacy.id = 'recording-view'
  legacy.classList.remove('sheet', 'offline')
  sheet.append(legacy)
  return legacy
}

function recordingElement(id, legacyId = null) {
  const node = id === 'recording-view' ? ensureRecordingView() : $(id)
  const fallback = legacyId ? $(legacyId) : null
  const oldTitle = id === 'sheet-title' ? $('sheet')?.querySelector('.letterhead .lh-title') : null
  const oldSource = id === 'recording-source' ? $('lh-status') : null
  return node || fallback || oldTitle || oldSource
}

function recordingText(id, text, legacyId = null) {
  const node = recordingElement(id, legacyId)
  if (node) node.textContent = text
}

function showRecordingView(open, render = true) {
  const recording = open === true
  const view = recordingElement('recording-view', 'offline-result')
  const close = recordingElement('recording-close', 'offline-close')
  if (view) view.hidden = !recording
  if (close) close.hidden = !recording
  if ($('note-empty')) $('note-empty').hidden = recording
  if ($('note-filled')) $('note-filled').hidden = recording
  recordingText('sheet-title', recording
    ? 'SECOND LISTEN — RECORDING REVIEW'
    : 'SECOND LISTEN — POST-INVESTMENT VISIT NOTES')
  const source = $('recording-source') || $('offline-status')
  // The summary row already carries the review count. Keep the letterhead
  // quiet and reserve its right side for the shared back-to-workspace action.
  if ($('lh-status')) $('lh-status').hidden = true
  if (source && source.id === 'offline-status') source.hidden = !recording
  if ($('sheet')) $('sheet').setAttribute('aria-label', recording ? 'Recording analysis' : 'Post-investment visit notes')
  if (!recording && render) renderLedger(lastLedger)
}

function prepareDebriefView() {
  historyReadyForNextDebrief = true
  document.body.classList.remove('recording-open')
  showRecordingView(false, false)
  $('note-empty').hidden = false
  $('note-filled').hidden = true
  $('lh-status').textContent = 'DRAFT'
  $('lh-status').className = 'lh-status'
  refreshPrev()
}

function clearCurrentAnalysis() {
  historyReadyForNextDebrief = false
  document.body.classList.remove('recording-open')
  showRecordingView(false, false)
  $('note-empty').hidden = false
  $('note-filled').hidden = true
  $('lh-status').textContent = 'DRAFT'
  $('lh-status').className = 'lh-status'
  renderPrev({}, false)
}

function evidenceRow(event, eid, fresh) {
  const row = el('article', 'entry' + (event.escalation ? ' review' : '') + (fresh ? ' flash' : ''))
  row.append(el('span', 'eid', eid))
  const main = el('div')
  const meta = el('div', 'entry-meta')
  meta.append(el('span', 'dim', DIMENSION_LABELS[event.dimension] || 'Evidence'))
  if (event.escalation) meta.append(el('span', 'chip', 'Review'))
  const cite = el('span', 'cite', 'said at ' + stamp(event.at_seconds))
  cite.title = sampleMode ? 'Illustrative timestamp' : 'Time recorded in the live session, not a word-aligned audio citation'
  meta.append(cite)
  main.append(meta, el('p', 'signal', event.signal))
  const quote = el('button', 'quote quote-btn', '“' + event.quote + '”')
  quote.type = 'button'
  quote.title = 'Locate this quote in the conversation'
  quote.onclick = () => highlightQuote(event.quote)
  main.append(quote)
  row.append(main)
  return row
}

function recordingEvidenceRow(signal, eid) {
  const row = el('article', 'entry' + (signal.escalation ? ' review' : ''))
  row.append(el('span', 'eid', eid))
  const main = el('div')
  const meta = el('div', 'entry-meta')
  meta.append(el('span', 'dim', DIMENSION_LABELS[signal.dimension] || signal.dimension || 'Evidence'))
  if (signal.escalation) meta.append(el('span', 'chip', 'Trigger'))
  main.append(meta, el('p', 'signal', signal.signal), el('div', 'quote', '“' + signal.quote + '”'))
  row.append(main)
  return row
}

function followupRow(check) {
  const labels = {
    completed: 'Resolved',
    unresolved: 'Still open',
    unclear: 'Needs confirmation',
    not_addressed: 'Not addressed',
  }
  const row = el('article', 'followup-row status-' + check.status)
  const main = el('div')
  main.append(el('p', 'task', check.task))
  const meta = [check.owner && 'Owner ' + check.owner, check.deadline && 'due ' + check.deadline].filter(Boolean).join(' · ')
  if (meta) main.append(el('p', 'task-meta', meta))
  if (check.quote) main.append(el('div', 'quote', '“' + check.quote + '”'))
  if (check.note) main.append(el('p', 'followup-note', check.note))
  row.append(el('span', 'followup-status', labels[check.status] || 'Review'), main)
  return row
}

function actionRow(event, eid, fresh) {
  const row = el('article', 'entry action' + (fresh ? ' flash' : ''))
  row.append(el('span', 'eid', eid))
  const main = el('div')
  main.append(el('p', 'task', event.task), el('p', 'task-meta', 'Owner ' + event.owner + ' · due ' + event.deadline + ' · agreed at ' + stamp(event.at_seconds)))
  row.append(main)
  return row
}

function commitmentRow(c) {
  const row = el('label', 'commit')
  const box = document.createElement('input')
  box.type = 'checkbox'
  box.onclick = () => row.classList.toggle('checked', box.checked)
  const wrap = el('span')
  wrap.append(el('span', 'task', c.task), el('span', 'commit-meta', c.owner + ' · due ' + c.deadline))
  row.append(box, wrap)
  return row
}

function renderLedger(ledger) {
  if (!sampleMode) lastLedger = ledger
  if (document.body.classList.contains('recording-open')) return
  const close = recordingElement('recording-close', 'offline-close')
  if (close) close.hidden = true
  const ids = Object.keys(ledger.sessions || {})
  const current = currentSessionId(ledger)
  const session = ledger.sessions[current]
  if (current !== renderLedger.lastId) { seenEntries.clear(); renderLedger.lastId = current }

  if (!session) {
    $('note-empty').hidden = false
    $('note-filled').hidden = true
    $('lh-status').textContent = 'DRAFT'; $('lh-status').className = 'lh-status'
    refreshPrev()
    return
  }

  $('note-empty').hidden = true
  $('note-filled').hidden = false
  // A completed debrief can return to the same blank workspace as a
  // recording review. Never expose it while the live session is active.
  if (close) close.hidden = ws?.readyState === 1
  // Saved follow-ups belong to the next debrief's context, not this
  // completed report.
  $('sec-prev').style.display = 'none'

  const events = [...(session.events || [])].sort((a, b) => (a.at_seconds ?? 0) - (b.at_seconds ?? 0))
  const evidence = events.filter(e => e.tool === 'log_evidence')
  const actions = events.filter(e => e.tool === 'add_action_item')
  const escalations = evidence.filter(e => e.escalation)

  $('note-company').textContent = session.company || 'Unassigned company'
  const started = (session.started_at || '').slice(0, 16).replace('T', ' ')
  $('note-sub').textContent = 'Debrief · ' + (started || 'date unknown') + ' · ref ' + String(current).slice(-8)
  noteStatus(escalations.length)

  // Session picker, for reading past debriefs of any company.
  const pickerWrap = $('session-pick-wrap')
  if (!sampleMode && ids.length > 1 && ws?.readyState !== 1) {
    pickerWrap.hidden = false
    const select = $('session-pick')
    select.replaceChildren()
    for (const id of ids.sort((a, b) => (ledger.sessions[b].started_at || '').localeCompare(ledger.sessions[a].started_at || ''))) {
      const entry = ledger.sessions[id]
      const option = el('option', '', (entry.company || 'Unassigned') + ' · ' + (entry.started_at || '').slice(5, 10))
      option.value = id; option.selected = id === current
      select.append(option)
    }
    select.onchange = () => { selectedSession = select.value; renderLedger(lastLedger) }
  } else pickerWrap.hidden = true

  const listReview = $('list-review'); listReview.replaceChildren()
  const listSignals = $('list-signals'); listSignals.replaceChildren()
  const listActions = $('list-actions'); listActions.replaceChildren()
  evidence.forEach((event, i) => {
    const eid = 'R-' + pad(i + 1), fresh = !seenEntries.has(eid + current)
    seenEntries.add(eid + current)
    ;(event.escalation ? listReview : listSignals).append(evidenceRow(event, eid, fresh))
  })
  actions.forEach((event, i) => {
    const eid = 'A-' + pad(i + 1), fresh = !seenEntries.has(eid + current)
    seenEntries.add(eid + current)
    listActions.append(actionRow(event, eid, fresh))
  })
  $('sec-review').style.display = listReview.children.length ? '' : 'none'
  $('sec-signals').style.display = listSignals.children.length ? '' : 'none'
  $('sec-actions').style.display = listActions.children.length ? '' : 'none'
  $('st-signals').textContent = evidence.length
  $('st-review').textContent = escalations.length
  $('st-actions').textContent = actions.length
  $('cnt-review').textContent = escalations.length ? '· ' + escalations.length : ''
  $('cnt-signals').textContent = (evidence.length - escalations.length) ? '· ' + (evidence.length - escalations.length) : ''
  $('cnt-actions').textContent = actions.length ? '· ' + actions.length : ''

  $('note-download').onclick = () => downloadNote(current, session.company)

  refreshPrev()
}

// ---------- previous commitments ("from last debrief") ----------

function refreshPrev() {
  if (sampleMode) return renderPrev(SAMPLE_HISTORY, true)
  const company = (ws?.readyState === 1 ? liveCompany : $('company').value).trim()
  if (!company) return renderPrev({}, false)
  return fetch('/api/history?company=' + encodeURIComponent(company)).then(responseJSON).then(v => renderPrev(v, false)).catch(() => {})
}
function renderPrev(value, isSample) {
  const commitments = value.commitments || []
  const showHistory = commitments.length > 0 && (isSample || historyReadyForNextDebrief)
  // Filled note.
  const list = $('prev-list'); list.replaceChildren()
  $('prev-head').textContent = 'Previous follow-ups' + (value.last_debrief_at ? ' · ' + value.last_debrief_at.slice(0, 10) : '')
  if (showHistory && isSample) list.append(el('div', 'sample-note', 'FICTIONAL PREVIOUS REVIEW · HOW THE COMMITMENT CHECK WORKS'))
  if (showHistory && commitments.length) {
    for (const c of commitments) list.append(commitmentRow(c))
    $('sec-prev').style.display = ''
  } else $('sec-prev').style.display = 'none'
  // Empty note.
  if ($('sec-prev-empty')) $('sec-prev-empty').style.display = showHistory ? '' : 'none'
  const emptyList = $('prev-empty'); emptyList.replaceChildren()
  $('prev-head-empty').textContent = 'Previous follow-ups' + (value.last_debrief_at ? ' · ' + value.last_debrief_at.slice(0, 10) : '')
  if (showHistory && commitments.length) {
    for (const c of commitments) emptyList.append(commitmentRow(c))
  }
}
function refreshLedger(render = true) {
  if (sampleMode) return
  return fetch('/api/ledger').then(responseJSON).then(ledger => {
    lastLedger = ledger
    if (render) renderLedger(ledger)
    return ledger
  }).catch(error => feedback(error.message, true))
}

async function autoSaveFollowUps(sessionId, company) {
  if (!sessionId || !company || autoSavedFollowUps.has(sessionId)) return
  const session = lastLedger.sessions?.[sessionId]
  const hasActions = session?.events?.some(event => event.tool === 'add_action_item')
  if (!hasActions) return
  autoSavedFollowUps.add(sessionId)
  try {
    const result = await fetch('/api/history', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, company }),
    }).then(responseJSON)
    $('company').value = company
    historyReadyForNextDebrief = false
    refreshPrev()
    feedback(`${result.commitments} follow-up(s) will be checked automatically next time you review ${company}.`)
  } catch (error) {
    autoSavedFollowUps.delete(sessionId)
    feedback('Follow-ups could not be carried forward automatically. ' + error.message, true)
  }
}

function highlightQuote(quote) {
  document.querySelectorAll('#transcript .line').forEach(line => {
    const match = line.textContent.toLowerCase().includes(quote.toLowerCase())
    line.classList.toggle('highlight', match)
    if (match) line.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  })
}

// ---------- note export ----------

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
    if (!sampleMode) clearCurrentAnalysis()
  } catch (error) { feedback(error.message, true) }
}

// ---------- the sample walkthrough ----------

function exitSample() {
  if (!sampleMode) return
  sampleRun++
  clearTimeout(sampleTimer)
  sampleTimer = null
  window.speechSynthesis?.cancel()
  sampleMode = false
  document.body.classList.remove('sampling')
  if (typeof setStatus === 'function') setStatus('idle')
  $('company').value = companyBeforeSample
  $('sample-btn').textContent = 'Watch a sample ↗'
  $('live-hint').textContent = 'Evidence is filed to the note on the right as you speak →'
  resetTranscript()
  feedback(''); renderLedger(lastLedger); refreshPrev()
}
function resetTranscript() {
  $('transcript').replaceChildren(el('div', 'empty', 'Ready for a new debrief. Tell your partner what changed at the latest check-in.'))
}

const SAMPLE_LINES = [
  ['you', 'The founder seemed upbeat. They have a new office, but our CFO left last month. Nobody has formally taken over finance.'],
  ['partner', 'Who is covering finance, and since when?'],
  ['you', 'I need to check. They also moved some of the R&D grant to cover payroll. Revenue has been flat for two quarters.'],
  ['partner', 'Was there written approval to use the grant for payroll?'],
  ['you', "I'm not sure."],
  ['partner', 'Shall we add a follow-up to request the written approval?'],
  ['you', 'Yes. Assign it to Alex, due next Monday.'],
  ['partner', 'The follow-up is recorded for Alex, due next Monday.'],
]

function renderSampleEvents(count) {
  renderLedger({ sessions: { [SAMPLE_ID]: { ...SAMPLE, events: SAMPLE.events.slice(0, count) } } })
}

function appendSampleLine(who, text) {
  const row = el('div', 'line ' + (who === 'partner' ? 'agent sample-user' : 'sample-user'))
  row.append(el('span', 'who', who), el('span', 'said', text))
  $('transcript').append(row)
  $('transcript').scrollTop = $('transcript').scrollHeight
}

function sampleSpeech(text, who, done) {
  const finish = () => { sampleTimer = setTimeout(done, 420) }
  if (!window.speechSynthesis) {
    sampleTimer = setTimeout(done, Math.max(850, text.length * 32))
    return
  }
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'en-US'
  utterance.rate = who === 'partner' ? 0.98 : 0.92
  utterance.pitch = who === 'partner' ? 1.06 : 0.96
  utterance.onend = finish
  utterance.onerror = finish
  window.speechSynthesis.speak(utterance)
}

function playSampleLine(index, run) {
  if (!sampleMode || run !== sampleRun || index >= SAMPLE_LINES.length) {
    if (sampleMode && run === sampleRun) {
      if (typeof setStatus === 'function') setStatus('idle', 'Sample complete')
      feedback('Sample complete. Nothing was written to your workspace.')
    }
    return
  }
  const [who, text] = SAMPLE_LINES[index]
  appendSampleLine(who, text)
  if (index === 0) renderSampleEvents(1)
  if (index === 2) renderSampleEvents(3)
  if (index === 6) renderSampleEvents(4)
  if (typeof setStatus === 'function') setStatus(who === 'partner' ? 'speaking' : 'listening', who === 'partner' ? 'Sample partner is speaking' : 'Sample investor is speaking')
  sampleSpeech(text, who, () => playSampleLine(index + 1, run))
}

$('sample-btn').onclick = () => {
  if (sampleMode) { exitSample(); return }
  if (ws?.readyState <= 1) { feedback('End the current debrief before opening the sample.', true); return }
  companyBeforeSample = $('company').value
  sampleMode = true
  document.body.classList.add('sampling')
  $('company').value = 'GreenLeaf'
  $('sample-btn').textContent = 'Close sample ×'
  $('live-hint').textContent = 'Click a quote in the note to locate it in this conversation.'
  $('transcript').replaceChildren(el('div', 'sample-note', 'FICTIONAL CONVERSATION · ILLUSTRATIVE TIMING · NOT A LIVE AI RESULT'))
  sampleRun++
  renderLedger({ sessions: {} })
  feedback('Sample walkthrough starting. Listen as the note builds beside the conversation.')
  playSampleLine(0, sampleRun)
}
$('sample-close').onclick = exitSample

// ---------- upload: the recording note ----------

$('analyze-btn').onclick = () => {
  if (sampleMode) exitSample()
  if (!$('company').value.trim()) {
    feedback('Enter the company name before uploading a recording.', true)
    $('company').focus()
    return
  }
  $('file').click()
}
$('file').onchange = async () => {
  const file = $('file').files[0]; $('file').value = ''
  if (!file) return
  if (!file.size || file.size > 50 * 1024 * 1024) { feedback('Choose an audio file between 1 byte and 50 MB.', true); return }
  const company = $('company').value.trim()
  if (!company) { feedback('Enter the company name before uploading a recording.', true); $('company').focus(); return }
  const button = $('analyze-btn'); button.disabled = true; button.textContent = 'Transcribing & analyzing…'
  recordingText('recording-title', company)
  recordingText('recording-sub', company + ' · ' + file.name + ' · processing')
  recordingText('recording-source', 'PROCESSING', 'offline-status')
  const stats = $('recording-stats')
  if (stats) { stats.hidden = true; stats.replaceChildren() }
  const body = recordingElement('offline-body')
  if (!body) throw new Error('Recording report panel is unavailable. Please reopen the page.')
  body.replaceChildren(el('p', 'empty', 'Transcribing and analyzing the recording…'))
  document.body.classList.add('recording-open')
  showRecordingView(true)
  feedback('Processing ' + file.name + '. Longer recordings can take several minutes. Keep this page open.')
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 15 * 60 * 1000)
  try {
    const data = await fetch('/api/upload', { method: 'POST', headers: { 'X-Filename': encodeURIComponent(file.name), 'X-Company': encodeURIComponent(company) }, body: file, signal: controller.signal }).then(responseJSON)
    renderOffline(data, file.name, company)
    feedback('Analysis ready. Review the candidates, then download the recording note.')
  } catch (error) { renderOfflineError(error.name === 'AbortError' ? 'The request timed out. Try a shorter recording.' : error.message) }
  finally { clearTimeout(timeout); button.disabled = false; button.textContent = 'Upload a recording →' }
}
function renderOfflineError(message) {
  recordingText('recording-source', 'ERROR', 'offline-status')
  recordingText('recording-sub', 'The recording could not be analyzed')
  const stats = $('recording-stats')
  if (stats) { stats.hidden = true; stats.replaceChildren() }
  const body = recordingElement('offline-body')
  if (body) body.replaceChildren(el('p', 'empty', message))
  document.body.classList.add('recording-open')
  showRecordingView(true)
  feedback(message, true)
}
function renderOffline(data, name, company) {
  recordingText('recording-title', data.company || company || 'Recording review')
  recordingText('recording-sub', name + (data.language ? ' · ' + data.language.toUpperCase() : ''))
  recordingText('recording-source', (data.language || '').toUpperCase() || 'UPLOADED', 'offline-status')
  const body = recordingElement('offline-body')
  if (!body) throw new Error('Recording report panel is unavailable. Please reopen the page.')
  body.replaceChildren()
  const analysis = data.analysis || {}; const signals = analysis.signals || []; const questions = analysis.questions || []
  const followups = analysis.followup_checks || []
  const review = signals.filter(s => s.escalation)
  const other = signals.filter(s => !s.escalation)
  const stats = $('recording-stats')
  if (stats) stats.replaceChildren()
  for (const [label, value, hot] of [['signals', signals.length, false], ['to review', review.length, true], ['questions', questions.length, false]]) {
    const item = el('span', 'stat' + (hot ? ' hot' : ''))
    item.append(el('b', '', String(value)), document.createTextNode(label))
    if (stats) stats.append(item)
  }
  if (stats) stats.hidden = false
  body.append(el('div', 'notice', `${analysis.method === 'llm' ? 'AI analysis' : 'Keyword screening'} · ${analysis.notice || 'Verify every candidate against the recording.'}`))
  if (data.cached) body.append(el('p', 'empty', 'Saved transcription reused; analysis rerun.'))

  function section(title) {
    const node = el('section', 'recording-section')
    node.append(el('h3', 'recording-section-head', title))
    return node
  }
  if (review.length) {
    const node = section('Needs your review')
    review.forEach((s, i) => node.append(recordingEvidenceRow(s, 'R-' + pad(i + 1))))
    body.append(node)
  }
  if (other.length) {
    const node = section('Other observations')
    other.forEach((s, i) => node.append(recordingEvidenceRow(s, 'R-' + pad(review.length + i + 1))))
    body.append(node)
  }
  if (followups.length) {
    const node = section('Previous follow-up check')
    followups.forEach(check => node.append(followupRow(check)))
    body.append(node)
  }
  if (!signals.length) body.append(el('p', 'empty', 'No candidates matched. This does not establish that the company has no risks. Check the transcript for missed context.'))
  if (questions.length) {
    const node = section('Suggested questions for the next conversation')
    for (const q of questions) { const row = el('div', 'q-row'); row.append(el('span', 'q', '↗'), el('span', '', q.question)); node.append(row) }
    body.append(node)
  }
  const transcript = section('Source transcript')
  const details = el('details'); details.append(el('summary', '', 'Read the full transcript'), el('div', 'offline-transcript', data.text || 'No speech was transcribed.')); transcript.append(details); body.append(transcript)
  const bar = el('div', 'note-bar'); const download = el('button', 'export', 'Download recording note ↓')
  download.type = 'button'
  download.onclick = () => {
    const text = [`# Recording review — ${data.company || company || name}`, '', `Source file: ${name}`, `Analysis method: ${analysis.method || 'keyword'}`, analysis.notice || '', '', '## Previous follow-up check', ...followups.map(check => `\n- [${check.status}] ${check.task}${check.owner ? ` — ${check.owner}` : ''}${check.deadline ? `, due ${check.deadline}` : ''}${check.quote ? `\n  Quote: “${check.quote}”` : ''}${check.note ? `\n  Note: ${check.note}` : ''}`), '', '## Candidates (not final grades)', ...signals.map(s => `\n- ${s.signal}\n  Quote: “${s.quote}”\n  Checklist review: ${s.escalation ? 'needed' : 'not flagged'}`), '', '## Suggested questions (not agreed actions)', ...questions.map(q => '- ' + q.question), '', '## Transcript', data.text || '', '', 'Generated by Second Listen. Verify quotes against the audio.']
    downloadText(text.join('\n'), name.replace(/\.[^.]+$/, '') + '-review.md')
    feedback('Recording note downloaded.')
    clearCurrentAnalysis()
  }
  bar.append(download); body.append(bar)
  document.body.classList.add('recording-open')
  showRecordingView(true)
  const view = recordingElement('recording-view', 'offline-result')
  view?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// ---------- wiring ----------

const recordingClose = recordingElement('recording-close', 'offline-close')
if (recordingClose) recordingClose.onclick = () => {
  clearCurrentAnalysis()
}

$('btn-stop').onclick = () => stop()
$('company').addEventListener('change', () => { if (!sampleMode) refreshPrev() })
$('debug-toggle').onclick = () => { $('debug').hidden = !$('debug').hidden }
$('debug-close').onclick = () => { $('debug').hidden = true }

if (AGENT.preview) {
  $('preview-notice').hidden = false
  $('btn').disabled = true; $('analyze-btn').disabled = true; $('mic').disabled = true
}

// Do not restore the latest saved report on page load. The right pane is a
// blank workspace until the user starts a debrief or uploads a recording.
refreshLedger(false)
refreshPrev()
