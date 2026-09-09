#!/usr/bin/env python3
"""Second Listen browser deployment. Python standard library only.

Default: local, inline voice config. DEMO_ONLY=1 runs without API credentials.
Remote live deployments require HTTPS at the reverse proxy. APP_PASSWORD is an
optional extra gate; the public contest demo uses bounded, in-memory capacity
limits instead.
"""
import base64
import copy
import hashlib
import hmac
import html
import json
import math
import os
import re
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from lib import ApiError, aai, atomic_write_text, ensure_agent, load_env, read_agent, read_json, required
from archive import DEFAULT_TRIALS_DIR, archive_async
import transcribe
import analyze
import history
from history_from_ledger import build_history, merge_action_fields, normalize_action_task, slugify
from note import build_note

DEFAULT_DATA_DIR = HERE.parents[1] / 'data'
LEDGER = DEFAULT_DATA_DIR / 'ledger.json'
GATE_LOG = DEFAULT_DATA_DIR / 'gate_log.json'
TRIALS_DIR = Path(os.environ.get('TRIALS_DIR') or DEFAULT_DATA_DIR / 'trials')
TRANSCRIPT_CACHE = Path(os.environ.get('TRANSCRIPT_CACHE_DIR') or DEFAULT_DATA_DIR / 'transcript_cache')
LEDGER_LOCK = threading.Lock()
UPLOAD_SLOTS = threading.BoundedSemaphore(2)
AGENT = None
PAGE = ''
DIMENSIONS = {'operations', 'exit_potential', 'self_funding', 'team_integrity', 'financial_health'}
TOKEN_EXPIRES_IN_SECONDS = 60
DEFAULT_SESSION_MAX_DURATION_SECONDS = 300
MIN_SESSION_MAX_DURATION_SECONDS = 60
MAX_SESSION_MAX_DURATION_SECONDS = 300

# Public demo guardrails. These limits are intentionally conservative: a normal
# visitor needs one token, while a shared contest link must not mint unlimited
# billable Voice Agent sessions. They reset when this single free-tier process
# restarts, so they complement (rather than replace) the upstream account limit.
PUBLIC_OPERATION_LIMITS = {
    'token': {'window_seconds': 15 * 60, 'per_client': 2, 'global': 6},
    'upload': {'window_seconds': 60 * 60, 'per_client': 1, 'global': 3},
}
PUBLIC_OPERATION_GRANTS = {operation: [] for operation in PUBLIC_OPERATION_LIMITS}
PUBLIC_OPERATION_LOCK = threading.Lock()


class TokenError(Exception):
    """A safe, user-facing failure from the temporary-token proxy."""
    def __init__(self, message: str, code: str = 'token_unavailable'):
        super().__init__(message)
        self.code = code


def debug_log(*args):
    if os.environ.get('DEBUG'):
        print(*args, file=sys.stderr)


def demo_only():
    return os.environ.get('DEMO_ONLY') == '1'


def session_max_duration_seconds():
    """Return a bounded live-session limit for the public contest demo."""
    raw = os.environ.get('VOICE_SESSION_MAX_DURATION_SECONDS', str(DEFAULT_SESSION_MAX_DURATION_SECONDS))
    try:
        seconds = int(raw)
    except ValueError:
        debug_log('invalid VOICE_SESSION_MAX_DURATION_SECONDS; using default')
        return DEFAULT_SESSION_MAX_DURATION_SECONDS
    if not MIN_SESSION_MAX_DURATION_SECONDS <= seconds <= MAX_SESSION_MAX_DURATION_SECONDS:
        debug_log('out-of-range VOICE_SESSION_MAX_DURATION_SECONDS; using default')
        return DEFAULT_SESSION_MAX_DURATION_SECONDS
    return seconds


def reserve_public_operation(operation, client, now=None):
    """Reserve one bounded public operation, returning its opaque reservation.

    The global cap remains effective if a caller rotates spoofable forwarded IP
    headers. Reservation happens before the upstream request so concurrent
    callers cannot all pass the same capacity check.
    """
    rule = PUBLIC_OPERATION_LIMITS[operation]
    now = time.monotonic() if now is None else now
    with PUBLIC_OPERATION_LOCK:
        grants = PUBLIC_OPERATION_GRANTS[operation]
        cutoff = now - rule['window_seconds']
        grants[:] = [grant for grant in grants if grant[0] > cutoff]
        if len(grants) >= rule['global']:
            return None
        if sum(grant[1] == client for grant in grants) >= rule['per_client']:
            return None
        reservation = (now, client)
        grants.append(reservation)
        return reservation


def release_public_operation(operation, reservation):
    """Release a reservation when no upstream request was successfully made."""
    with PUBLIC_OPERATION_LOCK:
        grants = PUBLIC_OPERATION_GRANTS[operation]
        try:
            grants.remove(reservation)
        except ValueError:
            pass


def public_agent(agent):
    copied = copy.deepcopy(agent)
    for tool in copied.get('tools', []):
        for header in (tool.get('http') or {}).get('headers', []):
            header['value'] = '<hidden>'
    for llm in copied.get('llm', []):
        llm.pop('api_key', None)
    return copied


def render_page():
    """Render the current HTML shell so a long-lived dev server cannot serve stale markup."""
    return ((HERE / 'index.html').read_text(encoding='utf-8')
            .replace('{{AGENT_NAME}}', html.escape(AGENT['name']))
            .replace('{{AGENT_JSON}}', json.dumps(AGENT).replace('<', '\\u003c')))


def resolve_agent():
    name = os.environ.get('AGENT', 'second-listen')
    agent = read_agent(name)
    history.apply_history(agent)
    result = ensure_agent(agent, name=name)
    return {'id': result['id'], 'name': agent['name']}


def mint_token():
    """Mint one browser token without leaking the upstream response.

    The browser needs only the single-use token.  Returning a small allowlist
    also prevents an unexpected upstream field from being copied into the
    client response, and the error path deliberately omits raw API details.
    """
    max_session_duration = session_max_duration_seconds()
    for attempt in range(2):
        try:
            payload = aai(
                f'/token?product=voice_agent&expires_in_seconds={TOKEN_EXPIRES_IN_SECONDS}'
                f'&max_session_duration_seconds={max_session_duration}'
            )
            break
        except (ApiError, OSError) as err:
            retryable = isinstance(err, OSError) or (
                isinstance(err, ApiError) and (err.status == 408 or err.status == 429 or err.status >= 500)
            )
            if attempt == 0 and retryable:
                time.sleep(0.4)
                continue
            debug_log('temporary voice token request failed')
            if isinstance(err, ApiError) and err.status in (401, 403):
                raise TokenError('AssemblyAI rejected the API key. Check app/.env.', 'api_key_rejected') from err
            if isinstance(err, ApiError) and err.status == 429:
                raise TokenError('AssemblyAI token service is rate limited. Please wait and retry.', 'rate_limited') from err
            if isinstance(err, ApiError) and err.status >= 500:
                raise TokenError('AssemblyAI token service is unavailable. Please retry.', 'upstream_unavailable') from err
            raise TokenError('Could not reach AssemblyAI token service. Check the network and retry.', 'network_error') from err
    token = payload.get('token') if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token.strip():
        debug_log('temporary voice token response did not contain a token')
        raise TokenError('AssemblyAI returned no usable voice token. Please retry.', 'invalid_token_response')
    return {
        'token': token.strip(),
        'expires_in_seconds': TOKEN_EXPIRES_IN_SECONDS,
        'max_session_duration_seconds': max_session_duration,
    }


def read_ledger():
    if not LEDGER.exists():
        return {'sessions': {}}
    try:
        value = json.loads(LEDGER.read_text(encoding='utf-8'))
    except (OSError, ValueError) as err:
        raise ValueError('The ledger is damaged. Restore its backup before recording new evidence.') from err
    if not isinstance(value, dict) or not isinstance(value.get('sessions'), dict):
        raise ValueError('The ledger is damaged. Restore its backup before recording new evidence.')
    return value


def write_ledger(value):
    atomic_write_text(LEDGER, json.dumps(value, ensure_ascii=False, indent=2))


def read_gate_log():
    if not GATE_LOG.exists():
        return []
    try:
        value = json.loads(GATE_LOG.read_text(encoding='utf-8'))
    except (OSError, ValueError) as err:
        raise ValueError('The gate log is damaged. Restore its backup before recording new events.') from err
    if not isinstance(value, list):
        raise ValueError('The gate log is damaged. Restore its backup before recording new events.')
    return value


def valid_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise ValueError('A valid session_id is required')
    return value


def company_name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 120:
        raise ValueError('Enter a company name (1–120 characters)')
    return value.strip()


def validate_event(body):
    valid_id(body.get('session_id'))
    args = body.get('arguments')
    if not isinstance(args, dict):
        raise ValueError('Tool arguments must be an object')
    tool = body.get('name')
    fields = ('dimension', 'quote', 'signal') if tool == 'log_evidence' else ('task', 'owner', 'deadline')
    if tool not in ('log_evidence', 'add_action_item'):
        raise ValueError('Unknown tool')
    if any(not isinstance(args.get(k), str) or not args[k].strip() or len(args[k]) > 4000 for k in fields):
        raise ValueError('Tool fields must be nonempty strings')
    event = {k: args[k].strip() for k in fields}
    if tool == 'log_evidence':
        if args['dimension'] not in DIMENSIONS or type(args.get('escalation')) is not bool:
            raise ValueError('Invalid evidence dimension or escalation flag')
        event['escalation'] = args['escalation']
    seconds = body.get('elapsed_seconds')
    if seconds is not None and (type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0):
        raise ValueError('Invalid elapsed time')
    event.update(tool=tool, at_seconds=seconds)
    if body.get('call_id'):
        event['call_id'] = valid_id(body['call_id'])
    return event


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def _send(self, status, body, content_type='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        if status == 401:
            self.send_header('WWW-Authenticate', 'Basic realm="Second Listen", charset="UTF-8"')
        # Closing rejected requests also discards any unread request body.
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        self.wfile.write(body)

    def _json(self, status, body):
        self._send(status, json.dumps(body, ensure_ascii=False).encode('utf-8'))

    def _authorized(self):
        origin = self.headers.get('Origin')
        if (self.headers.get('Sec-Fetch-Site') == 'cross-site'
                or (origin and urlsplit(origin).netloc != self.headers.get('Host'))):
            self._json(403, {'error': 'Cross-origin requests are not allowed'})
            return False
        if os.environ.get('REQUIRE_HTTPS') == '1' and self.headers.get('Host', '').split(':')[0] not in ('127.0.0.1', 'localhost', '::1'):
            if self.headers.get('X-Forwarded-Proto', '').lower() != 'https':
                self._json(400, {'error': 'HTTPS is required for remote workspaces'})
                return False
        password = os.environ.get('APP_PASSWORD', '')
        if password:
            try:
                scheme, encoded = self.headers.get('Authorization', '').split(' ', 1)
                credential = base64.b64decode(encoded, validate=True).decode('utf-8')
                supplied = credential.split(':', 1)[1]
                if scheme.lower() == 'basic' and hmac.compare_digest(supplied.encode(), password.encode()):
                    return True
            except (ValueError, IndexError, UnicodeError):
                pass
            self._json(401, {'error': 'Workspace password required'})
            return False
        return True

    def _client_key(self):
        """Return a best-effort client key without trusting it as the only cap."""
        forwarded = self.headers.get('X-Forwarded-For', '')
        if forwarded:
            candidate = forwarded.split(',', 1)[0].strip()
            if candidate:
                return candidate[:128]
        return self.client_address[0]

    def _reserve_public_operation(self, operation):
        reservation = reserve_public_operation(operation, self._client_key())
        if reservation is not None:
            return reservation
        window_minutes = PUBLIC_OPERATION_LIMITS[operation]['window_seconds'] // 60
        self._json(429, {
            'error': f'Public demo capacity is temporarily full. Please retry in {window_minutes} minutes.',
            'code': 'demo_capacity_limited',
        })
        return None

    def _body(self, limit=128 * 1024, raw=False):
        if self.headers.get('Transfer-Encoding'):
            raise ValueError('Chunked requests are not supported')
        length = int(self.headers.get('Content-Length', 0))
        if not 0 < length <= limit:
            raise ValueError('Empty or oversized request')
        value = self.rfile.read(length)
        if len(value) != length:
            raise ValueError('Incomplete request body')
        if raw:
            return value
        value = json.loads(value)
        if not isinstance(value, dict):
            raise ValueError('JSON body must be an object')
        return value

    def _body_to_file(self, limit=50 * 1024 * 1024):
        if self.headers.get('Transfer-Encoding'):
            raise ValueError('Chunked requests are not supported')
        length = int(self.headers.get('Content-Length', 0))
        if not 0 < length <= limit:
            raise ValueError('Empty or oversized request')
        digest = hashlib.sha256()
        handle = tempfile.NamedTemporaryFile(prefix='.second-listen-upload-', delete=False)
        path = Path(handle.name)
        try:
            remaining = length
            while remaining:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError('Incomplete request body')
                handle.write(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
            handle.close()
            return path, digest.hexdigest()
        except Exception:
            handle.close()
            path.unlink(missing_ok=True)
            raise

    def do_GET(self):
        path = urlsplit(self.path).path
        query = parse_qs(urlsplit(self.path).query)
        if path == '/health':
            self._json(200, {'ok': True, 'demo_only': demo_only()})
            return
        if not self._authorized():
            return
        try:
            if path == '/api/ledger':
                self._json(200, {'sessions': {}} if demo_only() else read_ledger())
            elif path == '/api/history':
                company = (query.get('company') or [''])[0]
                self._json(200, {} if demo_only() or not company else history.load_history(company) or {})
            elif path == '/api/context':
                if demo_only():
                    self._json(503, {'error': 'Preview only. Configure AssemblyAI to start a live debrief.'})
                    return
                if not AGENT.get('config'):
                    self._json(409, {'error': 'Company memory requires MODE=inline.'})
                    return
                company = company_name((query.get('company') or [''])[0])
                config = copy.deepcopy(AGENT['config'])
                has_history = history.apply_history(config, company)
                self._json(200, {'config': config, 'has_history': has_history})
            elif path == '/api/note':
                sid = valid_id((query.get('session') or [''])[0])
                session = ({} if demo_only() else read_ledger()['sessions']).get(sid)
                if session is None:
                    self._json(404, {'error': 'Session not found'})
                    return
                company = session.get('company') or (query.get('company') or [''])[0]
                self._send(200, build_note(sid, session, company).encode('utf-8'), 'text/markdown; charset=utf-8')
            elif path == '/token':
                if demo_only():
                    self._json(503, {'error': 'Live voice is disabled in preview mode'})
                else:
                    reservation = self._reserve_public_operation('token')
                    if reservation is None:
                        return
                    try:
                        self._json(200, mint_token())
                    except Exception:
                        release_public_operation('token', reservation)
                        raise
            elif path == '/agent':
                self._json(200, public_agent(AGENT['config']) if AGENT.get('config') else public_agent(aai(f"/agents/{AGENT['id']}")))
            elif path in ('/app.js', '/workspace.js', '/styles.css'):
                kind = 'text/css' if path.endswith('.css') else 'text/javascript'
                self._send(200, (HERE / path[1:]).read_bytes(), kind + '; charset=utf-8')
            elif path == '/':
                # Keep the response in sync with index.html during local
                # iteration. JS/CSS already load from disk; serving a cached
                # HTML shell here can otherwise leave the upload wiring and
                # its recording-view elements out of sync.
                self._send(200, render_page().encode('utf-8'), 'text/html; charset=utf-8')
            else:
                self._json(404, {'error': 'Not found'})
        except TokenError as err:
            self._json(502, {'error': str(err), 'code': err.code})
        except ApiError:
            # Do not echo upstream bodies: they are not useful to the browser
            # and must never become a path for credential leakage.
            debug_log('AssemblyAI request failed')
            self._json(502, {'error': 'AssemblyAI is unavailable. Please retry.'})
        except (ValueError, OSError) as err:
            debug_log(err)
            self._json(400, {'error': str(err) if isinstance(err, ValueError) else 'Could not read workspace data'})

    def do_POST(self):
        if not self._authorized():
            return
        if demo_only():
            self._json(403, {'error': 'Preview mode does not write workspace data or call paid APIs'})
            return
        path = urlsplit(self.path).path
        try:
            if path == '/api/upload':
                reservation = self._reserve_public_operation('upload')
                if reservation is None:
                    return
                if not UPLOAD_SLOTS.acquire(blocking=False):
                    release_public_operation('upload', reservation)
                    self._json(429, {'error': 'Two recordings are already processing. Try again shortly.'})
                    return
                try:
                    filename = unquote(self.headers.get('X-Filename') or 'recording.ogg')
                    if Path(filename).suffix.lower() not in transcribe._MIME:
                        raise ValueError('Unsupported audio format')
                    audio_path, audio_hash = self._body_to_file()
                    company = company_name(unquote(self.headers.get('X-Company') or ''))
                    prior_history = history.load_history(company) or {}
                    try:
                        cache_file = TRANSCRIPT_CACHE / (audio_hash + '.json')
                        result = read_json(cache_file)
                        cached = isinstance(result, dict) and isinstance(result.get('text'), str)
                        if not cached:
                            result = transcribe.transcribe_file(audio_path, filename)
                            atomic_write_text(cache_file, json.dumps(result, ensure_ascii=False))
                        result = copy.deepcopy(result)
                        result['cached'] = cached
                        result['company'] = company
                        result['analysis'] = analyze.analyze_transcript(
                            result.get('text', ''), result.get('language'), prior_history)
                        self._json(200, result)
                    finally:
                        audio_path.unlink(missing_ok=True)
                finally:
                    UPLOAD_SLOTS.release()
                return
            body = self._body()
            if path == '/api/archive':
                sid = valid_id(body.get('session_id'))
                archive_async(sid, TRIALS_DIR)
                self._json(202, {'ok': True, 'status': 'queued'})
            elif path == '/api/gate':
                with LEDGER_LOCK:
                    log = read_gate_log()
                    log.append({'at': datetime.now(timezone.utc).isoformat(),
                                'session_id': valid_id(body.get('session_id')),
                                'at_seconds': body.get('at_seconds'), 'kind': body.get('kind', 'fire')})
                    atomic_write_text(GATE_LOG, json.dumps(log[-2000:], ensure_ascii=False))
                self._json(200, {'ok': True})
            elif path == '/api/history':
                sid = valid_id(body.get('session_id'))
                company = company_name(body.get('company'))
                with LEDGER_LOCK:
                    session = read_ledger()['sessions'].get(sid)
                    if not session:
                        raise ValueError('Session not found')
                    if not session.get('company') or slugify(session['company']) != slugify(company):
                        raise ValueError('Company does not match this debrief')
                    value = build_history(session, company)
                    if not value['commitments']:
                        raise ValueError('This debrief has no agreed actions to carry forward')
                    dest = history.HISTORY_DIR / (slugify(company) + '.json')
                    previous = read_json(dest) or {}
                    if previous.get('last_debrief_at', '') > value['last_debrief_at']:
                        raise ValueError('A newer debrief is already saved for this company')
                    atomic_write_text(dest, json.dumps(value, ensure_ascii=False, indent=2))
                self._json(200, {'ok': True, 'commitments': len(value['commitments'])})
            elif path == '/api/history/status':
                company = company_name(body.get('company'))
                task = body.get('task')
                status = body.get('status')
                if not isinstance(task, str) or not task.strip():
                    raise ValueError('A follow-up task is required')
                if status not in ('completed', 'open'):
                    raise ValueError('Status must be completed or open')
                with LEDGER_LOCK:
                    path = history.HISTORY_DIR / (slugify(company) + '.json')
                    value = read_json(path)
                    if not isinstance(value, dict) or not isinstance(value.get('commitments'), list):
                        raise ValueError('History file is missing or damaged')
                    match = next((item for item in value['commitments']
                                  if normalize_action_task(item.get('task', ''))
                                  == normalize_action_task(task)), None)
                    if match is None:
                        raise ValueError('Follow-up not found for this company')
                    match['status'] = status
                    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2))
                self._json(200, {'ok': True, 'status': status})
            elif path == '/api/ledger':
                event = validate_event(body)
                company = company_name(body.get('company'))
                with LEDGER_LOCK:
                    ledger = read_ledger()
                    entry = ledger['sessions'].setdefault(body['session_id'], {
                        'company': company, 'started_at': datetime.now(timezone.utc).isoformat(), 'events': []})
                    if entry.get('company') and slugify(entry['company']) != slugify(company):
                        raise ValueError('Company cannot change during a session')
                    entry.setdefault('company', company)
                    duplicate = False
                    changed = False
                    for existing in entry['events']:
                        same_call = event.get('call_id') and existing.get('call_id') == event['call_id']
                        same_action = (
                            event['tool'] == 'add_action_item'
                            and existing.get('tool') == 'add_action_item'
                            and normalize_action_task(existing.get('task', ''))
                            == normalize_action_task(event.get('task', ''))
                        )
                        if same_call or same_action:
                            duplicate = True
                            if same_action:
                                changed = merge_action_fields(existing, event)
                            break
                    if not duplicate:
                        entry['events'].append(event)
                    if not duplicate or changed:
                        write_ledger(ledger)
                self._json(200, {'ok': True, 'duplicate': duplicate, 'updated': changed, 'event_count': len(entry['events'])})
            else:
                self._json(404, {'error': 'Not found'})
        except transcribe.TranscribeError as err:
            debug_log(err)
            self._json(502, {'error': 'Transcription failed. Check your audio and AssemblyAI connection, then retry.'})
        except (ValueError, OSError) as err:
            debug_log(err)
            self._json(400, {'error': str(err) if isinstance(err, ValueError) else 'Workspace operation failed. Please retry.'})

    def do_DELETE(self):
        # Global destructive reset was removed. Records are retained locally.
        self._json(405, {'error': 'Bulk deletion is disabled'})

    def log_message(self, *args):
        pass


def main():
    global AGENT, PAGE, LEDGER, GATE_LOG, TRIALS_DIR, TRANSCRIPT_CACHE
    load_env()
    host = os.environ.get('HOST', '127.0.0.1')
    name = os.environ.get('AGENT', 'second-listen')
    mode = os.environ.get('MODE', 'inline')
    if not demo_only():
        required('ASSEMBLYAI_API_KEY', 'set it in app/.env')
    data_dir = Path(os.environ.get('DATA_DIR') or DEFAULT_DATA_DIR)
    LEDGER = data_dir / 'ledger.json'
    GATE_LOG = data_dir / 'gate_log.json'
    history.HISTORY_DIR = data_dir / 'history'
    TRIALS_DIR = Path(os.environ.get('TRIALS_DIR') or data_dir / 'trials')
    TRANSCRIPT_CACHE = Path(os.environ.get('TRANSCRIPT_CACHE_DIR') or data_dir / 'transcript_cache')
    if demo_only() or mode == 'inline':
        config = read_agent(name)
        if public_agent(config) != config:
            sys.exit('Inline mode cannot expose HTTP credentials or LLM keys. Use MODE=stored for this agent.')
        AGENT = {'id': '', 'name': config['name'], 'config': config, 'preview': demo_only()}
    elif mode == 'stored':
        AGENT = resolve_agent()
    else:
        sys.exit('MODE must be inline or stored')
    PAGE = ((HERE / 'index.html').read_text(encoding='utf-8')
            .replace('{{AGENT_NAME}}', html.escape(AGENT['name']))
            .replace('{{AGENT_JSON}}', json.dumps(AGENT).replace('<', '\\u003c')))
    fixed = os.environ.get('PORT')
    port = int(fixed) if fixed else 3000
    try:
        server = ThreadingHTTPServer((host, port), Handler)
    except OSError as err:
        raise SystemExit(f'Could not bind http://{host}:{port}. Is another Second Listen server already running?') from err
    print(f"Second Listen: http://localhost:{port} ({'sample preview' if demo_only() else mode})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
