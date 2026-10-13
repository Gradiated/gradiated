import importlib.util
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

source = Path(__file__).resolve().parents[2] / 'product/inference/gpu/host-agent.py'
spec = importlib.util.spec_from_file_location('host_agent', source)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)
root = Path(sys.argv[1])
(root / 'pods').mkdir(exist_ok=True)
host = agent.Agent({'instance_id': 'synthetic'}, root)
server = ThreadingHTTPServer(('127.0.0.1', 0), agent.handler_for(host, 'host-only-key'))
print(f'http://127.0.0.1:{server.server_port}/_kubelet', flush=True)
server.serve_forever()
