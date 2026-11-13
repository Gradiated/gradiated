import json
from contextvars import ContextVar

from estimator import EnergyEstimator


MAX_BUFFER = 16 * 1024 * 1024
GENERATION_PATHS = ('/v1/chat/completions', '/v1/completions')
current_request = ContextVar('generation_energy', default=None)


class RequestEnergy:
    def __init__(self, estimator):
        self.estimator = estimator
        self.ticket = None
        self.finished = False
        self.joules = None

    def start(self):
        if self.ticket is None and not self.finished:
            self.ticket = self.estimator.begin()

    def finish(self):
        if not self.finished:
            self.finished = True
            if self.ticket is not None:
                self.joules = self.estimator.finish(self.ticket)
        return self.joules


def mark_generation_started():
    request = current_request.get()
    if request is not None:
        request.start()


def add_estimate(body, request, terminal_only=False):
    try:
        value = json.loads(body)
        if not isinstance(value, dict) or not isinstance(value.get('usage'), dict):
            return body
        if terminal_only and value.get('choices') != []:
            return body
        joules = request.finish()
        if joules is None:
            return body
        value['usage']['estimated_joules'] = joules
        return json.dumps(value, separators=(',', ':'), ensure_ascii=False).encode()
    except Exception:
        return body


class EnergyMiddleware:
    def __init__(self, app, estimator=None):
        self.app = app
        self.estimator = estimator or EnergyEstimator()

    async def __call__(self, scope, receive, send):
        if (scope['type'] != 'http' or scope.get('path') not in GENERATION_PATHS
                or scope.get('method') != 'POST'):
            return await self.app(scope, receive, send)

        self.estimator.start()
        request = RequestEnergy(self.estimator)
        context_token = current_request.set(request)
        streaming = False
        passthrough = False
        buffer = b''

        async def emit(message):
            nonlocal streaming, passthrough, buffer
            if message['type'] == 'http.response.start':
                headers = message.get('headers', [])
                streaming = any(k.lower() == b'content-type' and b'text/event-stream' in v for k, v in headers)
                passthrough = message['status'] != 200 or any(k.lower() == b'content-encoding' for k, _ in headers)
                if not passthrough:
                    message = {**message, 'headers': [(k, v) for k, v in headers if k.lower() != b'content-length']}
                await send(message)
                return
            if message['type'] != 'http.response.body' or passthrough:
                await send(message)
                return

            buffer += message.get('body', b'')
            more = message.get('more_body', False)
            if len(buffer) > MAX_BUFFER:
                passthrough = True
                await send({**message, 'body': buffer})
                buffer = b''
                return

            if streaming:
                while b'\n\n' in buffer:
                    frame, buffer = buffer.split(b'\n\n', 1)
                    if frame.startswith(b'data: ') and frame != b'data: [DONE]':
                        frame = b'data: ' + add_estimate(frame[6:], request, terminal_only=True)
                    await send({'type': 'http.response.body', 'body': frame + b'\n\n', 'more_body': True})
                if not more:
                    await send({**message, 'body': buffer})
                    buffer = b''
            elif not more:
                await send({**message, 'body': add_estimate(buffer, request)})
                buffer = b''

        try:
            await self.app(scope, receive, emit)
        finally:
            request.finish()
            current_request.reset(context_token)
