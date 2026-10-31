METRICS = {
    'prefill_backlog_prompt_tokens': 'Full prompt tokens charged by frontend admission until prefill completes.',
    'inflight_requests': 'Requests waiting or running in the frontend.',
    'queue_token_limit': 'Configured prefill backlog threshold; minus one means unlimited.',
    'queue_request_limit': 'Configured unfinished request limit; minus one means unlimited.',
    'queue_telemetry_available': 'Whether frontend admission counters are available.',
}


def snapshot(scope):
    try:
        engine = scope['app'].state.engine_client
        config = engine.scheduler_config
        return {
            'prefill_backlog_prompt_tokens': engine.get_num_queued_tokens(),
            'inflight_requests': engine.get_num_unfinished_requests(),
            'queue_token_limit': config.max_num_queued_tokens if config.max_num_queued_tokens is not None else -1,
            'queue_request_limit': config.max_num_queued_reqs if config.max_num_queued_reqs is not None else -1,
            'queue_telemetry_available': 1,
        }
    except (AttributeError, KeyError, TypeError, RuntimeError):
        return {'queue_telemetry_available': 0}


def render(values):
    lines = []
    for key, value in values.items():
        name = 'gradiated_runtime_' + key
        lines.extend((f'# HELP {name} {METRICS[key]}', f'# TYPE {name} gauge', f'{name} {int(value)}'))
    return ('\n' + '\n'.join(lines) + '\n').encode()


class QueueMetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'].rstrip('/') != '/metrics':
            await self.app(scope, receive, send)
            return
        values = render(snapshot(scope))
        scope = {**scope, 'headers': [(key, value) for key, value in scope.get('headers', [])
                                    if key.lower() not in (b'accept', b'accept-encoding')] + [
                                        (b'accept', b'text/plain; version=0.0.4'),
                                        (b'accept-encoding', b'identity')]}
        append = False

        async def observe(message):
            nonlocal append
            if message['type'] == 'http.response.start':
                headers = message.get('headers', [])
                compressed = any(key.lower() == b'content-encoding' and value.lower() != b'identity'
                                 for key, value in headers)
                append = message['status'] == 200 and not compressed
                if append:
                    message = {**message, 'headers': [(key, value) for key, value in headers
                                                       if key.lower() != b'content-length']}
            elif message['type'] == 'http.response.body' and append and not message.get('more_body', False):
                message = {**message, 'body': message.get('body', b'') + values}
            await send(message)

        await self.app(scope, receive, observe)
