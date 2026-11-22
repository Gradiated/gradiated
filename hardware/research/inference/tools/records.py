#!/usr/bin/env python3
"""Validate compact research records without loading models or contacting devices."""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import mean

PROJECT = Path(__file__).resolve().parents[1]
REPO = next(p for p in PROJECT.parents if (p / 'product').is_dir())


def reject_constant(value):
    raise ValueError(f'Non-finite JSON constant: {value}')


def read(path):
    return json.loads(Path(path).read_text(), parse_constant=reject_constant)


def configuration_digest(configuration):
    encoded = json.dumps(configuration, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def validate_schema(value, schema, location='$'):
    if 'anyOf' in schema:
        for option in schema['anyOf']:
            try:
                validate_schema(value, option, location)
                return
            except ValueError:
                pass
        raise ValueError(f'{location}: no allowed representation matched')
    if 'const' in schema and (type(value) is not type(schema['const']) or value != schema['const']):
        raise ValueError(f'{location}: expected {schema["const"]!r}')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'{location}: invalid value {value!r}')
    kind = schema.get('type')
    kinds = {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool, 'null': type(None)}
    if kind == 'number':
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f'{location}: expected a finite number')
    elif kind and type(value) is not kinds[kind]:
        raise ValueError(f'{location}: expected {kind}')
    if kind == 'object':
        properties = schema.get('properties', {})
        missing = set(schema.get('required', [])) - value.keys()
        extra = value.keys() - properties.keys()
        if missing or (schema.get('additionalProperties') is False and extra):
            raise ValueError(f'{location}: missing {sorted(missing)}, unexpected {sorted(extra)}')
        for key, item in value.items():
            if key in properties:
                validate_schema(item, properties[key], f'{location}.{key}')
    elif kind == 'array':
        if len(value) < schema.get('minItems', 0):
            raise ValueError(f'{location}: insufficient samples')
        for index, item in enumerate(value):
            validate_schema(item, schema['items'], f'{location}[{index}]')
    elif kind == 'string':
        if len(value) < schema.get('minLength', 0) or ('pattern' in schema and not re.fullmatch(schema['pattern'], value)):
            raise ValueError(f'{location}: invalid string')
    if 'minimum' in schema and value < schema['minimum']:
        raise ValueError(f'{location}: below minimum')


def validate(record):
    validate_schema(record, read(PROJECT / 'schemas/run.schema.json'))
    device = record['device']
    if configuration_digest(device['configuration']) != device['configuration_sha256']:
        raise ValueError('Device configuration differs from its SHA-256 pin')
    times = [datetime.fromisoformat(record[key].replace('Z', '+00:00')) for key in ('started_at', 'completed_at')]
    if any(t.tzinfo is None for t in times) or times[1] < times[0]:
        raise ValueError('Run timestamps need timezones and chronological order')
    if record['supersedes'] == record['id']:
        raise ValueError('A correction must have a new run ID')
    names = [m['name'] for m in record['metrics']]
    if len(names) != len(set(names)):
        raise ValueError('Metric names must be unique')
    if record['status'] == 'passed' and not (record['correctness']['passed'] and record['quality']['passed']):
        raise ValueError('A passed run must pass correctness and quality')
    return record


def compare(left, right):
    for record in (left, right):
        validate(record)
        if record['status'] != 'passed':
            raise ValueError('Only passed runs can support this comparison')
    for field in ('model', 'workload', 'protocol', 'evidence_type'):
        if left[field] != right[field]:
            raise ValueError(f'Incompatible {field}; define a reviewed comparison instead')
    differences = []
    right_metrics = {m['name']: m for m in right['metrics']}
    for first in left['metrics']:
        second = right_metrics.get(first['name'])
        if second is None:
            continue
        if (first['unit'], first['kind'], first['method']) != (second['unit'], second['kind'], second['method']):
            raise ValueError(f'Incompatible metric definition: {first["name"]}')
        a, b = mean(first['samples']), mean(second['samples'])
        differences.append({'metric': first['name'], 'unit': first['unit'], 'left_mean': a, 'right_mean': b,
                            'right_over_left': b / a if a else None,
                            'sample_counts': [len(first['samples']), len(second['samples'])]})
    if not differences:
        raise ValueError('No common metrics')
    return {'left': left['id'], 'right': right['id'], 'metrics': differences,
            'note': 'Descriptive sample means, not a significance test. Inspect settings, conditions and limitations.'}


def verify_artifacts(manifest, root):
    root = Path(root).resolve()
    files = manifest['files']
    if not files:
        raise ValueError('Artifact manifest is empty')
    for name, pin in files.items():
        if Path(name).is_absolute():
            raise ValueError(f'Artifact path must be relative: {name}')
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f'Artifact is absent or escapes root: {name}')
        if path.stat().st_size != pin['bytes'] or digest(path) != pin['sha256']:
            raise ValueError(f'Artifact differs: {name}')
    for name, target in manifest.get('symlinks', {}).items():
        path = root / name
        if (Path(name).is_absolute() or not path.parent.resolve().is_relative_to(root)
                or not path.is_symlink() or str(path.readlink()) != target):
            raise ValueError(f'Artifact symlink differs or escapes root: {name}')
    return len(files)


def check():
    result_root = PROJECT / 'results'
    paths = sorted(result_root.rglob('run.json'))
    runs = {}
    registered = set()
    for path in paths:
        record = validate(read(path))
        if (record['id'] in runs or path.parent.name != record['id']
                or path.parent.parent != result_root):
            raise ValueError(f'Duplicate or misplaced run: {path}')
        runs[record['id']] = record
        registered.add(path.resolve())
    for identity in runs:
        visited = set()
        current = identity
        while current is not None:
            if current in visited or current not in runs:
                raise ValueError(f'Correction history is cyclic or incomplete: {identity}')
            visited.add(current)
            current = runs[current]['supersedes']
    for baseline in read(PROJECT / 'models/baselines.json')['baselines']:
        path = (PROJECT / 'models' / baseline['model_manifest']).resolve()
        if not path.is_relative_to(PROJECT) or not path.is_file():
            raise ValueError(f'Missing baseline manifest: {baseline["id"]}')
        if digest(path) != baseline['model_manifest_sha256']:
            raise ValueError(f'Baseline manifest changed: {baseline["id"]}')
    for publication in (REPO / 'hardware/publishing').glob('**/results.json'):
        selection = read(publication)
        validate_schema(selection, read(PROJECT / 'schemas/publication.schema.json'))
        selected = set()
        for pin in selection['runs']:
            path = (REPO / pin['path']).resolve()
            if path not in registered or path in selected or digest(path) != pin['sha256']:
                raise ValueError(f'Invalid publication run: {pin["path"]}')
            selected.add(path)
            run = validate(read(path))
            if run['status'] != 'passed':
                raise ValueError('Publication selects a failed run')
    print(f'Validated {len(paths)} run records, baseline pins and publication selections.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('check')
    command = commands.add_parser('validate'); command.add_argument('path', type=Path)
    command = commands.add_parser('compare'); command.add_argument('left', type=Path); command.add_argument('right', type=Path)
    command = commands.add_parser('verify-artifacts'); command.add_argument('manifest', type=Path); command.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'check':
            check()
        elif args.command == 'validate':
            validate(read(args.path)); print('Valid run record.')
        elif args.command == 'compare':
            print(json.dumps(compare(read(args.left), read(args.right)), indent=2, allow_nan=False))
        else:
            print(f'Verified {verify_artifacts(read(args.manifest), args.root)} artifacts.')
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
