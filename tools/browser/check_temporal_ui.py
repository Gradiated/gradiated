#!/usr/bin/env python3
"""Render the production Cloud frontend against a synthetic namespace reader."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlparse
import uuid

from playwright.sync_api import sync_playwright


def main(image):
    with tempfile.TemporaryDirectory(prefix='temporal-ui-browser-') as directory:
        container = 'temporal-ui-assets-' + uuid.uuid4().hex[:10]
        subprocess.run(['docker', 'create', '--name', container, image], check=True, capture_output=True)
        try:
            subprocess.run(['docker', 'cp', container + ':/opt/temporal-ui-cloud/.', directory], check=True, capture_output=True)
        finally:
            subprocess.run(['docker', 'rm', container], check=True, capture_output=True)
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=directory))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = 'http://127.0.0.1:' + str(server.server_port)
        calls = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                def route(interception):
                    request = interception.request
                    path = urlparse(request.url).path
                    assert urlparse(request.url).netloc == urlparse(origin).netloc, 'Unexpected external browser request'
                    if path.startswith('/api/'):
                        assert request.method == 'GET', 'Read-only UI issued a write'
                        calls.append(path)
                        status = 200
                        if path == '/api/v1/settings':
                            body = {'Auth': {'Enabled': False, 'Options': []}, 'DefaultNamespace': 'fixture',
                                    'DisableWriteActions': True, 'DisableNewsFetch': True, 'Codec': {'Endpoint': ''}, 'Version': '2.54.1'}
                        elif path == '/api/v1/namespaces/fixture/search-attributes':
                            status, body = 403, {'code': 7, 'message': 'Only WorkflowService calls are permitted'}
                        elif path.endswith('/workflow-count'):
                            body = {'count': '0'}
                        elif path.endswith('/workflows'):
                            body = {'executions': []}
                        elif path == '/api/v1/namespaces/fixture':
                            body = {'namespaceInfo': {'name': 'fixture', 'state': 'NAMESPACE_STATE_REGISTERED'}, 'config': {}}
                        else:
                            status, body = 400, {'code': 3, 'message': 'No namespace in global request'}
                        interception.fulfill(status=status, content_type='application/json', body=json.dumps(body))
                    elif path == '/' or path.startswith('/namespaces/') or path.startswith('/login'):
                        interception.fulfill(content_type='text/html', body=Path(directory, 'index.html').read_text())
                    else:
                        interception.continue_()
                context.route('**/*', route)
                page = context.new_page()
                page.goto(origin + '/', wait_until='networkidle', timeout=45000)
                page.wait_for_function("document.title === 'Workflows | fixture'", timeout=20000)
                assert '/namespaces/fixture/workflows' in page.url
                assert '/api/v1/namespaces/fixture/workflows' in calls
                assert not set(calls) & {'/api/v1/cluster-info', '/api/v1/system-info', '/api/v1/namespaces'}
                assert 'Internal Error' not in page.locator('body').inner_text()
                context.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
    print('Cloud workflow page renders with namespace Read permissions, including OperatorService denial; no cluster-wide startup calls or writes.')


if __name__ == '__main__':
    main(sys.argv[1])
