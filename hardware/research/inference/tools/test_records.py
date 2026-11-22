import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import records


def sample():
    identity = {'id': 'fixture', 'sha256': 'a' * 64}
    return {
        'schema_version': 1, 'id': 'fixture-run', 'experiment_id': 'fixture-experiment',
        'status': 'passed', 'evidence_type': 'software',
        'source': {'commit': 'b' * 40, 'patch_sha256': None},
        'model': identity.copy(), 'implementation': identity.copy(), 'workload': identity.copy(),
        'device': {'id': 'test-device', 'configuration': {}, 'configuration_sha256': '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a'},
        'protocol': {'id': 'fixture-v1', 'sha256': 'd' * 64, 'quality_gate': 'exact-reference',
                     'tokenizer': 'bytes', 'batch_size': 1, 'concurrency': 1, 'context_limit': 256,
                     'warmup': 'none', 'measurement_boundary': 'software-process'},
        'correctness': {'passed': True, 'evidence': 'test fixture'},
        'quality': {'passed': True, 'evidence': 'test fixture'}, 'conditions': {},
        'started_at': '2026-11-14T12:00:00Z', 'completed_at': '2026-11-14T12:00:01Z',
        'metrics': [{'name': 'latency', 'unit': 'ms', 'samples': [2, 4],
                     'kind': 'observed', 'method': 'fixture-clock-v1'}],
        'artifacts': [], 'limitations': ['Synthetic unit-test data, never a research result.'], 'supersedes': None,
    }


class RecordContract(unittest.TestCase):
    def test_comparison_keeps_samples_and_allows_a_different_implementation(self):
        first, second = sample(), sample()
        second['id'] = 'fixture-other'
        second['implementation']['sha256'] = 'e' * 64
        second['metrics'][0]['samples'] = [1, 2]
        result = records.compare(first, second)['metrics'][0]
        self.assertEqual(result['right_over_left'], 0.5)
        self.assertEqual(result['sample_counts'], [2, 2])

    def test_unlike_workloads_quality_boundaries_and_evidence_are_rejected(self):
        for field, value in [('model', {'id': 'different', 'sha256': 'f' * 64}),
                             ('workload', {'id': 'different', 'sha256': 'f' * 64}),
                             ('evidence_type', 'physical-measurement')]:
            other = sample(); other[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                records.compare(sample(), other)
        other = sample(); other['protocol']['measurement_boundary'] = 'whole-board'
        with self.assertRaises(ValueError): records.compare(sample(), other)
        other = sample(); other['protocol']['quality_gate'] = 'relaxed'
        with self.assertRaises(ValueError): records.compare(sample(), other)

    def test_failed_or_nonfinite_measurements_cannot_support_a_speedup(self):
        for change in ('failed', 'nan', 'negative', 'missing-quality', 'units'):
            other = sample()
            if change == 'failed': other['status'] = 'failed'
            if change == 'nan': other['metrics'][0]['samples'] = [float('nan')]
            if change == 'negative': other['metrics'][0]['samples'] = [-1]
            if change == 'missing-quality': other['quality']['passed'] = False
            if change == 'units': other['metrics'][0]['unit'] = 'seconds'
            with self.subTest(change=change), self.assertRaises(ValueError):
                records.compare(sample(), other)

    def test_artifact_corruption_and_path_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); artifact = root / 'weights.bin'; artifact.write_bytes(b'fixture')
            pin = {'bytes': artifact.stat().st_size, 'sha256': records.digest(artifact)}
            self.assertEqual(records.verify_artifacts({'files': {'weights.bin': pin}}, root), 1)
            artifact.write_bytes(b'changed')
            with self.assertRaises(ValueError): records.verify_artifacts({'files': {'weights.bin': pin}}, root)
            with self.assertRaises(ValueError): records.verify_artifacts({'files': {'../weights.bin': pin}}, root)

    def test_schema_rejects_missing_provenance_and_self_corrections(self):
        item = sample(); del item['source']
        with self.assertRaises(ValueError): records.validate(item)
        item = sample(); item['supersedes'] = item['id']
        with self.assertRaises(ValueError): records.validate(item)
        item = sample(); item['started_at'] = '2026-11-14T12:00:02Z'
        with self.assertRaises(ValueError): records.validate(item)

    def test_configuration_pin_detects_changed_device_settings(self):
        item = sample()
        item['device']['configuration']['clock_mhz'] = 50
        with self.assertRaises(ValueError):
            records.validate(item)

    def test_artifact_symlink_retargeting_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'payload').write_bytes(b'fixture')
            (root / 'selected').symlink_to('payload')
            manifest = {'files': {'payload': {'bytes': 7, 'sha256': records.digest(root / 'payload')}},
                        'symlinks': {'selected': 'payload'}}
            self.assertEqual(records.verify_artifacts(manifest, root), 1)
            (root / 'selected').unlink()
            (root / 'selected').symlink_to('elsewhere')
            with self.assertRaises(ValueError):
                records.verify_artifacts(manifest, root)

    def test_publication_rejects_unregistered_and_malformed_selections(self):
        with tempfile.TemporaryDirectory() as directory:
            root, project = self.registry(Path(directory))
            extra = project / 'results/unregistered.json'
            extra.write_text(json.dumps(sample()))
            publication = root / 'hardware/publishing/example/results.json'
            publication.parent.mkdir(parents=True)
            publication.write_text(json.dumps({'schema_version': 1, 'publication_id': 'example',
                'runs': [{'path': str(extra.relative_to(root)), 'sha256': records.digest(extra)}]}))
            with patch.object(records, 'PROJECT', project), patch.object(records, 'REPO', root):
                with self.assertRaises(ValueError): records.check()
                publication.write_text(json.dumps({'schema_version': 1, 'runs': []}))
                with self.assertRaises(ValueError): records.check()

    def test_corrections_require_an_existing_acyclic_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root, project = self.registry(Path(directory))
            first = sample(); first['supersedes'] = 'missing-run'
            folder = project / 'results' / first['id']; folder.mkdir()
            (folder / 'run.json').write_text(json.dumps(first))
            with patch.object(records, 'PROJECT', project), patch.object(records, 'REPO', root):
                with self.assertRaises(ValueError): records.check()
                second = sample(); second['id'] = 'second-run'; second['supersedes'] = first['id']
                first['supersedes'] = second['id']
                (folder / 'run.json').write_text(json.dumps(first))
                folder = project / 'results' / second['id']; folder.mkdir()
                (folder / 'run.json').write_text(json.dumps(second))
                with self.assertRaises(ValueError): records.check()
                first['supersedes'] = None
                (project / 'results' / first['id'] / 'run.json').write_text(json.dumps(first))
                records.check()

    def registry(self, directory):
        project = directory / 'hardware/research/inference'
        (project / 'schemas').mkdir(parents=True)
        for source in records.PROJECT.joinpath('schemas').glob('*.json'):
            (project / 'schemas' / source.name).write_bytes(source.read_bytes())
        (project / 'results').mkdir()
        (project / 'models').mkdir()
        (project / 'models/baselines.json').write_text('{"baselines": []}')
        return directory, project


if __name__ == '__main__':
    unittest.main()
