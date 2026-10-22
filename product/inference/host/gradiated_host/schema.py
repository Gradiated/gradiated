# The base image has no jsonschema package; keywords the enrollment schemas do not use are refused.
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
TYPES = {
    'object': lambda value: isinstance(value, dict),
    'string': lambda value: isinstance(value, str),
    'boolean': lambda value: isinstance(value, bool),
    'integer': lambda value: isinstance(value, int) and not isinstance(value, bool),
    'number': lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
}
KEYWORDS = {'$schema', 'type', 'properties', 'required', 'additionalProperties',
            'pattern', 'const', 'enum', 'minimum', 'maximum'}


def load(name):
    return json.loads((HERE / f'enrollment-{name}.schema.json').read_text())


def _pattern(pattern):
    # JSON Schema patterns are ECMAScript; in Python "$" also matches before a final newline.
    return re.compile(pattern[:-1] + r'\Z' if pattern.endswith('$') else pattern)


def check(schema, value, where='$'):
    unknown = set(schema) - KEYWORDS
    if unknown:
        raise ValueError(f'Unsupported schema keywords at {where}: {sorted(unknown)}')
    if 'type' in schema and not TYPES[schema['type']](value):
        raise ValueError(f'{where} must be {schema["type"]}')
    if 'const' in schema and value != schema['const']:
        raise ValueError(f'{where} must be {schema["const"]!r}')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'{where} must be one of {schema["enum"]}')
    if 'pattern' in schema and not _pattern(schema['pattern']).search(value):
        raise ValueError(f'{where} has an invalid format')
    if 'minimum' in schema and value < schema['minimum']:
        raise ValueError(f'{where} is below {schema["minimum"]}')
    if 'maximum' in schema and value > schema['maximum']:
        raise ValueError(f'{where} is above {schema["maximum"]}')
    if isinstance(value, dict):
        properties = schema.get('properties', {})
        missing = [name for name in schema.get('required', []) if name not in value]
        if missing:
            raise ValueError(f'{where} is missing {missing}')
        if schema.get('additionalProperties') is False and set(value) - set(properties):
            raise ValueError(f'{where} has unexpected fields {sorted(set(value) - set(properties))}')
        for name, item in value.items():
            if name in properties:
                check(properties[name], item, f'{where}.{name}')
    return value


def payload(value):
    return check(load('payload'), value)


def result(value):
    return check(load('result'), value)
