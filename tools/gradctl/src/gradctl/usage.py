"""GPU cost events: `compute_usage` events in the FDE PostHog project, next to OpenRouter's `$ai_generation` events.

One event covers one resource (a VM, or GPU time recorded by hand) for one interval:

  distinct_id        the customer the work is for (`bild-ai`), or `gradiated` for internal work; OpenRouter
                     requests set the same value as `user`
  customer, workstream, stage, run_id
                     attribution; stage is e.g. cleaning, env-build, training, rollout, eval, serving, dev
  provider, resource_name, resource_id, region, term
                     where it ran; term is spot or on-demand
  gpu_type, gpu_count
  usd_per_hour, usd_per_gpu_hour, price_source
                     the price used for this interval and where it came from
  interval_start, interval_end, duration_seconds, vm_state, billed
  gpu_hours, cost_usd
                     zero unless the resource was in a billed state
  schema_version, source

The event uuid is derived from the resource and interval start, so sending an interval twice does not count it
twice. The default token is the FDE project's public ingestion token, which can only write events.
GRADIATED_USAGE_POSTHOG_TOKEN and GRADIATED_USAGE_POSTHOG_HOST override it; GRADIATED_USAGE_EVENTS=0 turns
sending off.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

EVENT = 'compute_usage'
SCHEMA_VERSION = 1
# Public ingestion token of the FDE PostHog project: it can only send events.
DEFAULT_TOKEN = 'phc_rbdJJeRHk2fUEWLrH4ALmLmYWHPsd5ZyNyaps3QXHqDM'
DEFAULT_HOST = 'https://us.i.posthog.com'
UNATTRIBUTED = 'unattributed'
# Provider states in which GPU time is billed. A stopped VM still pays for its disk, which is not counted.
BILLED_STATES = {'RUNNING', 'STARTING', 'PROVISIONING', 'UPDATING'}
NAMESPACE = uuid.UUID('6f1d2b3c-7a4e-4c5d-9b8a-0c1d2e3f4a5b')


def now() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    text = str(value).replace('Z', '+00:00')
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def event(*, customer, stage, run_id, workstream, provider, resource_name, resource_id, region, term, gpu_type,
          gpu_count, usd_per_hour, price_source, start, end, vm_state, source) -> dict:
    duration = max(0.0, (end - start).total_seconds())
    billed = vm_state in BILLED_STATES and usd_per_hour is not None
    hours = duration / 3600
    customer = customer or UNATTRIBUTED
    key = f'{provider}:{resource_id or resource_name}:{start.isoformat()}'
    return {
        'event': EVENT,
        'distinct_id': customer,
        'timestamp': end.isoformat(),
        'uuid': str(uuid.uuid5(NAMESPACE, key)),
        'properties': {
            'schema_version': SCHEMA_VERSION, 'source': source,
            'customer': customer, 'workstream': workstream, 'stage': stage, 'run_id': run_id,
            'provider': provider, 'resource_name': resource_name, 'resource_id': resource_id, 'region': region,
            'term': term, 'gpu_type': gpu_type, 'gpu_count': gpu_count,
            'usd_per_hour': usd_per_hour,
            'usd_per_gpu_hour': (usd_per_hour / gpu_count) if usd_per_hour is not None and gpu_count else None,
            'price_source': price_source,
            'interval_start': start.isoformat(), 'interval_end': end.isoformat(),
            'duration_seconds': round(duration, 1), 'vm_state': vm_state, 'billed': billed,
            'gpu_hours': round(hours * (gpu_count or 0), 6) if billed else 0.0,
            'cost_usd': round(hours * usd_per_hour, 6) if billed else 0.0,
        },
    }


def send(events: list[dict]) -> int:
    """Send events to PostHog in one batch; returns how many were sent (0 when sending is off)."""
    if not events or os.environ.get('GRADIATED_USAGE_EVENTS', '1') == '0':
        return 0
    host = os.environ.get('GRADIATED_USAGE_POSTHOG_HOST', DEFAULT_HOST).rstrip('/')
    body = json.dumps({'api_key': os.environ.get('GRADIATED_USAGE_POSTHOG_TOKEN', DEFAULT_TOKEN),
                       'batch': events}).encode()
    request = urllib.request.Request(f'{host}/batch/', data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()
    return len(events)


@contextlib.contextmanager
def ledger(state: Path):
    """The local record of each VM's attribution and how far it has been metered, locked while it is changed."""
    path = state / 'usage.json'
    with open(state / 'usage.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(path.read_text()) if path.exists() else {}
        yield data
        with tempfile.NamedTemporaryFile('w', dir=state, delete=False) as replacement:
            json.dump(data, replacement, indent=1, sort_keys=True)
        os.replace(replacement.name, path)
