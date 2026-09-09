import json
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import analyze
import archive
import history
import history_from_ledger as ledger_tools
import transcribe


class RegressionTests(unittest.TestCase):
    def test_history_prompt_contains_every_open_commitment(self):
        agent = {'greeting': 'hello', 'system_prompt': 'base'}
        prior = {'company': 'Fixture', 'commitments': [
            {'task': 'First task', 'owner': 'Alice', 'deadline': 'Friday'},
            {'task': 'Second task', 'owner': 'Bob', 'deadline': 'Monday'},
        ]}
        with patch.object(history, 'load_history', return_value=prior):
            self.assertTrue(history.apply_history(agent, 'Fixture'))
        self.assertIn('Second task', agent['system_prompt'])
        self.assertIn('Bob', agent['system_prompt'])

    def test_completed_commitment_is_not_injected_again(self):
        agent = {'greeting': 'hello', 'system_prompt': 'base'}
        prior = {'company': 'Fixture', 'commitments': [
            {'task': 'Done task', 'status': 'completed'},
        ]}
        with patch.object(history, 'load_history', return_value=prior):
            self.assertFalse(history.apply_history(agent, 'Fixture'))
        self.assertEqual(agent['greeting'], 'hello')

    def test_cli_session_selection_is_company_scoped(self):
        ledger = {'sessions': {
            'alpha': {'company': 'Alpha', 'started_at': '2026-09-01', 'events': []},
            'beta': {'company': 'Beta', 'started_at': '2026-09-02', 'events': []},
        }}
        session_id, session = ledger_tools.pick_session(ledger, '', 'Alpha')
        self.assertEqual((session_id, session['company']), ('alpha', 'Alpha'))

    def test_corrupt_ledger_is_not_treated_as_empty(self):
        spec = importlib.util.spec_from_file_location(
            'review_server', ROOT / 'deployment' / 'browser' / 'server.py')
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'ledger.json'
            path.write_text('{"sessions":', encoding='utf-8')
            with patch.object(server, 'LEDGER', path):
                with self.assertRaises(ValueError):
                    server.read_ledger()

    def test_completed_followup_requires_transcript_evidence(self):
        value = {'signals': [], 'questions': [], 'followup_checks': [{
            'task': 'Send approval', 'status': 'completed', 'quote': '', 'note': ''
        }]}
        history_data = {'commitments': [{'task': 'Send approval'}]}
        with self.assertRaises(ValueError):
            analyze._validated_analysis(value, 'No approval mentioned.', history_data)

    def test_transcribe_auth_strips_bearer_prefix(self):
        with patch.dict(os.environ, {'ASSEMBLYAI_API_KEY': 'Bearer FIXTURE_KEY'}):
            self.assertEqual(transcribe._auth()['Authorization'], 'FIXTURE_KEY')

    def test_gate_log_corrupt_is_not_treated_as_empty(self):
        spec = importlib.util.spec_from_file_location(
            'review_server_gate', ROOT / 'deployment' / 'browser' / 'server.py')
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'gate.json'
            path.write_text('{"broken":', encoding='utf-8')
            with patch.object(server, 'GATE_LOG', path):
                with self.assertRaises(ValueError):
                    server.read_gate_log()

    def test_cli_ledger_corrupt_reports_damaged(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'ledger.json'
            path.write_text('{"sessions":', encoding='utf-8')
            with patch.object(ledger_tools, 'LEDGER', path):
                with self.assertRaises(SystemExit):
                    ledger_tools.load_ledger()

    def test_archive_download_rejects_non_https(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                archive._download('file:///etc/hostname', Path(temp) / 'out.ogg')

    def test_voice_token_has_a_bounded_session_limit(self):
        spec = importlib.util.spec_from_file_location(
            'review_server_token', ROOT / 'deployment' / 'browser' / 'server.py')
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        requested = []
        with patch.dict(os.environ, {'VOICE_SESSION_MAX_DURATION_SECONDS': '120'}, clear=False):
            with patch.object(server, 'aai', side_effect=lambda path: requested.append(path) or {'token': 'fixture'}):
                result = server.mint_token()
        self.assertIn('expires_in_seconds=60', requested[0])
        self.assertIn('max_session_duration_seconds=120', requested[0])
        self.assertEqual(result['max_session_duration_seconds'], 120)

    def test_voice_token_rejects_an_overlong_session_limit(self):
        spec = importlib.util.spec_from_file_location(
            'review_server_token_limit', ROOT / 'deployment' / 'browser' / 'server.py')
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        with patch.dict(os.environ, {'VOICE_SESSION_MAX_DURATION_SECONDS': '301'}, clear=False):
            self.assertEqual(server.session_max_duration_seconds(), 300)

    def test_public_token_capacity_is_limited_per_client_and_globally(self):
        spec = importlib.util.spec_from_file_location(
            'review_server_public_capacity', ROOT / 'deployment' / 'browser' / 'server.py')
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        empty_grants = {operation: [] for operation in server.PUBLIC_OPERATION_LIMITS}
        with patch.object(server, 'PUBLIC_OPERATION_GRANTS', empty_grants):
            self.assertIsNotNone(server.reserve_public_operation('token', 'visitor-a', now=0))
            self.assertIsNotNone(server.reserve_public_operation('token', 'visitor-a', now=1))
            self.assertIsNone(server.reserve_public_operation('token', 'visitor-a', now=2))

        empty_grants = {operation: [] for operation in server.PUBLIC_OPERATION_LIMITS}
        with patch.object(server, 'PUBLIC_OPERATION_GRANTS', empty_grants):
            for index in range(server.PUBLIC_OPERATION_LIMITS['token']['global']):
                self.assertIsNotNone(server.reserve_public_operation('token', f'visitor-{index}', now=index))
            self.assertIsNone(server.reserve_public_operation('token', 'visitor-overflow', now=10))


if __name__ == '__main__':
    unittest.main()
