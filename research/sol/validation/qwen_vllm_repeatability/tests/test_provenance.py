import unittest

from validation.qwen_vllm_repeatability.provenance import (
    SourceProvenance,
    validate_source,
)
from validation.qwen_vllm_repeatability.schema import CampaignSpec
from validation.qwen_vllm_repeatability.tests.test_schema import valid_mapping


class ProvenanceTests(unittest.TestCase):
    def test_source_content_identity_includes_dirty_diff_and_commands(self) -> None:
        first = SourceProvenance.create(
            revision="b" * 40,
            version="0.1.dev1",
            tracked_diff_sha256="c" * 64,
            installed_binary_sha256="f" * 64,
            installed_binary_path="/tmp/vllm/_C.abi3.so",
            dirty_paths=("a.cpp",),
            server_command=("python", "-m", "server"),
            benchmark_command=("python", "-m", "bench"),
        )
        second = SourceProvenance.create(
            revision="b" * 40,
            version="0.1.dev1",
            tracked_diff_sha256="d" * 64,
            installed_binary_sha256="f" * 64,
            installed_binary_path="/tmp/vllm/_C.abi3.so",
            dirty_paths=("a.cpp",),
            server_command=("python", "-m", "server"),
            benchmark_command=("python", "-m", "bench"),
        )

        self.assertNotEqual(first.content_id, second.content_id)

    def test_validation_rejects_revision_version_or_diff_drift(self) -> None:
        spec = CampaignSpec.from_mapping(valid_mapping())
        source = SourceProvenance.create(
            revision="b" * 40,
            version="wrong",
            tracked_diff_sha256="c" * 64,
            installed_binary_sha256="f" * 64,
            installed_binary_path="/tmp/vllm/_C.abi3.so",
            dirty_paths=("a.cpp",),
            server_command=("python",),
            benchmark_command=("python",),
        )

        reasons = validate_source(source, spec.engine)

        self.assertEqual(reasons, ("vLLM version drift",))


if __name__ == "__main__":
    unittest.main()
