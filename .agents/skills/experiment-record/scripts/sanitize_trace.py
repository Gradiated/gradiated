"""Sanitize approved visible-message exports, not raw provider/customer payloads."""
from pathlib import Path
from collections import Counter
import argparse
import hashlib
import ipaddress
import json
import re

IPV4 = re.compile(r'(?<![A-Za-z0-9])(?:\d{1,3}\\*\.){3}\d{1,3}(?![A-Za-z0-9])')
IPV6 = re.compile(r'(?<![A-Za-z0-9])[0-9a-fA-F]*:[0-9a-fA-F:]+(?![A-Za-z0-9])')
ACCOUNT = re.compile(r'(?<![\w.])[\w.-]+@(?:\[[^\]\s]+\]|[A-Za-z0-9_.\\:-]+)')
AUTH_LINK = re.compile(r'https://login\.tailscale\.com/[^\s<>"\x27)]+', re.I)
CREDENTIAL = re.compile(r'\b(?:sk-(?:or-v1-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|(?:AKIA|ASIA)[A-Z0-9]{16})\b')
ACTIVITY_FIELDS = {'position', 'item_id', 'run_id', 'type', 'status', 'updated_at', 'body_exported', 'tool_name'}


def redact(text, counts):
    def replace(category, replacement):
        def apply(_):
            counts[category] += 1
            return replacement
        return apply
    text = AUTH_LINK.sub(replace('authentication_links', '[REDACTED_AUTHENTICATION_LINK]'), text)
    text = CREDENTIAL.sub(replace('credential_tokens', '[REDACTED_CREDENTIAL]'), text)
    text = ACCOUNT.sub(replace('account_endpoints', '[REDACTED_ACCOUNT_ENDPOINT]'), text)

    def address(match):
        candidate = match.group().replace('\\', '')
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            return match.group()
        counts['network_addresses'] += 1
        return '[REDACTED_NETWORK_ADDRESS]'
    text = IPV4.sub(address, text)
    return IPV6.sub(address, text)


def activity_metadata(row):
    clean = {k: v for k, v in row.items() if k in ACTIVITY_FIELDS}
    if row['type'] == 'reasoning':
        raise ValueError('Private reasoning must not enter activity exports')
    if 'tool_name' in clean and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.:-]*', clean['tool_name']):
        raise ValueError('Unexpected tool identifier')
    clean['body_exported'] = False
    return clean


def sanitize(directory):
    manifest_path = directory / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    counts = Counter()
    messages = [json.loads(line) for line in (directory / 'conversation.jsonl').read_text().splitlines()]
    activities = [json.loads(line) for line in (directory / 'activity.jsonl').read_text().splitlines()]
    for row in messages:
        if row['type'] not in {'user_message', 'assistant_message', 'proposed_plan'}:
            raise ValueError('Unexpected conversation item type')
        per_message = Counter()
        row['text'] = redact(row['text'], per_message)
        if per_message:
            row['redactions'] = dict(Counter(row.get('redactions', {})) + per_message)
            counts.update(per_message)
    counts['removed_command_previews'] = sum('command_preview' in row for row in activities)
    activities = [activity_metadata(row) for row in activities]
    for filename, rows in [('conversation.jsonl', messages), ('activity.jsonl', activities)]:
        (directory / filename).write_text(''.join(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n' for row in rows))
    manifest['redactions'] = dict(Counter(manifest.get('redactions', {})) + counts)
    manifest['redaction_count_semantics'] = 'Cumulative transformation events; deleted previews may overlap earlier IP redactions.'
    manifest['activity_scope'] = 'Metadata only: tool names, item types, IDs, status, timestamps. No commands, arguments, titles, or raw input/output bodies.'
    manifest['network_redaction'] = 'Literal and regex-escaped IPv4, IPv6, and account endpoints removed from visible message text; command previews omitted entirely.'
    manifest['files'] = {filename: {'sha256': hashlib.sha256((directory / filename).read_bytes()).hexdigest(),
                                  'bytes': (directory / filename).stat().st_size}
                         for filename in ['conversation.jsonl', 'activity.jsonl']}
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    return dict(counts)


def self_test():
    cases = ['endpoint=203.0.113.7', r'endpoint=100\.64\.1\.2', r'endpoint=203\\.0\\.113\\.7',
             'ssh root@203.0.113.7', r'ssh root@203\.0\.113\.7', 'root@[REDACTED_PRIVATE_IP]',
             'endpoint=fd00::1234', 'alice@example.invalid']
    for text in cases:
        counts = Counter()
        clean = redact(text, counts)
        assert '[REDACTED_' in clean and sum(counts.values()) > 0
        assert clean == redact(clean, Counter()), 'Redaction must be idempotent'
    assert redact('torch 2.14.1; loss 0.195; 12:00:55', Counter()) == 'torch 2.14.1; loss 0.195; 12:00:55'
    sample = {'position': 1, 'type': 'command_execution', 'command_preview': 'ssh root@203.0.113.7',
              'title': 'private endpoint', 'text': 'restricted body'}
    assert activity_metadata(sample) == {'position': 1, 'type': 'command_execution', 'body_exported': False}
    print('PASS: literal/escaped addresses, public SSH/account endpoints, IPv6, idempotence, metadata allowlist')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace_directory', nargs='?', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
    if args.trace_directory:
        print(json.dumps(sanitize(args.trace_directory)))
    elif not args.self_test:
        parser.error('Provide trace_directory or --self-test')
