#!/usr/bin/env python3
"""Second Listen browser deployment. Python standard library only.

Default: local, inline voice config. DEMO_ONLY=1 runs without API credentials.
Remote live deployments require APP_PASSWORD and HTTPS at the reverse proxy.
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
from history_from_ledger import build_history, slugify
from note import build_note

LEDGER = HERE.parents[1] / 'data' / 'ledger.json'
GATE_LOG = HERE.parents[1] / 'data' / 'gate_log.json'
TRIALS_DIR = Path(os.environ.get('TRIALS_DIR') or DEFAULT_TRIALS_DIR)
TRANSCRIPT_CACHE = Path(os.environ.get('TRANSCRIPT_CACHE_DIR') or HERE.parents[1] / 'data' / 'transcript_cache')
LEDGER_LOCK = threading.Lock()
UPLOAD_SLOTS = threading.BoundedSemaphore(2)
AGENT = None
PAGE = ''
DIMENSIONS = {'operations', 'exit_potential', 'self_funding', 'team_integrity', 'financial_health'}
TOKEN_EXPIRES_IN_SECONDS = 60


class TokenError(Exception):
    """A safe, user-facing failure from the temporary-token proxy."""


def debug_log(*args):
    if os.environ.get('DEBUG'):
        print(*args, file=sys.stderr)


def demo_only():
    return os.environ.get('DEMO_ONLY') == '1'


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
    for attempt in range(2):
        try:
            payload = aai(f'/token?product=voice_agent&expires_in_seconds={TOKEN_EXPIRES_IN_SECONDS}')
            break
        except (ApiError, OSError) as err:
            retryable = isinstance(err, OSError) or (
                isinstance(err, ApiError) and (err.status == 408 or err.status == 429 or err.status >= 500)
            )
            if attempt == 0 and retryable:
                time.sleep(0.4)
                continue
            debug_log('temporary voice token request failed')
            raise TokenError('Voice token service is unavailable. Please retry.') from err
    token = payload.get('token') if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token.strip():
        debug_log('temporary voice token response did not contain a token')
        raise TokenError('Voice token service returned no usable token. Please retry.')
    return {'token': token.strip(), 'expires_in_seconds': TOKEN_EXPIRES_IN_SECONDS}


def read_ledger():
    value = read_json(LEDGER, {'sessions': {}})
    if not isinstance(value, dict) or not isinstance(value.get('sessions'), dict):
        raise ValueError('The ledger is damaged. Restore its backup before recording new evidence.')
    return value


def write_ledger(value):
    atomic_write_text(LEDGER, json.dumps(value, ensure_ascii=False, indent=2))


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
                    self._json(200, mint_token())
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
            self._json(502, {'error': str(err)})
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
                if not UPLOAD_SLOTS.acquire(blocking=False):
                    self._json(429, {'error': 'Two recordings are already processing. Try again shortly.'})
                    return
                try:
                    audio = self._body(50 * 1024 * 1024, raw=True)
                    filename = unquote(self.headers.get('X-Filename') or 'recording.ogg')
                    if Path(filename).suffix.lower() not in transcribe._MIME:
                        raise ValueError('Unsupported audio format')
                    cache_file = TRANSCRIPT_CACHE / (hashlib.sha256(audio).hexdigest() + '.json')
                    result = read_json(cache_file)
                    cached = isinstance(result, dict) and isinstance(result.get('text'), str)
                    if not cached:
                        result = transcribe.transcribe(audio, filename)
                        atomic_write_text(cache_file, json.dumps(result, ensure_ascii=False))
                    result = copy.deepcopy(result)
                    result['cached'] = cached
                    result['analysis'] = analyze.analyze_transcript(result.get('text', ''), result.get('language'))
                    self._json(200, result)
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
                    log = read_json(GATE_LOG, []) or []
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
                    duplicate = any(
                        (event.get('call_id') and e.get('call_id') == event['call_id'])
                        or (event['tool'] == 'add_action_item' and all(e.get(k) == event.get(k) for k in ('tool', 'task', 'owner', 'deadline')))
                        for e in entry['events'])
                    if not duplicate:
                        entry['events'].append(event)
                        write_ledger(ledger)
                self._json(200, {'ok': True, 'duplicate': duplicate, 'event_count': len(entry['events'])})
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
    global AGENT, PAGE, TRIALS_DIR, TRANSCRIPT_CACHE
    load_env()
    host = os.environ.get('HOST', '127.0.0.1')
    if host not in ('127.0.0.1', 'localhost', '::1') and not demo_only() and not os.environ.get('APP_PASSWORD'):
        sys.exit('Remote live workspaces require APP_PASSWORD. Use DEMO_ONLY=1 for a public sample preview.')
    name = os.environ.get('AGENT', 'second-listen')
    mode = os.environ.get('MODE', 'inline')
    if not demo_only():
        required('ASSEMBLYAI_API_KEY', 'set it in app/.env')
    if demo_only() or mode == 'inline':
        config = read_agent(name)
        if public_agent(config) != config:
            sys.exit('Inline mode cannot expose HTTP credentials or LLM keys. Use MODE=stored for this agent.')
        AGENT = {'id': '', 'name': config['name'], 'config': config, 'preview': demo_only()}
    elif mode == 'stored':
        AGENT = resolve_agent()
    else:
        sys.exit('MODE must be inline or stored')
    TRIALS_DIR = Path(os.environ.get('TRIALS_DIR') or DEFAULT_TRIALS_DIR)
    TRANSCRIPT_CACHE = Path(os.environ.get('TRANSCRIPT_CACHE_DIR') or HERE.parents[1] / 'data' / 'transcript_cache')
    PAGE = ((HERE / 'index.html').read_text(encoding='utf-8')
            .replace('{{AGENT_NAME}}', html.escape(AGENT['name']))
            .replace('{{AGENT_JSON}}', json.dumps(AGENT).replace('<', '\\u003c')))
    fixed = os.environ.get('PORT')
    port = int(fixed) if fixed else 3000
    while True:
        try:
            server = ThreadingHTTPServer((host, port), Handler)
            break
        except OSError:
            if fixed or port >= 3010:
                raise
            port += 1
    print(f"Second Listen: http://localhost:{port} ({'sample preview' if demo_only() else mode})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
