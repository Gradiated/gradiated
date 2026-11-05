import http.server
import importlib.util
import os
import math
import re
from pathlib import Path
import sys
import urllib.request

from config import ACTIVE_REQUESTS, QUEUED_REQUESTS, QUEUE_TIMEOUT_SECONDS, detect_profile, settings

root = Path(__file__).resolve().parents[1]
base_path = root / 'warmup-base.py'
if not base_path.is_file():
    base_path = root / 'glm/warmup-supervisor.py'
spec = importlib.util.spec_from_file_location('glm_warmup_base', base_path)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base_handler = base.handler


class Supervisor(base.Supervisor):
    def health(self):
        if self.child is None or self.child.poll() is not None:
            return False
        try:
            # SMG /health is process liveness; /readiness requires a healthy worker.
            with urllib.request.urlopen(self.runtime_url + '/readiness', timeout=2) as response:
                return response.status == 200
        except Exception:
            return False


def namespace_metrics(text, prefix):
    lines = []
    for line in text.splitlines():
        fields = line.split()
        if line.startswith(('# HELP ', '# TYPE ')):
            name = fields[2] if len(fields) > 2 else ''
        elif line.startswith('#') or not fields:
            continue
        else:
            name = fields[0].split('{', 1)[0]
        if name.startswith(prefix):
            lines.append(line)
    return '\n'.join(lines).encode()


def full_kv_pressure(text):
    values = []
    sample = re.compile(r'sglang:full_token_usage(?:\{(?:[^"{}]|"(?:\\.|[^"\\])*")*\})?\s+(\S+)(?:\s+\d+)?')
    for line in text.splitlines():
        if not line.startswith('sglang:full_token_usage'):
            continue
        match = sample.fullmatch(line)
        if match is None:
            raise ValueError('Malformed native full-token pressure sample')
        value = float(match[1])
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('Native full-token pressure is not a ratio')
        values.append(value)
    if not values:
        raise ValueError('Native full-token pressure is unavailable')
    return max(values)


def metrics(config):
    texts = []
    for port in [config['backend'], config['metrics']]:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/metrics', timeout=2) as response:
            if response.status != 200:
                raise RuntimeError('Native runtime metrics unavailable')
            body = response.read(4 * 1024 * 1024)
            if len(body) >= 4 * 1024 * 1024:
                raise ValueError('Native metrics response exceeds bound')
            texts.append(body.decode())
    pressure = full_kv_pressure(texts[0])
    chunks = [namespace_metrics(texts[0], 'sglang:'), namespace_metrics(texts[1], 'smg_')]
    for name, value, help_text in [
        ('gradiated_runtime_active_request_limit', config.get('active_requests', ACTIVE_REQUESTS), 'SMG requests holding an active permit.'),
        ('gradiated_runtime_waiting_request_limit', QUEUED_REQUESTS, 'SMG requests waiting for a permit.'),
        ('gradiated_runtime_queue_timeout_seconds', QUEUE_TIMEOUT_SECONDS, 'Native SMG maximum queue age.'),
        ('vllm:kv_cache_usage_perc', pressure, 'Compatibility alias: maximum native SGLang non-evictable full-attention KV usage ratio.'),
    ]:
        chunks.append(f'\n# HELP {name} {help_text}\n# TYPE {name} gauge\n{name} {value}\n'.encode())
    return b'\n'.join(chunks)


def handler(supervisor, config):
    parent = base_handler(supervisor)
    class Handler(parent):
        def do_GET(self):
            if self.path != '/metrics':
                return super().do_GET()
            try:
                body, code = metrics(config), 200
            except (OSError, RuntimeError, ValueError):
                body, code = b'native metrics unavailable\n', 503
            self.send_response(code)
            self.send_header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    return Handler


def main(environment=os.environ):
    config = settings(detect_profile(environment))
    original = base.handler
    base.handler = lambda supervisor: handler(supervisor, config)
    try:
        supervisor = Supervisor([sys.executable, str(root / 'glm-sglang/service.py')],
            runtime_url=f"http://127.0.0.1:{config['front']}",
            timeout=int(environment.get('RUNTIME_STARTUP_TIMEOUT_SECONDS', '3600')),
            max_queued_requests=config['active_requests'] + QUEUED_REQUESTS)
        return supervisor.run(port=config['warmup'])
    finally:
        base.handler = original


if __name__ == '__main__':
    raise SystemExit(main())
