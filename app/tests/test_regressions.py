import json
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import analyze
import history
import history_from_ledger as ledger_tools


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


if __name__ == '__main__':
    unittest.main()
