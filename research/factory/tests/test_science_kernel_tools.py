import hashlib
import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest

from grad_research.science_tools.common import ScienceToolError
from grad_research.science_tools.kernel_evaluator import evaluate_reproducer
from grad_research.science_tools.replacement import ReplacementRegistry
from grad_research.science_tools.reproducer import extract_reproducer


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_metadata(root: pathlib.Path, wall_share: float = 0.25) -> None:
    inputs = root / "inputs"
    inputs.mkdir(exist_ok=True)
    input_path = inputs / "fixture.json"
    input_path.write_text("[1,2,3]\n")
    (root / "metadata.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "exact_shape_reproducer",
                "operation": {
                    "id": "op-1",
                    "shape": [1, 16],
                    "layout": "contiguous",
                    "dtype": "float32",
                    "phase": "decode",
                    "hardware": "fixture",
                    "production_non_overlap_wall_share": wall_share,
                },
                "artifacts": {
                    "inputs": [
                        {
                            "path": "inputs/fixture.json",
                            "sha256": sha256(input_path),
                            "size_bytes": input_path.stat().st_size,
                        }
                    ]
                },
            }
        )
    )


class ReproducerTests(unittest.TestCase):
    def test_selected_operation_is_safely_extracted_with_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            input_path = artifacts / "tensor.json"
            reference_path = artifacts / "oracle.py"
            consumer_path = artifacts / "consume.py"
            candidate_path = artifacts / "candidate.py"
            input_path.write_text("[1, 2, 3]\n")
            reference_path.write_text("print('reference')\n")
            consumer_path.write_text("print('consumer')\n")
            candidate_path.write_text("print('candidate')\n")
            trace = root / "trace.jsonl"
            trace.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "operation_id": "other",
                                "semantic": {"family": "gemm", "phase": "prefill"},
                            }
                        ),
                        json.dumps(
                            {
                                "operation_id": "decode-qkv",
                                "semantic": {
                                    "family": "linear",
                                    "phase": "decode",
                                },
                                "shape": [8, 4096, 6144],
                                "layout": {"input": "row_major"},
                                "dtype": {"input": "float16", "weight": "fp8"},
                                "scales": {"weight": "per_tensor"},
                                "hardware": {"name": "H200", "sm": 90},
                                "production_non_overlap_wall_share": 0.17,
                                "artifacts": {
                                    "inputs": {
                                        "path": "tensor.json",
                                        "sha256": sha256(input_path),
                                    },
                                    "reference": "oracle.py",
                                    "consumer": "consume.py",
                                    "candidate": "candidate.py",
                                },
                            }
                        ),
                    ]
                )
                + "\n"
            )
            output = root / "repro"

            result = extract_reproducer(
                trace,
                output,
                semantic_selectors={
                    "family": "linear",
                    "semantic.phase": "decode",
                },
                artifact_root=artifacts,
            )

            self.assertEqual(result["artifact_count"], 4)
            metadata = json.loads((output / "metadata.json").read_text())
            self.assertEqual(metadata["operation"]["id"], "decode-qkv")
            self.assertEqual(metadata["operation"]["shape"], [8, 4096, 6144])
            self.assertEqual(metadata["operation"]["phase"], "decode")
            self.assertEqual(
                metadata["operation"]["production_non_overlap_wall_share"], 0.17
            )
            copied = output / metadata["artifacts"]["inputs"][0]["path"]
            self.assertEqual(copied.read_bytes(), input_path.read_bytes())
            self.assertEqual(
                metadata["artifacts"]["inputs"][0]["sha256"], sha256(copied)
            )

    def test_trace_artifact_traversal_is_rejected_without_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            (root / "secret.bin").write_bytes(b"secret")
            trace = root / "trace.json"
            trace.write_text(
                json.dumps(
                    {
                        "operations": [
                            {
                                "operation_id": "unsafe",
                                "artifacts": {"inputs": "../secret.bin"},
                            }
                        ]
                    }
                )
            )
            output = root / "repro"

            with self.assertRaisesRegex(ScienceToolError, "unsafe"):
                extract_reproducer(
                    trace,
                    output,
                    operation_id="unsafe",
                    artifact_root=artifacts,
                )

            self.assertFalse(output.exists())

    def test_generic_template_copies_explicit_benchmark_and_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            benchmark = root / "benchmark.py"
            reference = root / "reference.py"
            input_path = root / "input.json"
            benchmark.write_text("print(1)\n")
            reference.write_text("print(1)\n")
            input_path.write_text("[1, 2]\n")
            output = root / "generic"

            extract_reproducer(
                None,
                output,
                benchmark_path=benchmark,
                reference_path=reference,
                input_paths=[input_path],
                generic_metadata={
                    "shape": [32, 128],
                    "dtype": "float16",
                    "phase": "prefill",
                },
            )

            metadata = json.loads((output / "metadata.json").read_text())
            self.assertEqual(metadata["operation"]["shape"], [32, 128])
            self.assertTrue(
                (output / metadata["generic_template"]["benchmark_artifact"]).is_file()
            )
            self.assertEqual(len(metadata["artifacts"]["inputs"]), 1)

    def test_exact_reproducer_rejects_missing_shape_or_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            benchmark = root / "benchmark.py"
            reference = root / "reference.py"
            benchmark.write_text("print(1)\n")
            reference.write_text("print(1)\n")

            with self.assertRaisesRegex(ScienceToolError, "shape"):
                extract_reproducer(
                    None,
                    root / "missing-shape",
                    benchmark_path=benchmark,
                    reference_path=reference,
                )

            captured_input = root / "input.bin"
            captured_input.write_bytes(b"input")
            for shape in ("unknown", [32, -1], {"query": [1, None, 128]}):
                with self.subTest(shape=shape):
                    with self.assertRaisesRegex(
                        ScienceToolError,
                        "concrete positive integer|positive",
                    ):
                        extract_reproducer(
                            None,
                            root / f"invalid-shape-{len(str(shape))}",
                            benchmark_path=benchmark,
                            reference_path=reference,
                            input_paths=[captured_input],
                            generic_metadata={"shape": shape},
                        )


class KernelEvaluatorTests(unittest.TestCase):
    def test_correctness_timing_proof_setup_and_opportunity_are_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            repro = root / "repro"
            repro.mkdir()
            write_metadata(repro)
            output = root / "evaluation"
            emitter = (
                "import json,os,pathlib;"
                "p=os.environ.get('LAB_CANDIDATE_PROOF_PATH');"
                "p and pathlib.Path(p).write_text("
                "json.dumps({'implementation':'candidate'}));"
                "print(json.dumps({'values':[1.0,2.0,3.0]}))"
            )
            spec = {
                "commands": {
                    "setup": {
                        "argv": [
                            sys.executable,
                            "-c",
                            (
                                "import pathlib;"
                                "p=pathlib.Path(r'{output_dir}');"
                                "(p/'setup-count').write_text("
                                "str(int((p/'setup-count').read_text())+1)"
                                " if (p/'setup-count').exists() else '1');"
                                "(p/'compiled.bin').write_bytes(b'cubin')"
                            ),
                        ]
                    },
                    "reference": {"argv": [sys.executable, "-c", emitter]},
                    "baseline": {"argv": [sys.executable, "-c", emitter]},
                    "candidate": {"argv": [sys.executable, "-c", emitter]},
                },
                "correctness": {"atol": 1e-6, "rtol": 1e-6},
                "timing": {"warmup": 1, "repetitions": 3},
                "candidate_path_proof": {
                    "path": "candidate-proof.json",
                    "contains": {"implementation": "candidate"},
                },
                "compiler_artifacts": ["{output_dir}/compiled.bin"],
                "speed_of_light_seconds": 0.001,
                "profiler": {
                    "argv": [
                        sys.executable,
                        "-c",
                        "print('native profiler output retained as a raw log')",
                    ]
                },
            }

            result = evaluate_reproducer(
                repro, spec, output, timeout_seconds=5
            )

            self.assertEqual(result["status"], "complete")
            self.assertIsNone(result["decision"])
            self.assertTrue(result["correctness"]["candidate"]["passed"])
            self.assertTrue(result["correctness"]["full_output_consumed"])
            self.assertTrue(result["candidate_path_proof"]["verified"])
            self.assertEqual(
                len(result["candidate_path_proof"]["executions"]), 5
            )
            self.assertEqual((output / "setup-count").read_text(), "1")
            self.assertEqual(len(result["compiler_artifacts"]), 1)
            self.assertEqual(result["timing"]["baseline"]["count"], 3)
            self.assertEqual(result["timing"]["candidate"]["count"], 3)
            self.assertEqual(
                result["opportunity"]["production_non_overlap_wall_share"], 0.25
            )
            self.assertIsNone(result["profiler"]["output"])
            self.assertEqual(result["profiler"]["command"]["returncode"], 0)
            self.assertNotIn("winner", json.dumps(result).lower())

    def test_custom_consumer_receives_complete_file_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            repro = root / "repro"
            repro.mkdir()
            write_metadata(repro)
            output = root / "evaluation"
            producer = (
                "import json,os,pathlib;"
                "pathlib.Path('value.bin').write_bytes(b'full-output');"
                "p=os.environ.get('LAB_CANDIDATE_PROOF_PATH');"
                "p and pathlib.Path(p).write_text("
                "json.dumps({'selected':'candidate'}))"
            )
            consumer = (
                "import os,pathlib,sys;"
                "left=pathlib.Path(os.environ['LAB_REFERENCE_OUTPUT']).read_bytes();"
                "right=pathlib.Path(os.environ['LAB_TARGET_OUTPUT']).read_bytes();"
                "sys.exit(0 if left==right==b'full-output' else 7)"
            )
            command = {
                "argv": [sys.executable, "-c", producer],
                "output": {"kind": "files", "path": "value.bin"},
            }
            candidate_command = {
                **command,
                "argv": [sys.executable, "-c", producer, "candidate"],
            }
            spec = {
                "commands": {
                    "reference": command,
                    "baseline": command,
                    "candidate": candidate_command,
                },
                "correctness": {
                    "consumer": {"argv": [sys.executable, "-c", consumer]}
                },
                "timing": {"warmup": 0, "repetitions": 1},
                "candidate_path_proof": {
                    "path": "candidate-proof.json",
                    "contains": {"selected": "candidate"},
                },
            }

            result = evaluate_reproducer(repro, spec, output, timeout_seconds=5)

            self.assertEqual(result["status"], "complete")
            self.assertEqual(
                result["correctness"]["candidate"]["mode"], "custom_consumer"
            )
            self.assertTrue(result["correctness"]["candidate"]["passed"])
            self.assertTrue(
                pathlib.Path(
                    result["outputs"]["candidate"]["artifacts"][0]["path"]
                ).is_file()
            )

    def test_timing_uses_device_reported_json_metric_when_declared(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            repro = root / "repro"
            repro.mkdir()
            write_metadata(repro)
            output = root / "evaluation"

            def command(latency_us: int) -> dict[str, object]:
                return {
                    "argv": [
                        sys.executable,
                        "-c",
                        (
                            "import json,os,pathlib; "
                            "p=os.environ.get('LAB_CANDIDATE_PROOF_PATH'); "
                            "p and pathlib.Path(p).write_text("
                            "json.dumps({'selected':'candidate'})); "
                            f"print(json.dumps({{'values':[1,2],"
                            f"'latency_us':{latency_us}}}))"
                        ),
                    ],
                    "output": {
                        "kind": "json",
                        "source": "stdout",
                        "value_path": "values",
                    },
                }

            result = evaluate_reproducer(
                repro,
                {
                    "commands": {
                        "reference": command(10),
                        "baseline": command(10),
                        "candidate": command(7),
                    },
                    "timing": {
                        "warmup": 0,
                        "repetitions": 2,
                        "source": "output_json",
                        "value_path": "latency_us",
                        "unit": "microseconds",
                    },
                    "candidate_path_proof": {
                        "path": "candidate-proof.json",
                        "contains": {"selected": "candidate"},
                    },
                },
                output,
                timeout_seconds=5,
            )

            self.assertAlmostEqual(result["timing"]["baseline"]["median"], 10e-6)
            self.assertAlmostEqual(result["timing"]["candidate"]["median"], 7e-6)
            self.assertAlmostEqual(
                result["opportunity"]["measured_component_reduction_fraction"],
                0.3,
            )

    def test_stale_declared_outputs_cannot_be_certified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            repro = root / "repro"
            repro.mkdir()
            write_metadata(repro)
            stale = root / "stale.json"
            stale.write_text('{"value":1}\n')
            command = {
                "argv": [sys.executable, "-c", "pass"],
                "output": {"kind": "json", "path": str(stale)},
            }

            with self.assertRaisesRegex(ScienceToolError, "stale"):
                evaluate_reproducer(
                    repro,
                    {
                        "commands": {
                            "reference": command,
                            "baseline": command,
                            "candidate": {
                                **command,
                                "argv": [sys.executable, "-c", "pass", "candidate"],
                            },
                        }
                    },
                    root / "evaluation",
                    timeout_seconds=5,
                )

    def test_identical_baseline_and_candidate_require_candidate_path_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            repro = root / "repro"
            repro.mkdir()
            write_metadata(repro)
            command = {
                "argv": [
                    sys.executable,
                    "-c",
                    "import json; print(json.dumps({'value':1}))",
                ]
            }

            with self.assertRaisesRegex(ScienceToolError, "candidate_path_proof"):
                evaluate_reproducer(
                    repro,
                    {
                        "commands": {
                            "reference": command,
                            "baseline": command,
                            "candidate": command,
                        }
                    },
                    root / "evaluation",
                    timeout_seconds=5,
                )

    def test_command_failure_is_durable_and_keeps_raw_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            repro = root / "repro"
            repro.mkdir()
            write_metadata(repro)
            output = root / "evaluation"
            okay = {
                "argv": [
                    sys.executable,
                    "-c",
                    "import json; print(json.dumps({'value':1}))",
                ]
            }
            spec = {
                "commands": {
                    "reference": okay,
                    "baseline": okay,
                    "candidate": {
                        "argv": [
                            sys.executable,
                            "-c",
                            "import sys; print('candidate failed', file=sys.stderr); sys.exit(4)",
                        ]
                    },
                },
                "candidate_path_proof": {
                    "path": "candidate-proof.json",
                    "contains": {"selected": "candidate"},
                },
            }

            with self.assertRaisesRegex(ScienceToolError, "exit 4"):
                evaluate_reproducer(repro, spec, output, timeout_seconds=5)

            result = json.loads((output / "evaluation.json").read_text())
            self.assertEqual(result["status"], "failed")
            stderr_logs = list((output / "runs").glob("*/command.stderr.log"))
            self.assertTrue(stderr_logs)
            self.assertTrue(
                any("candidate failed" in path.read_text() for path in stderr_logs)
            )

    def test_timeout_is_durable_and_stops_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            repro = root / "repro"
            repro.mkdir()
            write_metadata(repro)
            output = root / "evaluation"
            slow = {
                "argv": [
                    sys.executable,
                    "-c",
                    "import time; time.sleep(2); print('{}')",
                ]
            }
            spec = {
                "commands": {
                    "reference": slow,
                    "baseline": slow,
                    "candidate": slow,
                }
            }

            with self.assertRaisesRegex(ScienceToolError, "exceeded"):
                evaluate_reproducer(
                    repro, spec, output, timeout_seconds=0.05
                )

            result = json.loads((output / "evaluation.json").read_text())
            self.assertEqual(result["status"], "failed")
            self.assertIn("exceeded", result["error"]["message"])


class ReplacementRegistryTests(unittest.TestCase):
    def test_context_selection_falls_back_and_writes_proof_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            proof = pathlib.Path(temporary) / "proof.jsonl"
            registry = ReplacementRegistry(proof_path=proof)
            registry.register(
                "attention",
                lambda value: f"stock:{value}",
                phase="decode",
                shape=(1, 8, 128),
            )

            with registry.select(
                "candidate",
                operation="attention",
                phase="decode",
                shape=(1, 8, 128),
            ):
                value = registry.call(
                    "attention", "x", phase="decode", shape=(1, 8, 128)
                )

            self.assertEqual(value, "stock:x")
            event = json.loads(proof.read_text().strip())
            self.assertEqual(event["requested_mode"], "candidate")
            self.assertEqual(event["selected"], "stock")
            self.assertTrue(event["fallback"])
            self.assertEqual(
                event["fallback_reason"], "candidate_not_registered"
            )
            self.assertEqual(
                event["requested_key"], "attention|decode|1x8x128"
            )

    def test_candidate_exception_can_fall_back_to_stock_with_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            proof = pathlib.Path(temporary) / "proof.jsonl"
            registry = ReplacementRegistry(proof_path=proof)

            def candidate(value: int) -> int:
                raise RuntimeError(f"bad candidate {value}")

            registry.register("linear", lambda value: value + 1, candidate)
            value = registry.call(
                "linear", 4, mode="candidate", fallback_on_error=True
            )

            self.assertEqual(value, 5)
            event = json.loads(proof.read_text().strip())
            self.assertEqual(event["fallback_reason"], "candidate_raised")
            self.assertEqual(event["candidate_error_type"], "RuntimeError")
            self.assertTrue(event["success"])

    def test_operation_wide_context_selects_specific_candidate(self) -> None:
        registry = ReplacementRegistry()
        registry.register(
            "attention",
            lambda: "stock",
            lambda: "candidate",
            phase="decode",
            shape=(2, 64),
        )

        with registry.select("candidate", operation="attention"):
            value = registry.call(
                "attention", phase="decode", shape=(2, 64)
            )

        self.assertEqual(value, "candidate")

    def test_environment_selector_can_enable_candidate(self) -> None:
        registry = ReplacementRegistry(environment_variable="TEST_REPLACEMENTS")
        registry.register(
            "linear",
            lambda: "stock",
            lambda: "candidate",
            phase="prefill",
            shape=(16, 4096),
        )
        previous = os.environ.get("TEST_REPLACEMENTS")
        os.environ["TEST_REPLACEMENTS"] = json.dumps(
            {"linear|prefill|16x4096": "candidate"}
        )
        try:
            value = registry.call(
                "linear", phase="prefill", shape=(16, 4096)
            )
        finally:
            if previous is None:
                os.environ.pop("TEST_REPLACEMENTS", None)
            else:
                os.environ["TEST_REPLACEMENTS"] = previous

        self.assertEqual(value, "candidate")


class WrapperTests(unittest.TestCase):
    def test_wrappers_are_executable(self) -> None:
        tools = pathlib.Path(__file__).parents[1] / "tools"
        for name in ("lab-reproducer", "lab-kernel-eval"):
            mode = (tools / name).stat().st_mode
            self.assertTrue(mode & stat.S_IXUSR, name)


if __name__ == "__main__":
    unittest.main()
