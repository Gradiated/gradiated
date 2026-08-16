import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nebius"))

from observer_dependency_producer import ProducerError, materialize_export, probe_target_schema  # noqa: E402


class ProducerTests(unittest.TestCase):
    def _fixture(self, root: Path) -> Path:
        path = root / "positive.sqlite"
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE StringIds(id INTEGER, value TEXT)")
        con.execute("CREATE TABLE NVTX_EVENTS(start INTEGER, end INTEGER, text TEXT)")
        con.execute("CREATE TABLE CUDA_API_TRACE(start INTEGER, end INTEGER, correlationId INTEGER, streamId INTEGER)")
        con.execute("INSERT INTO StringIds VALUES (1, 'scheduler-iteration-00000000000000000001')")
        con.execute("INSERT INTO NVTX_EVENTS VALUES (10, 30, 'scheduler-iteration-00000000000000000001')")
        con.execute("INSERT INTO CUDA_API_TRACE VALUES (12, 25, 77, 3)")
        con.commit(); con.close()
        return path

    def test_exact_version_probe_and_materialization_are_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = self._fixture(root)
            schema = probe_target_schema(source)
            self.assertEqual(schema["nsys_version"], "2026.3.1.157")
            request = [{"request_id": "req-1", "raw": "exact"}]
            first = materialize_export(source, root / "one", request_rows=request)
            second = materialize_export(source, root / "two", request_rows=request)
            self.assertEqual(first, second)
            self.assertEqual((root / "one" / "raw-events.jsonl").read_bytes(), (root / "two" / "raw-events.jsonl").read_bytes())

    def test_missing_or_renamed_schema_fails_before_materialization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / "negative.sqlite"
            con = sqlite3.connect(path)
            con.execute("CREATE TABLE NVTX_EVENTS(start INTEGER, end INTEGER, text TEXT)")
            con.execute("CREATE TABLE CUDA_API_TRACE(start INTEGER, end INTEGER, correlationId INTEGER, stream_id INTEGER)")
            con.commit(); con.close()
            with self.assertRaises(ProducerError):
                probe_target_schema(path)

    def test_wrong_version_and_one_byte_source_mutation_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = self._fixture(root)
            with self.assertRaises(ProducerError):
                probe_target_schema(source, version="2026.3.1.158")
            mutated = root / "mutated.sqlite"; mutated.write_bytes(source.read_bytes() + b"x")
            with self.assertRaises(ProducerError):
                probe_target_schema(mutated)


if __name__ == "__main__":
    unittest.main()
