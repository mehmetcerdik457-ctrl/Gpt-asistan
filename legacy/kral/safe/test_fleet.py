"""Offline protocol and orchestration tests; no real model quality claim."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from unittest.mock import patch

import fleet


class FleetTests(unittest.TestCase):
    def setUp(self):
        self.config = fleet.load_config(Path(__file__).with_name('fleet.example.json'))

    def load(self, config):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps(config))
            return fleet.load_config(path)

    def test_invalid_config(self):
        for field, value in [('max_parallel', 0), ('max_specialists', 9),
                             ('timeout_seconds', True), ('coordinators', ['missing'])]:
            config = copy.deepcopy(self.config)
            config[field] = value
            with self.subTest(field=field), self.assertRaises(fleet.FleetError):
                self.load(config)
        config = copy.deepcopy(self.config)
        config['models'][1]['id'] = config['models'][0]['id']
        with self.assertRaises(fleet.FleetError):
            self.load(config)

    def test_transport_configuration(self):
        for url in ['http://example.com/v1', 'https://user:secret@example.com/v1',
                    'https://example.com/v1?token=secret', 'file:///etc/passwd']:
            with self.subTest(url=url), self.assertRaises(fleet.FleetError):
                fleet.validate_url(url)
        self.assertEqual(fleet.validate_url('http://[::1]:11434/v1'), 'http://[::1]:11434/v1')

    def test_success_and_task_routing(self):
        self.config['models'][1]['tasks'] = ['writing']
        with patch.object(fleet, 'complete', return_value='yanıt') as complete:
            report = fleet.run(self.config, 'Test', 'code')
        self.assertEqual(report['status'], 'success')
        self.assertEqual(complete.call_count, 2)
        self.assertEqual(len(report['evidence']), 2)
        self.assertEqual(len(report['evidence'][0]['output_sha256']), 64)

    def test_parallel_specialists_and_limit(self):
        barrier = threading.Barrier(2)
        def complete(model, config, system, prompt):
            if not system.startswith('Koordinatör'):
                barrier.wait(timeout=3)
            return 'ok'
        with patch.object(fleet, 'complete', side_effect=complete):
            self.assertEqual(fleet.run(self.config, 'Test')['status'], 'success')
        self.config['max_specialists'] = 1
        with patch.object(fleet, 'complete', return_value='ok') as complete:
            fleet.run(self.config, 'Test')
            self.assertEqual(complete.call_count, 2)

    def test_partial_and_coordinator_fallback(self):
        def complete(model, config, system, prompt):
            if model['id'] == 'local-coordinator':
                raise fleet.FleetError('network_or_timeout')
            return 'ok'
        with patch.object(fleet, 'complete', side_effect=complete):
            report = fleet.run(self.config, 'Test')
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['coordinator'], 'local-reviewer')
        self.assertEqual(len(report['evidence']), 4)

    def test_all_specialists_fail_no_synthesis(self):
        with patch.object(fleet, 'complete', side_effect=fleet.FleetError('http_503')) as complete:
            report = fleet.run(self.config, 'Test')
        self.assertEqual(report['status'], 'failed')
        self.assertIsNone(report['answer'])
        self.assertEqual(complete.call_count, 2)

    def test_coordinators_fail(self):
        def complete(model, config, system, prompt):
            if system.startswith('Koordinatör'):
                raise fleet.FleetError('http_503')
            return 'ok'
        with patch.object(fleet, 'complete', side_effect=complete):
            report = fleet.run(self.config, 'Test')
        self.assertEqual(report['status'], 'failed')
        self.assertIsNone(report['answer'])

    def test_invalid_input_no_network(self):
        with patch.object(fleet, 'request') as request:
            for prompt in ['', 'x' * 12001]:
                with self.assertRaises(fleet.FleetError):
                    fleet.run(self.config, prompt)
            with self.assertRaises(fleet.FleetError):
                fleet.run(self.config, 'hello', 'unknown')
            request.assert_not_called()

    def test_missing_key_before_network(self):
        model = dict(self.config['models'][0], api_key_env='FLEET_TEST_KEY')
        with patch.dict(os.environ, {}, clear=True), patch.object(fleet.urllib.request, 'build_opener') as opener:
            with self.assertRaisesRegex(fleet.FleetError, 'credential_missing'):
                fleet.request(model, self.config, '/models')
            opener.assert_not_called()

    def test_bad_outputs_are_not_success(self):
        for response in [[], {'choices': []}, {'choices': [{'message': {'content': ''}}]},
                         {'choices': [{'message': {'content': 'cut'}, 'finish_reason': 'length'}]}]:
            with patch.object(fleet, 'request', return_value=response):
                with self.assertRaises(fleet.FleetError):
                    fleet.complete(self.config['models'][0], self.config, 'system', 'test')

    def test_inventory_does_not_call_inference(self):
        with patch.object(fleet, 'request') as request:
            self.assertEqual(fleet.inventory(self.config)[0]['status'], 'not_checked')
            request.assert_not_called()
        with patch.object(fleet, 'request', return_value={'data': []}):
            self.assertEqual(fleet.inventory(self.config, True)[0]['status'], 'not_listed')


class LocalProtocolTests(unittest.TestCase):
    def test_cli_against_local_protocol_fixture(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                body = json.dumps({'data': [{'id': 'fixture-model'}]}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)
            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append((self.path, data))
                body = json.dumps({'choices': [{'message': {'content': 'fixture answer'}, 'finish_reason': 'stop'}]}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config = fleet.load_config(Path(__file__).with_name('fleet.example.json'))
            for model in config['models']:
                model.update(base_url=f'http://127.0.0.1:{server.server_port}/v1', model='fixture-model')
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'config.json'
                path.write_text(json.dumps(config))
                cmd = [sys.executable, str(Path(__file__).with_name('assistant.py')), '--fleet-config', str(path)]
                result = subprocess.run(cmd + ['--fleet', 'test'], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report['status'], 'success')
                self.assertEqual(len(report['evidence']), 3)
                result = subprocess.run(cmd + ['--probe-models'], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)[0]['status'], 'listed')
            self.assertEqual(len(requests), 3)
            self.assertTrue(all(path == '/v1/chat/completions' for path, _ in requests))
            self.assertTrue(all(data['stream'] is False and 'tools' not in data for _, data in requests))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_redirect_refused(self):
        with self.assertRaisesRegex(fleet.FleetError, 'redirect_refused'):
            fleet.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere.example')


if __name__ == '__main__':
    unittest.main()
