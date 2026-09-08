// The page's client. Identical to the one in the JS starter: the
// audio worklets, the websocket session, and the transcript and event panes.
const $ = (id) => document.getElementById(id)
// The rate the API speaks. Both worklets resample, since a browser may
// ignore the rate an AudioContext asks for.
const WIRE_RATE = 24_000
const AGENT = window.AGENT

// Scratch buffers are reused: allocating on the audio thread causes glitches.
const CAPTURE_WORKLET = `
  class CaptureProcessor extends AudioWorkletProcessor {
    constructor() {
      super();
      this._ratio = sampleRate / ${WIRE_RATE};
      this._pos = 0;
      this._prev = 0;
      this._src = null;
      this._out = null;
    }
    _toPcm(samples, len) {
      const pcm = new Int16Array(len);
      for (let i = 0; i < len; i++) {
        const s = Math.max(-1, Math.min(1, samples[i]));
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      return pcm;
    }
    process(inputs) {
      const ch = inputs[0]?.[0];
      if (!ch) return true;
      if (this._ratio === 1) {
        const pcm = this._toPcm(ch, ch.length);
        this.port.postMessage(pcm.buffer, [pcm.buffer]);
        return true;
      }
      const n = ch.length;
      if (!this._src || this._src.length < n + 1) {
        this._src = new Float32Array(n + 1);
        this._out = new Float32Array(Math.ceil((n + 1) / this._ratio) + 2);
      }
      const src = this._src;
      const out = this._out;
      src[0] = this._prev;
      src.set(ch, 1);
      let outLen = 0;
      let pos = this._pos;
      while (pos < n) {
        const i = Math.floor(pos);
        const frac = pos - i;
        out[outLen++] = src[i] + (src[i + 1] - src[i]) * frac;
        pos += this._ratio;
      }
      this._pos = pos - n;
      this._prev = ch[n - 1];
      if (outLen) {
        const pcm = this._toPcm(out, outLen);
        this.port.postMessage(pcm.buffer, [pcm.buffer]);
      }
      return true;
    }
  }
  registerProcessor('capture', CaptureProcessor);
`

// A ring buffer rather than one AudioBufferSource per chunk, which drifts and
// clicks under jitter. Posting 'stop' empties it for barge-in.
const PLAYBACK_WORKLET = `
  class PlaybackProcessor extends AudioWorkletProcessor {
    constructor() {
      super();
      // Jitter buffer. First audio of a reply primes with a short fill so
      // speech starts ~130ms sooner; after an underrun the buffer refills to
      // the longer mark, so a burst of late frames still plays smoothly.
      this._prime = Math.round(sampleRate * 0.12);
      this._primeFull = Math.round(sampleRate * 0.25);
      this._primed = false;
      this._ring = new Float32Array(sampleRate * 30);
      this._writePos = 0;
      this._readPos = 0;
      this._available = 0;
      this._step = ${WIRE_RATE} / sampleRate;
      this._rsPos = 0;
      this._rsPrev = 0;
      // After a gap the speaker sits at zero, so interpolating from the
      // pre-gap _rsPrev would click. Reset it instead.
      this._drained = false;
      this.port.onmessage = (e) => {
        if (e.data === 'stop') {
          this._writePos = this._readPos = this._available = 0;
          this._rsPos = this._rsPrev = 0;
          this._primed = false;
          // A stop means the next audio is the start of a new reply.
          this._prime = Math.round(sampleRate * 0.12);
          return;
        }
        const int16 = new Int16Array(e.data);
        // int16[-1] would make _rsPrev NaN, silencing the ring for good.
        if (!int16.length) return;
        if (this._drained) {
          this._rsPrev = 0;
          this._rsPos = 0;
          this._drained = false;
        }
        if (this._step === 1) {
          for (let i = 0; i < int16.length; i++) this._push(int16[i] / 32768);
          return;
        }
        const n = int16.length;
        let pos = this._rsPos;
        while (pos < n) {
          const i = Math.floor(pos);
          const frac = pos - i;
          const a = i === 0 ? this._rsPrev : int16[i - 1] / 32768;
          const b = int16[i] / 32768;
          this._push(a + (b - a) * frac);
          pos += this._step;
        }
        this._rsPos = pos - n;
        this._rsPrev = int16[n - 1] / 32768;
      };
    }
    _push(v) {
      if (this._available < this._ring.length) {
        this._ring[this._writePos] = v;
        this._writePos = (this._writePos + 1) % this._ring.length;
        this._available++;
      }
    }
    process(inputs, outputs) {
      const output = outputs[0];
      const out = output[0];
      const cap = this._ring.length;
      if (!this._primed && this._available < this._prime) {
        // Silence while the first chunk of the reply buffers up.
        for (let i = 0; i < out.length; i++) out[i] = 0;
        for (let ch = 1; ch < output.length; ch++) output[ch].set(out);
        return true;
      }
      this._primed = true;
      for (let i = 0; i < out.length; i++) {
        if (this._available > 0) {
          out[i] = this._ring[this._readPos];
          this._readPos = (this._readPos + 1) % cap;
          this._available--;
        } else {
          out[i] = 0;
          if (!this._drained) {
            // Ran dry mid-reply: the network is jittering, so ask for the
            // longer fill before playback resumes.
            this._drained = true;
            this._prime = this._primeFull;
          }
        }
      }
      if (this._available === 0) this._primed = false;
      // Mono source, stereo sink.
      for (let ch = 1; ch < output.length; ch++) output[ch].set(out);
      return true;
    }
  }
  registerProcessor('playback', PlaybackProcessor);
`

const blobUrl = (code) =>
  URL.createObjectURL(new Blob([code], { type: 'application/javascript' }))

let ws, captureCtx, playbackCtx, playback, mic, callStart, timer
let callGeneration = 0, connectionDeadline
let sessionId = null
let endRequested = false
let serverEnded = false
// Client-side tools: hold results until the turn is idle (reply.done).
let lastEvent = null
const pendingTools = []
// --- duplicate agent-burst guard ---
// The platform can emit several back-to-back agent replies after a batch of
// tool results (Round 1.9: four near-identical "Noted. Does the agreement..."
// questions in a row). An agent reply that starts while no user speech has
// happened since the last agent reply is a burst artifact: keep the first,
// drop the rest until the user actually speaks again.
let lastAgentReplyAt = 0
let userSpokeSinceReply = true
let suppressReply = false
// A tool result intentionally causes a new agent reply without a new user
// turn. Keep that reply out of the duplicate-burst guard; otherwise the
// first answer after a logged signal is silently discarded as a duplicate.
let toolReplyExpected = false

// --- microphones ---

// --- semantic gate ---
// The voice API only lets the agent take the floor once its end-of-turn model
// decides the user finished, and then the agent needs ~2s before audio comes
// out. A speaker who pauses under ~2.5s between sentences buries every chance
// to interject, so the debrief becomes a monologue and the questions get
// dumped at the end (observed 2026-09-02: 94s of continuous speech, zero
// interjections). The gate watches the live user transcript and, near a
// finished-sentence boundary inside a long run of speech, briefly stops
// sending mic audio. The forced silence ends the turn, the agent answers, and
// the mic reopens as soon as the reply starts.
function sentEnds(text) {
  let n = 0
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (ch === '\u3002' || ch === '\uff01' || ch === '\uff1f' || ch === '\u2026') n++
  }
  return n
}
const isSentEnd = (ch) => ch === '\u3002' || ch === '\uff01' || ch === '\uff1f' || ch === '\u2026'
function lastSentAt(text) {
  for (let i = text.length - 1; i >= 0; i--) if (isSentEnd(text[i])) return i
  return -1
}
const GATE = {
  enabled: false, // A/B switch (2026-09-03): natural-pause turn-taking instead
                  // of the semantic gate. Flip to true to re-enable the gate.
  sentences: 2,   // finished sentences in the current run before we may fire
  chars: 40,      // and at least this much speech since the agent last spoke
  afterAgentMs: 6000, // agent must have last spoken at least this long ago
  gapMs: 3000,    // never fire twice within this window
  muteMs: 2000,   // hold the mic quiet: end-of-turn (~0.5s) + reply latency;
                  // reply.started reopens sooner, voice check reopens instantly
  lateChars: 6,   // ...or this many chars after the last sentence end
  forceMs: 15000, // failsafe: fire even without punctuation on a run this long
}
let gate = {
  sentences: 0,  // sentence ends seen since the agent last spoke / last fire
  chars: 0,      // user text growth in the same window
  prevLen: -1,   // length of the previous user partial we saw
  prevEnds: 0,   // sentence-end count of that partial
  agentEndAt: 0, // when the last agent reply finished
  lastFireAt: 0, // when the gate last fired
  runStartAt: 0, // when the current run of user speech started
  mutedUntil: 0, // input.audio suppressed until this epoch ms
  busy: false,   // agent reply is in progress
  armed: false,  // text conditions met; waiting for acoustic quiet to fire
}
const gateMuted = () => Date.now() < gate.mutedUntil
function gateNote(text, now) {
  if (!GATE.enabled) return false
  // text is the full user partial so far and replaces the previous one. A
  // large shrink means the previous partial was committed (new VAD turn), so
  // per-partial tracking restarts while the run keeps counting across the
  // user's continuous speech. now is injectable for tests.
  if (now === undefined) now = Date.now()
  const ends = sentEnds(text)
  if (gate.prevLen < 0 || text.length < gate.prevLen - 10) {
    if (gate.runStartAt === 0) gate.runStartAt = now
    gate.prevLen = text.length
    gate.prevEnds = ends
    return false
  }
  gate.chars += Math.max(0, text.length - gate.prevLen)
  gate.sentences += Math.max(0, ends - gate.prevEnds)
  gate.prevLen = text.length
  gate.prevEnds = ends
  if (gate.busy) return false
  if (now - gate.agentEndAt < GATE.afterAgentMs) return false
  if (now - gate.lastFireAt < GATE.gapMs) return false
  // Three ways to arm: the partial ends right on a sentence stop; the user
  // already spoke a few chars past a sentence end (punctuation may land in
  // the middle of a delta frame, so tail-only checks miss it); or the run is
  // simply so long that punctuation never came. Arming does not mute -- the
  // fire waits for real acoustic quiet in gateCheck, so continuous speech is
  // never cut mid-word.
  const tail = lastSentAt(text)
  const past = text.length - 1 - tail
  const mature = gate.sentences >= GATE.sentences && gate.chars >= GATE.chars
  const fast = mature && tail === text.length - 1
  const late = mature && tail >= 0 && past >= GATE.lateChars
  const slow = gate.chars >= GATE.chars && now - gate.runStartAt >= GATE.forceMs
  if (fast || late || slow) gate.armed = true
  return false
}
function gateReset() {
  gate.sentences = 0
  gate.chars = 0
  gate.prevLen = -1
  gate.prevEnds = 0
  gate.agentEndAt = 0
  gate.lastFireAt = 0
  gate.runStartAt = 0
  gate.mutedUntil = 0
  gate.busy = false
  gate.armed = false
}
// --- gate v3: local voice energy ---
// The transcript cannot show a pause (it only carries words), and muting on
// text alone is what cut sentences in half: the user's next words fell into
// the mute window and were lost. The raw mic stream is analysed locally
// instead -- the analyser sits outside the send path, so it keeps hearing
// while the mic is muted. An armed gate fires only after the user has been
// quiet for ENERGY.silenceMs, and if they start talking again while muted,
// the mic reopens at once.
const ENERGY = {
  pollMs: 40,      // analyser poll interval
  fftSize: 2048,   // ~85ms of audio per RMS window at the 24kHz wire rate
  floorMs: 500,    // the first moments after start calibrate the noise floor
  mult: 3.5,       // voice = rms above the calibrated floor by this factor...
  absMin: 0.004,   // ...and above this absolute level, so a hot mic still needs real signal
  silenceMs: 300,  // quiet this long before an armed gate may fire
}
let energyAnalyser = null
let energyBuf = null
let energyTimer = null
let noiseFloor = 0.002
let lastVoiceAt = 0
let sessionStartAt = 0

function pollEnergy() {
  if (!energyAnalyser) return
  energyAnalyser.getFloatTimeDomainData(energyBuf)
  let sum = 0
  for (let i = 0; i < energyBuf.length; i++) sum += energyBuf[i] * energyBuf[i]
  const rms = Math.sqrt(sum / energyBuf.length)
  const now = Date.now()
  if (now - sessionStartAt < ENERGY.floorMs) {
    // Calibration window: nobody talks in the first half second after
    // clicking Start, so the quietest reading stands in for the room.
    if (rms < noiseFloor) noiseFloor = rms
    return
  }
  if (rms >= Math.max(noiseFloor * ENERGY.mult, ENERGY.absMin)) {
    lastVoiceAt = now
    if (gateMuted()) {
      // The user was not done: hand the floor back before the platform
      // commits the turn and the agent starts over their sentence.
      gate.mutedUntil = 0
      logEvent('gate', 'mic open', 'voice during mute')
    }
    return
  }
  // Below the voice line it is room noise; follow it so the floor stays
  // honest when a fan spins up or the room goes quieter.
  noiseFloor = noiseFloor * 0.9 + rms * 0.1
}

function gateCheck() {
  if (!GATE.enabled) return
  const now = Date.now()
  if (!gate.armed || gate.busy || gateMuted()) return
  if (now - gate.agentEndAt < GATE.afterAgentMs) return
  if (now - gate.lastFireAt < GATE.gapMs) return
  if (now - lastVoiceAt < ENERGY.silenceMs) return
  gate.armed = false
  gate.mutedUntil = now + GATE.muteMs
  gate.lastFireAt = now
  gate.runStartAt = now
  gate.sentences = 0
  gate.chars = 0
  gate.prevLen = -1
  gate.prevEnds = 0
  const at = (callStart ? (Date.now() - callStart) / 1000 : 0).toFixed(1)
  logEvent('gate', 'semantic gate', 'mic muted ' + GATE.muteMs + 'ms')
  fetch('/api/gate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, at_seconds: Number(at), kind: 'fire' }),
  }).catch(() => {})
}

function startEnergy() {
  sessionStartAt = lastVoiceAt = Date.now()
  noiseFloor = 0.002
  if (!energyTimer) {
    energyTimer = setInterval(() => { pollEnergy(); gateCheck() }, ENERGY.pollMs)
  }
}

function stopEnergy() {
  clearInterval(energyTimer)
  energyTimer = null
  energyAnalyser = null
}
// Labels stay empty until mic permission is granted, so this runs again after
// getUserMedia.
async function listMics() {
  if (!navigator.mediaDevices?.enumerateDevices) return
  const devices = await navigator.mediaDevices.enumerateDevices()
  const inputs = devices
    .filter((device) => device.kind === 'audioinput')
    // Chrome's synthetic entries alias a real device and duplicate it.
    .filter((device) => device.deviceId !== 'default' && device.deviceId !== 'communications')
  const select = $('mic')
  const chosen = select.value
  select.replaceChildren()
  const auto = document.createElement('option')
  auto.value = ''
  auto.textContent = 'Default microphone'
  select.append(auto)
  inputs.forEach((device, i) => {
    const option = document.createElement('option')
    option.value = device.deviceId
    option.textContent = device.label || `Microphone ${i + 1}`
    select.append(option)
  })
  if (chosen && inputs.some((device) => device.deviceId === chosen)) select.value = chosen
}
listMics().catch(() => {})
navigator.mediaDevices?.addEventListener?.('devicechange', listMics)

$('btn').onclick = () => (ws?.readyState <= 1 ? stop() : start())

// --- side pane tabs (debug drawer: events / agent) ---
let agentLoaded = false

function showTab(name) {
  for (const tab of ['events', 'agent']) {
    const button = $('tab-' + tab), panel = $(tab + '-body')
    if (!button || !panel) continue
    button.classList.toggle('on', tab === name)
    button.setAttribute('aria-selected', String(tab === name))
    button.tabIndex = tab === name ? 0 : -1
    panel.hidden = tab !== name
  }
  if (name === 'agent' && !agentLoaded) {
    agentLoaded = true
    fetch('/agent')
      .then((res) => res.json())
      .then((agent) => {
        $('agent-body').replaceChildren()
        const pre = document.createElement('pre')
        pre.textContent = JSON.stringify(agent, null, 2)
        $('agent-body').append(pre)
      })
      .catch(() => {
        agentLoaded = false
        $('agent-body').textContent = 'Could not load the agent.'
      })
  }
}
$('tab-events').onclick = () => showTab('events')
$('tab-agent').onclick = () => showTab('agent')
async function addWorklet(ctx, code, name) {
  const url = blobUrl(code)
  try {
    await ctx.audioWorklet.addModule(url)
  } finally {
    URL.revokeObjectURL(url)
  }
  return new AudioWorkletNode(ctx, name)
}

async function fetchVoiceToken() {
  const retryableStatuses = new Set([408, 429, 500, 502, 503, 504])
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await fetch('/token', { cache: 'no-store', headers: { Accept: 'application/json' } })
      const body = await res.json().catch(() => ({}))
      if (res.ok) {
        if (typeof body.token !== 'string' || !body.token.trim()) {
          throw new Error('Voice token was not returned. Please retry.')
        }
        return body.token.trim()
      }
      const error = new Error(body.error || 'Voice token service is unavailable. Please retry.')
      error.status = res.status
      if (!retryableStatuses.has(res.status) || attempt === 2) throw error
    } catch (error) {
      // A transient browser/network failure has no Response status. Retry it
      // alongside the retryable upstream statuses, but never retry a client
      // rejection such as the server's cross-origin or auth response.
      if (attempt === 2 || (error.name !== 'TypeError' && !retryableStatuses.has(error.status))) {
        throw error
      }
    }
    await new Promise(resolve => setTimeout(resolve, 700 * (attempt + 1)))
  }
}

async function start() {
  if (AGENT.preview) return
  exitSample()
  const company = $('company').value.trim()
  if (!company) { feedback('Enter the company name before starting your debrief.', true); $('company').focus(); return }
  if (!navigator.mediaDevices?.getUserMedia) { feedback('Microphone access requires HTTPS or localhost.', true); return }
  liveCompany = company
  // A recording review can occupy the right card after an upload. Starting a
  // new live debrief is a new workflow, so switch the card back immediately
  // and prepare the prior commitments for this next conversation.
  if (typeof prepareDebriefView === 'function') prepareDebriefView()
  const generation = ++callGeneration
  endRequested = false
  serverEnded = false
  sessionId = null; selectedSession = null; pendingTools.length = 0; lastEvent = null
  printedReply = liveReply = null
  $('company').disabled = true
  $('sample-btn').disabled = true
  $('transcript').replaceChildren()
  $('elapsed').textContent = '0:00'
  feedback('')
  $('btn').disabled = true
  $('mic').disabled = true
  setStatus('connecting')

  try {
    if (AGENT.config) {
      const context = await fetch('/api/context?company=' + encodeURIComponent(company)).then(responseJSON)
      AGENT.config = context.config
    }
    // The API key never reaches the page; this token expires in 60 seconds.
    // Fetch immediately before each connection. The temporary token is
    // single-use and the API key remains on the server.
    const token = await fetchVoiceToken()

    // Two contexts, created in the click handler so Safari starts them.
    captureCtx = new AudioContext({ sampleRate: WIRE_RATE })
    playbackCtx = new AudioContext({ sampleRate: WIRE_RATE })
    await Promise.all([captureCtx.resume(), playbackCtx.resume()])

    playback = await addWorklet(playbackCtx, PLAYBACK_WORKLET, 'playback')
    playback.connect(playbackCtx.destination)

    const deviceId = $('mic').value
    mic = await navigator.mediaDevices.getUserMedia({
      audio: {
        // A preference, not `exact`: an unplugged device falls back.
        ...(deviceId ? { deviceId } : {}),
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: false,
        autoGainControl: false,
      },
    })
    listMics()
    const capture = await addWorklet(captureCtx, CAPTURE_WORKLET, 'capture')
    const micSource = captureCtx.createMediaStreamSource(mic)
    micSource.connect(capture)
    // Local voice-energy tap for the gate. It hangs off the same source but
    // is not in the send path, so it keeps hearing while the mic is muted.
    energyAnalyser = captureCtx.createAnalyser()
    energyAnalyser.fftSize = ENERGY.fftSize
    energyBuf = new Float32Array(ENERGY.fftSize)
    micSource.connect(energyAnalyser)
    startEnergy()

    const url = new URL('wss://agents.assemblyai.com/v1/ws')
    url.searchParams.set('token', token)
    ws = new WebSocket(url)
    let ready = false
    const socket = ws
    connectionDeadline = setTimeout(() => {
      if (generation !== callGeneration || ready) return
      setStatus('error', 'Connection timed out. Try again.'); socket.close(); reset()
    }, 20000)

    // The API takes base64 inside JSON, not binary frames.
    capture.port.onmessage = ({ data }) => {
      // Semantic gate: while muted we drop mic frames. The resulting silence
      // makes the platform end the user's turn so the agent can answer.
      if (gateMuted()) return
      if (!ready || ws.readyState !== 1) return
      const bytes = new Uint8Array(data)
      let binary = ''
      for (let i = 0; i < bytes.length; i += 0x8000) {
        binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000))
      }
      ws.send(JSON.stringify({ type: 'input.audio', audio: btoa(binary) }))
      logEvent('up', 'input.audio')
    }

    // Everything about the agent lives server-side; the session just names it.
    ws.onopen = () => {
      if (generation !== callGeneration) return
      if (AGENT.config) {
        // Inline mode: no stored agent; send the config fields directly.
        // Tools have to ride along -- the session service does not read them
        // from anywhere else here, and without them the agent never calls
        // log_evidence or add_action_item, so the ledger stays empty.
        ws.send(JSON.stringify({ type: 'session.update', session: {
          system_prompt: AGENT.config.system_prompt,
          greeting: AGENT.config.greeting,
          output: { voice: AGENT.config.voice.voice_id },
          tools: AGENT.config.tools || [],
          ...(AGENT.config.input ? { input: AGENT.config.input } : {}),
        } }))
        logEvent('up', 'session.update', 'inline config')
      } else {
        ws.send(JSON.stringify({ type: 'session.update', session: { agent_id: AGENT.id } }))
        logEvent('up', 'session.update', AGENT.id)
      }
    }

    ws.onmessage = ({ data }) => {
      if (generation !== callGeneration) return
      let msg
      try { msg = JSON.parse(data) } catch { logEvent('down', 'protocol.error', 'Invalid message'); return }
      switch (msg.type) {
        case 'session.ready':
          ready = true
          clearTimeout(connectionDeadline)
          sessionId = msg.session_id
          callStart = Date.now()
          timer = setInterval(tick, 1000)
          tick()
          refreshLedger()
          setStatus('listening')
          $('btn').disabled = false
          $('btn').classList.add('live')
          logEvent('down', msg.type, msg.session_id)
          break

        case 'input.speech.started':
          lastEvent = 'input.speech.started'
          userSpokeSinceReply = true
          // Barge-in: empty the ring buffer so the agent stops mid-word.
          playback?.port.postMessage('stop')
          setStatus('listening')
          logEvent('down', msg.type)
          break

        case 'reply.started':
          lastEvent = 'reply.started'
          if (toolReplyExpected) {
            toolReplyExpected = false
            logEvent('down', 'reply.continuation', 'after tool result')
          } else if (!userSpokeSinceReply && lastAgentReplyAt > 0) {
            // No user speech since the last agent reply: back-to-back burst.
            suppressReply = true
            logEvent('down', 'reply.suppressed', 'no user turn between replies')
            break
          }
          lastAgentReplyAt = Date.now()
          userSpokeSinceReply = false
          gate.busy = true
          gate.armed = false
          if (gateMuted()) {
            // The agent is speaking: reopen the mic so the user can answer.
            gate.mutedUntil = 0
            logEvent('gate', 'mic open', 'reply started')
          }
          setStatus('speaking')
          logEvent('down', msg.type)
          break

        case 'reply.audio': {
          if (suppressReply) break
          const raw = atob(msg.data)
          const bytes = new Uint8Array(raw.length)
          for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i)
          playback?.port.postMessage(bytes.buffer, [bytes.buffer])
          logEvent('down', msg.type)
          break
        }

        case 'reply.done':
          lastEvent = 'reply.done'
          if (suppressReply) {
            suppressReply = false
            logEvent('down', 'reply.done', 'suppressed burst reply')
            break
          }
          gate.busy = false
          gate.agentEndAt = Date.now()
          gate.sentences = 0
          gate.chars = 0
          gate.runStartAt = 0
          gate.prevLen = -1
          gate.prevEnds = 0
          setStatus('listening')
          if (msg.status === 'interrupted') {
            playback?.port.postMessage('stop')
            pendingTools.length = 0
          } else {
            flushTools()
          }
          logEvent('down', msg.type, msg.status)
          break

        // text is the full transcript so far, so it replaces.
        case 'transcript.user.delta':
          userSpokeSinceReply = true
          partial('you', msg.text)
          logEvent('down', msg.type, msg.text)
          gateNote(msg.text || '')
          break

        // delta is the next word only, so it appends.
        case 'transcript.agent.delta':
          if (suppressReply) break
          logEvent('down', msg.type, msg.delta)
          if (msg.reply_id && msg.reply_id === printedReply) break
          if (msg.reply_id !== liveReply) {
            liveReply = msg.reply_id
            dropPartial('agent')
          }
          partial('agent', appendDelta(partialText.agent || '', msg.delta))
          break

        case 'transcript.user':
          userSpokeSinceReply = true
          addLine('you', msg.text)
          logEvent('down', msg.type, msg.text)
          break

        case 'transcript.agent':
          if (suppressReply) break
          printedReply = msg.reply_id ?? printedReply
          addLine('agent', msg.text)
          logEvent('down', msg.type, msg.text)
          break

        case 'tool.call': {
          // Client-side tool: persist locally, then answer at the turn
          // boundary. The result waits for the POST to settle -- the system
          // prompt forbids the agent from claiming a record exists unless it
          // really does, so a failed write must answer ok:false, not a
          // canned {recorded:true}.
          const args = msg.arguments ?? {}
          const at = (callStart ? (Date.now() - callStart) / 1000 : 0).toFixed(1)
          logEvent('down', msg.type, `${msg.name} ${JSON.stringify(args)}`)
          addLine('tool', `${msg.name}(${JSON.stringify(args)}) @${at}s`)
          fetch('/api/ledger', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              session_id: sessionId,
              company: liveCompany,
              call_id: msg.call_id,
              elapsed_seconds: Number(at),
              name: msg.name,
              arguments: args,
            }),
          })
            .then((res) => {
              if (!res.ok) throw new Error('ledger write failed')
              return res.json()
            })
            .then(() => {
              if (generation === callGeneration) refreshLedger()
              return { ok: true, recorded: true }
            })
            .catch(() => {
              logEvent('down', 'ledger.error', msg.name + ' was NOT saved')
              if (generation === callGeneration) feedback('An item could not be saved. Ask your partner to retry before ending the debrief.', true)
              return { ok: false, recorded: false }
            })
            .then((result) => {
              if (generation !== callGeneration || socket.readyState !== 1) return
              pendingTools.push({ call_id: msg.call_id, result: JSON.stringify(result), is_error: !result.ok })
              flushTools()
            })
          break
        }

        case 'session.ended':
          logEvent('down', msg.type)
          serverEnded = true
          requestArchive()
          socket.close()
          break

        case 'session.error':
          setStatus('error', msg.message)
          logEvent('down', msg.type, `${msg.code}: ${msg.message}`)
          socket.close(); reset()
          break

        default:
          logEvent('down', msg.type)
      }
    }

    ws.onclose = () => {
      if (generation !== callGeneration) return
      const endedNormally = endRequested || serverEnded
      const endedSessionId = sessionId
      const endedCompany = liveCompany
      requestArchive()
      if (!$('status').classList.contains('error')) setStatus('idle')
      reset()
      // Pull the final ledger first, then carry confirmed actions forward. Do
      // not wait for archive completion or report repaint before saving.
      refreshLedger(false).then(() => {
        const carry = endedNormally && typeof autoSaveFollowUps === 'function'
          ? autoSaveFollowUps(endedSessionId, endedCompany)
          : Promise.resolve()
        return Promise.resolve(carry).finally(() => renderLedger(lastLedger))
      })
    }
    ws.onerror = () => {
      if (generation !== callGeneration) return
      setStatus('error', 'Connection failed. Please try again.'); socket.close(); reset()
    }
  } catch (error) {
    setStatus('error', error.message)
    reset()
  }
}

function stop() {
  // Close cleanly so the session record ends, falling back to the socket.
  if (ws?.readyState === 1) {
    endRequested = true
    ws.send(JSON.stringify({ type: 'session.end' }))
    logEvent('up', 'session.end')
    const socket = ws
    setTimeout(() => { if (socket.readyState === 1) socket.close() }, 3000)
  } else {
    ws?.close()
  }
  // Fallback for sockets that close without a session.ended frame; the
  // server dedupes and retries until the artifacts exist.
  requestArchive()
  playback?.port.postMessage('stop')
  mic?.getTracks().forEach((track) => track.stop())
  captureCtx?.close()
  playbackCtx?.close()
  captureCtx = playbackCtx = playback = mic = null
  reset()
  setStatus('idle')
}

function reset() {
  clearTimeout(connectionDeadline)
  clearInterval(timer)
  mic?.getTracks().forEach(track => track.stop())
  playback?.port.postMessage('stop')
  captureCtx?.close().catch(() => {})
  playbackCtx?.close().catch(() => {})
  captureCtx = playbackCtx = playback = mic = null
  pendingTools.length = 0; lastEvent = null
  $('company').disabled = false
  $('sample-btn').disabled = false
  stopEnergy()
  clearPartials()
  gateReset()
  lastAgentReplyAt = 0
  userSpokeSinceReply = true
  suppressReply = false
  toolReplyExpected = false
  open.forEach((run) => paint(run, true))
  open.clear()
  $('btn').disabled = false
  $('mic').disabled = false
  $('btn').classList.remove('live')
}

function setStatus(state, detail) {
  // The console swaps between the idle card and the live recorder on this class.
  document.body.classList.toggle('calling', state !== 'idle')
  $('status').className = 'status ' + state
  $('status-text').textContent = detail || ({idle:'Ready when you are',connecting:'Connecting…',listening:'Listening to you',speaking:'Your partner is speaking'}[state] || state)
}

// $4.50 an hour, the list price at assemblyai.com/pricing. Billing is per
// session minute, so the running figure is an estimate, not an invoice.
const COST_PER_SECOND = 4.5 / 3600

function tick() {
  const seconds = Math.floor((Date.now() - callStart) / 1000)
  $('elapsed').textContent =
    Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0')
  $('cost').textContent = '$' + (seconds * COST_PER_SECOND).toFixed(3)
}

// --- transcript ---
const partialText = {}
const partialEl = {}
// The full reply arrives once its audio has been sent, which beats the audio
// playing out, so deltas keep coming after the line is printed. printedReply
// stops them rebuilding the same sentence underneath it.
let liveReply = null
let printedReply = null

// Deltas arrive with a leading space sometimes and without it other times, so
// add one only when neither side has one and the delta is not punctuation.
const ATTACHES_LEFT = /^[.,!?;:%°)\]}…'"’”]/
const NO_SPACE_AFTER = /[([{$\-\/'"‘“]$/

function appendDelta(text, delta) {
  if (!delta) return text
  if (!text) return delta
  if (/^\s/.test(delta) || /\s$/.test(text)) return text + delta
  if (ATTACHES_LEFT.test(delta) || NO_SPACE_AFTER.test(text)) return text + delta
  return text + ' ' + delta
}

function dropPartial(who) {
  partialEl[who]?.remove()
  delete partialEl[who]
  delete partialText[who]
}

function transcriptLine(who, text, cls) {
  const line = document.createElement('div')
  line.className = 'line ' + who + (cls ? ' ' + cls : '')
  const label = document.createElement('span')
  label.className = 'who'
  label.textContent = who === 'agent' ? AGENT.name : who
  const body = document.createElement('span')
  body.className = 'said'
  body.textContent = text
  line.append(label, body)
  return line
}

function clearEmpty(el) {
  const empty = el.querySelector('.empty')
  if (empty) empty.remove()
}

function scroll(el) {
  el.scrollTop = el.scrollHeight
}

function partial(who, text) {
  clearEmpty($('transcript'))
  partialText[who] = text
  if (partialEl[who]) {
    partialEl[who].querySelector('.said').textContent = text
  } else {
    partialEl[who] = transcriptLine(who, text, 'partial')
    $('transcript').append(partialEl[who])
  }
  scroll($('transcript'))
}

function addLine(who, text) {
  clearEmpty($('transcript'))
  dropPartial(who)
  $('transcript').append(transcriptLine(who, text))
  scroll($('transcript'))
}

function clearPartials() {
  for (const who of Object.keys(partialEl)) dropPartial(who)
  liveReply = printedReply = null
}

// --- event log ---
// Audio frames arrive ~190 times a second each way, so these types hold a row
// open and count into it. Both streams run at once, hence a row per key.
const COALESCE = new Set([
  'input.audio',
  'reply.audio',
  'transcript.user.delta',
  'transcript.agent.delta',
])
const open = new Map()

function eventRow(direction, type, detail) {
  const row = document.createElement('div')
  row.className = 'event ' + direction
  const at = document.createElement('span')
  at.className = 'at'
  at.textContent = (callStart ? (Date.now() - callStart) / 1000 : 0).toFixed(1) + 's'
  const arrow = document.createElement('span')
  arrow.className = 'dir'
  arrow.textContent = direction === 'up' ? '↑' : '↓'
  const name = document.createElement('span')
  name.className = 'type'
  name.textContent = type
  const count = document.createElement('span')
  count.className = 'count'
  const info = document.createElement('span')
  info.className = 'detail'
  if (detail) info.textContent = detail
  row.append(at, arrow, name, count, info)
  return row
}

// Ten repaints a second, plus one when the run closes.
function paint(live, final) {
  const now = performance.now()
  if (!final && now - live.painted < 100) return
  live.painted = now
  live.row.querySelector('.count').textContent = live.count > 1 ? '×' + live.count : ''
  if (live.detail) live.row.querySelector('.detail').textContent = live.detail
}

function logEvent(direction, type, detail) {
  const log = $('events-body')
  clearEmpty(log)
  const key = direction + ' ' + type
  const live = open.get(key)
  if (live) {
    live.count += 1
    if (detail) live.detail = detail
    paint(live)
    return
  }
  // A real event closes the open runs, so the next burst starts a new row.
  if (!COALESCE.has(type)) {
    open.forEach((run) => paint(run, true))
    open.clear()
  }
  // Only follow the tail if the reader is there.
  const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40
  const row = eventRow(direction, type, detail)
  log.append(row)
  while (log.children.length > 400) log.firstChild.remove()
  if (COALESCE.has(type)) open.set(key, { row, count: 1, detail, painted: 0 })
  if (atBottom) scroll(log)
}

// --- client-side tools + ledger ---

const archivedRequested = new Set()

function requestArchive() {
  if (!sessionId || archivedRequested.has(sessionId)) return
  archivedRequested.add(sessionId)
  fetch('/api/archive', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  }).catch(() => {})
}

function flushTools() {
  if (lastEvent !== 'reply.done' || !pendingTools.length || ws?.readyState !== 1) return
  toolReplyExpected = true
  for (const tool of pendingTools.splice(0)) {
    ws?.send(JSON.stringify({
      type: 'tool.result',
      call_id: tool.call_id,
      result: tool.result,
      is_error: tool.is_error,
    }))
  }
}
