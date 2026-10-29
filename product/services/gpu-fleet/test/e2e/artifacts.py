# Serves host bundles over HTTPS, standing in for the S3 artifact bucket.
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import ssl

context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain('/etc/artifacts/tls.pem', '/etc/artifacts/tls.key')
server = ThreadingHTTPServer(('0.0.0.0', 443), partial(SimpleHTTPRequestHandler, directory='/srv'))
server.socket = context.wrap_socket(server.socket, server_side=True)
server.serve_forever()
