import hashlib
import json
from pathlib import Path
import tempfile
import urllib.request

REPOSITORY = 'RadixArk/Kimi-K3.1-Dflash2-Preview'
REVISION = 'd0d8bc2e3c6d0a195d2e00a49017e71ca8d881f1'
RELATIVE_PATH = Path('models/kimi-dflash')
MANIFEST_SHA256 = '7628fd0d9271872d3136204422293ea40eb4f77109c1e411d3dff58f0b8f8bc8'


def manifest(path):
    if path.is_symlink():
        raise ValueError('Draft manifest must be a regular file')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != MANIFEST_SHA256:
        raise ValueError('Draft manifest checksum mismatch')
    value = json.loads(data)
    if value['repository'] != REPOSITORY or value['revision'] != REVISION:
        raise ValueError('Unexpected draft checkpoint identity')
    if {item['path'] for item in value['files']} != {'config.json', 'model.safetensors'} or len(value['files']) != 2:
        raise ValueError('Unexpected draft checkpoint files')
    for item in value['files']:
        if type(item['size']) is not int or item['size'] <= 0 or len(item['sha256']) != 64:
            raise ValueError('Invalid draft checkpoint file descriptor')
    return data, value


def checksum(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify(directory):
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError('Draft directory must not be a symlink')
    _, pinned = manifest(directory / 'manifest.json')
    if {path.name for path in directory.iterdir()} != {'manifest.json', 'config.json', 'model.safetensors'}:
        raise ValueError('Draft checkpoint contains unexpected files')
    for item in pinned['files']:
        path = directory / item['path']
        if path.is_symlink() or not path.is_file():
            raise ValueError('Draft checkpoint file must be regular: ' + item['path'])
        if path.stat().st_size != item['size'] or checksum(path) != item['sha256']:
            raise ValueError('Draft checkpoint size/checksum mismatch: ' + item['path'])
    return {
        'repository': REPOSITORY,
        'revision': REVISION,
        'path': RELATIVE_PATH.as_posix(),
        'manifest_sha256': MANIFEST_SHA256,
        'files': {item['path']: {'size': item['size'], 'sha256': item['sha256']} for item in pinned['files']},
    }


def package(manifest_path, destination):
    data, pinned = manifest(Path(manifest_path))
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError('Draft package destination must be absent')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.kimi-dflash-', dir=destination.parent) as temporary:
        stage = Path(temporary) / 'model'
        stage.mkdir()
        for item in pinned['files']:
            url = f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{item['path']}"
            digest, count = hashlib.sha256(), 0
            with urllib.request.urlopen(url, timeout=120) as response, (stage / item['path']).open('xb') as stream:
                while block := response.read(1024 * 1024):
                    count += len(block)
                    if count > item['size']:
                        raise ValueError('Draft download exceeds pinned size: ' + item['path'])
                    digest.update(block)
                    stream.write(block)
            if count != item['size'] or digest.hexdigest() != item['sha256']:
                raise ValueError('Draft download size/checksum mismatch: ' + item['path'])
        (stage / 'manifest.json').write_bytes(data)
        identity = verify(stage)
        stage.rename(destination)
    return identity
