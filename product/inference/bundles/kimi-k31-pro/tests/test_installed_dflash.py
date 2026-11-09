"""CPU oracles executing functions from the installed Kimi DFLASH overlay.

Explicit KIMI_INSTALLED_SOURCE, KIMI_ORIGINAL_SOURCE and KIMI_PATCH_DIRECTORY
paths are required. Missing Torch or sources fail instead of skipping tests.
No GPU, model weights or SGLang import required.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import torch
SOURCE = Path(os.environ["KIMI_INSTALLED_SOURCE"])
PATCHES = Path(os.environ["KIMI_PATCH_DIRECTORY"])
ORIGINAL = Path(os.environ["KIMI_ORIGINAL_SOURCE"])


def functions(source, names, namespace):
    tree = ast.parse(source)
    selected = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            selected.append(node)
        elif isinstance(node, ast.ClassDef):
            selected.extend(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name in names)
    if {node.name for node in selected} != set(names):
        raise AssertionError("Missing pinned source functions")
    for node in selected:
        node.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)] + selected, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), "<patched-pinned-sglang>", "exec"), namespace)


class SamplingInfo:
    def __init__(self, batch_size, vocab):
        self.batch_size = batch_size
        self.has_custom_logit_processor = False
        self.penalizer_orchestrator = SimpleNamespace(is_required=True)
        self.acc_linear_penalties = torch.full((batch_size, vocab), 100.0)
        self.acc_additive_penalties = torch.full((batch_size, vocab), 200.0)
        self.acc_scaling_penalties = None
        self.grammar_mask = None
        self.logit_bias = torch.arange(vocab, dtype=torch.float32)[None, :].expand(batch_size, -1) / 100

    def __len__(self):
        return self.batch_size

    def apply_logits_bias(self, logits):
        if self.penalizer_orchestrator is not None:
            raise AssertionError("stale committed penalty state must not be applied")
        logits.add_(self.logit_bias)


def params(**updates):
    values = dict(sampling_seed=None, min_p=0, repetition_penalty=1.0,
                  min_new_tokens=0, top_k=-1, temperature=0.7,
                  frequency_penalty=0.0, presence_penalty=0.0)
    values.update(updates)
    return SimpleNamespace(**values)


def request(history=(), **updates):
    return SimpleNamespace(output_ids=list(history), sampling_params=params(**updates),
                           return_hidden_states=False)


class DFlashCorrectness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.overlay = SOURCE
        cls.original_source = (ORIGINAL / "sglang/srt/speculative/dflash_utils.py").read_text()
        cls.available = True
        cls.ns = dict(torch=torch, copy=copy,
                      is_dflash_sampling_verify_available=lambda: cls.available,
                      apply_custom_logit_processor=Mock(), get_parallel=lambda: SimpleNamespace(tp_size=8, pp_size=1), get_spec=lambda: SimpleNamespace(speculative_num_draft_tokens=5, speculative_use_block_verification=False), get_exec=lambda: SimpleNamespace(kernel=SimpleNamespace(enable_nvidia_megakernel=False)))
        functions((cls.overlay / "sglang/srt/speculative/dflash_utils.py").read_text(),
                  ["apply_dflash_output_penalties", "apply_dflash_verify_logits_adjustments", "validate_dflash_request"], cls.ns)
        functions((cls.overlay / "sglang/srt/speculative/dflash_worker_v2.py").read_text(),
                  ["_validate_phase1_sampling_support"], cls.ns)

    @unittest.skipIf(torch is None, "torch required for actual tensor execution")
    def test_sequential_logits_oracle(self):
        generator = torch.Generator().manual_seed(91)
        for bs in (1, 3):
            for block in (1, 2, 5, 8):
                for freq, presence in ((0.7, 0), (0, 1.3), (-0.7, -1.3), (0.7, 1.3)):
                    with self.subTest(bs=bs, block=block, frequency=freq, presence=presence):
                        vocab = 11
                        reqs = [request([1, 1, 3, row % vocab], frequency_penalty=freq if row != 1 else 0,
                                        presence_penalty=presence if row != 1 else 0) for row in range(bs)]
                        candidates = torch.randint(vocab, (bs, block), generator=generator)
                        candidates[:, 0] = torch.tensor([r.output_ids[-1] for r in reqs])
                        if block > 2:
                            candidates[:, 1:3] = 4  # repeated new token, no duplicate presence penalty
                        raw = torch.randn(bs * block, vocab, generator=generator)
                        actual = raw.clone()
                        info = SamplingInfo(bs, vocab)
                        expected = raw.view(bs, block, vocab).clone()
                        for row, req in enumerate(reqs):
                            history = req.output_ids[:]
                            for slot in range(block):
                                if slot:
                                    history.append(int(candidates[row, slot]))
                                counts = torch.tensor([history.count(token) for token in range(vocab)])
                                expected[row, slot] += info.logit_bias[row]
                                expected[row, slot] -= counts * req.sampling_params.frequency_penalty
                                expected[row, slot] -= (counts > 0) * req.sampling_params.presence_penalty
                        before = [r.output_ids[:] for r in reqs]
                        self.ns["apply_dflash_output_penalties"](next_token_logits=actual, candidates=candidates, sampling_info=info, reqs=reqs)
                        torch.testing.assert_close(actual.view_as(expected), expected, atol=2e-6, rtol=1e-6)
                        self.assertEqual(before, [r.output_ids for r in reqs])
                        self.assertIsNotNone(info.penalizer_orchestrator)
                        self.assertTrue(torch.all(info.acc_linear_penalties == 100))

    @unittest.skipIf(torch is None, "torch required for actual tensor execution")
    def test_original_negative_control(self):
        # Execute the original pinned helper, not a source-text approximation.
        original_ns = dict(torch=torch, apply_custom_logit_processor=Mock())
        functions(self.original_source, ["apply_dflash_verify_logits_adjustments"], original_ns)
        info = SamplingInfo(1, 2)
        info.logit_bias.zero_()
        info.penalizer_orchestrator = None
        info.acc_linear_penalties = torch.tensor([[0., -1.]])
        baseline = torch.zeros(2, 2)
        original_ns["apply_dflash_verify_logits_adjustments"](
            next_token_logits=baseline, sampling_info=info, draft_token_num=2)
        actual = torch.zeros(2, 2)
        self.ns["apply_dflash_output_penalties"](
            next_token_logits=actual, candidates=torch.tensor([[1, 0]]),
            sampling_info=info, reqs=[request([1], frequency_penalty=1.0)])
        self.assertAlmostEqual(actual[1].softmax(0)[0].item(), 0.5, places=6)
        self.assertAlmostEqual(baseline[1].softmax(0)[0].item(), .7310586, places=6)

    @unittest.skipIf(torch is None, "torch required for actual tensor execution")
    def test_history_refresh_after_committed_block(self):
        req = request([2], frequency_penalty=.7, presence_penalty=-.4)
        info = SamplingInfo(1, 4)
        info.logit_bias.zero_()
        for committed in ([1, 1, 3], [0], [3, 3]):
            req.output_ids.extend(committed)
            logits = torch.zeros(1, 4)
            self.ns["apply_dflash_output_penalties"](
                next_token_logits=logits,
                candidates=torch.tensor([[req.output_ids[-1]]]),
                sampling_info=info, reqs=[req])
            counts = torch.tensor([req.output_ids.count(token) for token in range(4)])
            torch.testing.assert_close(logits[0], -.7 * counts + .4 * (counts > 0))

    def test_default_fast_path(self):
        original = self.ns["apply_dflash_verify_logits_adjustments"]
        sentinel = Mock()
        self.ns["apply_dflash_verify_logits_adjustments"] = sentinel
        try:
            self.ns["apply_dflash_output_penalties"](next_token_logits=object(),
                candidates=SimpleNamespace(shape=(1, 5)), sampling_info=object(), reqs=[request()])
            sentinel.assert_called_once()
        finally:
            self.ns["apply_dflash_verify_logits_adjustments"] = original

    def test_request_guards(self):
        validate = self.ns["validate_dflash_request"]
        self.assertIsNone(validate(request(), True))
        for field, value in (("sampling_seed", 0), ("min_p", .1), ("repetition_penalty", 1.1), ("min_new_tokens", 1)):
            with self.subTest(field=field):
                self.assertIsNotNone(validate(request(**{field: value}), field == "sampling_seed"))
        for field in ("frequency_penalty", "presence_penalty"):
            self.assertIsNotNone(validate(request(**{field: .5}), True))
            self.assertIsNone(validate(request(**{field: .5}), False))
        type(self).available = False
        try:
            self.assertIsNotNone(validate(request(), False))
            self.assertIsNone(validate(request(temperature=0), False))
        finally:
            type(self).available = True

    def test_runtime_no_silent_greedy_fallback(self):
        validate = self.ns["_validate_phase1_sampling_support"]
        batch = SimpleNamespace(reqs=[request()], sampling_info=SimpleNamespace(is_all_greedy=False))
        worker = SimpleNamespace(selector=object(), _selector_sampling_enabled=False,
                                 lilicorr=None, _lilicorr_sampling_enabled=False)
        with self.assertRaisesRegex(RuntimeError, "greedy"):
            validate(worker, batch)
        worker._selector_sampling_enabled = True
        validate(worker, batch)
        worker.selector = None
        type(self).available = False
        try:
            with self.assertRaisesRegex(RuntimeError, "greedy"):
                validate(worker, batch)
            batch.sampling_info.is_all_greedy = True
            validate(worker, batch)
        finally:
            type(self).available = True


class BaselineSeedCorrectness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        overlay = SOURCE
        cls.sampling_source = (overlay / "sglang/srt/sampling/sampling_batch_info.py").read_text()
        cls.sampler_source = (overlay / "sglang/srt/layers/sampler.py").read_text()
        cls.ns = dict(torch=torch, get_exec=lambda: SimpleNamespace(kernel=SimpleNamespace(sampling_backend="flashinfer")),
                      murmur_hash32=cls.cpu_hash_reference)
        functions(cls.sampler_source, ["multinomial_with_seed", "top_k_top_p_min_p_sampling_from_probs_torch", "_sample_from_probs"], cls.ns)

    @staticmethod
    def cpu_hash_reference(seeds, positions, columns):
        # CPU reference of unchanged pinned Triton MurmurHash32. GPU hash kernel
        # execution is outside these CPU tests and remains a rollout requirement.
        mask = 0xffffffff
        def rotate(x, bits):
            return ((x << bits) | (x >> (32 - bits))) & mask
        def mix(h, k):
            k = (k * 0xcc9e2d51) & mask
            k = rotate(k, 15)
            k = (k * 0x1b873593) & mask
            return ((rotate(h ^ k, 13) * 5) + 0xe6546b64) & mask
        result = []
        for seed, pos in zip(seeds.tolist(), positions.tolist()):
            row = []
            for column in columns.tolist():
                h = 0
                for value in (seed & mask, (seed >> 32) & mask, pos & mask, column):
                    h = mix(h, value)
                h ^= 16
                h ^= h >> 16
                h = (h * 0x85ebca6b) & mask
                h ^= h >> 13
                h = (h * 0xc2b2ae35) & mask
                h ^= h >> 16
                row.append(h)
            result.append(row)
        return torch.tensor(result, dtype=torch.uint32)

    def test_explicit_seed_without_global_determinism(self):
        tree = ast.parse(self.sampling_source)
        method = next(n for c in tree.body if isinstance(c, ast.ClassDef) for n in c.body
                      if isinstance(n, ast.FunctionDef) and n.name == "from_schedule_batch")
        prefix = []
        for node in method.body:
            prefix.append(node)
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "sampling_seed" for t in node.targets):
                break
        method.body = prefix + [ast.Return(value=ast.Name(id="sampling_seed", ctx=ast.Load()))]
        method.decorator_list = []
        ns = dict(torch=torch, is_pin_memory_available=lambda device: False,
                  get_exec=lambda: SimpleNamespace(deterministic=SimpleNamespace(enable_deterministic_inference=False)))
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), "<pinned-seed-construction>", "exec", flags=__import__("__future__").annotations.compiler_flag), ns)
        reqs = [request(sampling_seed=0), request(sampling_seed=17), request()]
        for req in reqs:
            req.sampling_params.top_p = .95
        result = ns["from_schedule_batch"](None, SimpleNamespace(reqs=reqs, device="cpu"), 4)
        self.assertEqual(result.tolist(), [0, 17, -1])
        self.assertIsNone(ns["from_schedule_batch"](None, SimpleNamespace(reqs=reqs[2:], device="cpu"), 4))

    def test_seeded_top_p_routes_around_flashinfer(self):
        info = SimpleNamespace(sampling_mask_batch_indices=None, sampling_seed=torch.tensor([7, -1]),
                               top_ks=torch.tensor([4, 4]), top_ps=torch.tensor([.8, .8]),
                               min_ps=torch.zeros(2), need_min_p_sampling=False, max_top_k=None)
        probs = torch.tensor([[.4, .3, .2, .1], [.4, .3, .2, .1]])
        sampled, capture = self.ns["_sample_from_probs"](SimpleNamespace(), probs, info, torch.tensor([10, 10]), False)
        self.assertEqual(sampled.shape, (2,))
        self.assertIsNone(capture)

    def test_seed_repeatability_and_batch_composition(self):
        draw = self.ns["multinomial_with_seed"]
        logits = torch.tensor([[-.2, -.5, -1., -3.]])
        for seed in (0, 77, 9_007_199_254_740_991):
            first = draw(logits, torch.tensor([seed]), torch.tensor([12]))
            torch.manual_seed(998)
            second = draw(logits, torch.tensor([seed]), torch.tensor([12]))
            self.assertEqual(first.item(), second.item())
        reference = draw(logits, torch.tensor([77]), torch.tensor([12]))
        for global_seed in range(12):
            torch.manual_seed(global_seed)
            mixed = draw(logits.expand(3, -1), torch.tensor([-1, 77, 0]), torch.tensor([12, 12, 12]))
            self.assertEqual(mixed[1].item(), reference.item())
        draws = [draw(logits, torch.tensor([-1]), torch.tensor([12])).item() for _ in range(50)]
        self.assertGreater(len(set(draws)), 1)

    def test_mixed_merge_and_filter_seed_alignment(self):
        tree = ast.parse(self.sampling_source)
        method = next(n for c in tree.body if isinstance(c, ast.ClassDef) for n in c.body
                      if isinstance(n, ast.FunctionDef) and n.name == "merge_batch")
        # Execute the actual new seed-normalization block and existing tensor
        # merge loop in isolation from unrelated grammar/penalty state.
        selected = [node for node in method.body if
                    (isinstance(node, ast.If) and "self.sampling_seed is not None or" in ast.unparse(node.test))
                    or (isinstance(node, ast.For) and isinstance(node.iter, ast.List)
                        and any(isinstance(v, ast.Constant) and v.value == "sampling_seed" for v in node.iter.elts))]
        self.assertEqual(len(selected), 2)
        method.body = selected
        method.decorator_list = []
        ns = dict(torch=torch)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), "<pinned-seed-merge>", "exec", flags=__import__("__future__").annotations.compiler_flag), ns)
        class Batch:
            device = "cpu"
            def __init__(self, seed, length):
                self.sampling_seed = seed
                self.temperatures = torch.ones(length, 1)
            def __len__(self):
                return self.temperatures.shape[0]
        for reverse in (False, True):
            seeded, ordinary = Batch(torch.tensor([0, 13]), 2), Batch(None, 1)
            first, second = (ordinary, seeded) if reverse else (seeded, ordinary)
            ns["merge_batch"](first, second)
            expected = [-1, 0, 13] if reverse else [0, 13, -1]
            self.assertEqual(first.sampling_seed.tolist(), expected)
            self.assertEqual(first.sampling_seed[torch.tensor([2, 0])].tolist(), [expected[2], expected[0]])


class TensorPointer:
    def __init__(self, tensor, offset=0):
        self.tensor = tensor.reshape(-1)
        self.offset = offset

    def __add__(self, offset):
        return TensorPointer(self.tensor, self.offset + offset)

    __radd__ = __add__


class TritonCPU:
    """Small CPU memory interpreter for the actual pinned rejection kernel.

    Exercises numerical branches and pointer strides; does not simulate GPU
    compiler behavior, parallel reductions or graph capture.
    """
    int32 = torch.int32 if torch is not None else None
    program = 0

    @classmethod
    def program_id(cls, dimension):
        return cls.program

    @staticmethod
    def load(pointer, mask=None, other=0):
        offset = torch.as_tensor(pointer.offset).long()
        if mask is None:
            return pointer.tensor[offset]
        valid = torch.as_tensor(mask)
        safe = torch.where(valid, offset, torch.zeros_like(offset))
        return torch.where(valid, pointer.tensor[safe], torch.as_tensor(other))

    @staticmethod
    def store(pointer, value):
        pointer.tensor[pointer.offset] = value

    @staticmethod
    def where(condition, yes, no):
        return torch.where(torch.as_tensor(condition), torch.as_tensor(yes), torch.as_tensor(no))

    arange = staticmethod(lambda start, stop: torch.arange(start, stop))
    sum = staticmethod(lambda value, axis=None: value.sum(dim=axis))
    max = staticmethod(lambda value, axis=None: value.max() if axis is None else value.max(dim=axis).values)
    argmax = staticmethod(lambda value, axis=0: value.argmax(dim=axis))
    cumsum = staticmethod(lambda value, axis: value.cumsum(dim=axis))
    maximum = staticmethod(lambda a, b: torch.maximum(torch.as_tensor(a), torch.as_tensor(b)))
    minimum = staticmethod(lambda a, b: torch.minimum(torch.as_tensor(a), torch.as_tensor(b)))
    static_range = staticmethod(range)


class DFlashSeedCorrectness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        overlay = SOURCE
        cls.ns = dict(torch=torch, tl=TritonCPU,
                      is_dflash_sampling_verify_available=lambda: True,
                      megakernel_enabled=lambda: cls.megakernel)
        cls.megakernel = False
        helper_source = (overlay / "sglang/srt/speculative/seeded_dflash.py").read_text()
        helper_names = ["_dflash_mul32", "seeded_dflash_uniforms"]
        if any(isinstance(node, ast.FunctionDef) and node.name == "seeded_dflash_uniforms_reference"
               for node in ast.parse(helper_source).body):
            helper_names.append("seeded_dflash_uniforms_reference")
        functions(helper_source, helper_names, cls.ns)
        functions((overlay / "sglang/kernels/ops/speculative/reject_sampling.py").read_text(),
                  ["speculative_sampling_classic_kernel"], cls.ns)
        functions((overlay / "sglang/srt/speculative/dflash_worker_v2.py").read_text(),
                  ["_validate_phase1_sampling_support", "_graph_proposal_unusable", "forward_batch_generation"], cls.ns)
        cls.utils_source = (SOURCE / "sglang/srt/speculative/dflash_utils.py").read_text()
        cls.accept_source = (overlay / "sglang/kernels/ops/speculative/dspark/dspark_accept.py").read_text()
        cls.kernel_source = (overlay / "sglang/kernels/ops/speculative/reject_sampling.py").read_text()
        cls.ns["F"] = torch.nn.functional
        functions((SOURCE / "sglang/srt/models/dflash.py").read_text(), ["_follow_maps", "sample_path"], cls.ns)

    @staticmethod
    def scalar_philox(seed, position, stream):
        mask = 0xffffffff
        c0, c1, c2, c3 = position & mask, (position >> 32) & mask, stream, 0
        k0, k1 = seed & mask, (seed >> 32) & mask
        for _ in range(10):
            a, b = c0 * 0xd2511f53, c2 * 0xcd9e8d57
            c0, c1, c2, c3 = (b >> 32) ^ c1 ^ k0, b & mask, (a >> 32) ^ c3 ^ k1, a & mask
            k0, k1 = (k0 + 0x9e3779b9) & mask, (k1 + 0xbb67ae85) & mask
        return (c0 >> 8) * 2.0 ** -24

    def test_counter_philox_scalar_oracle_and_alignment(self):
        generate = self.ns["seeded_dflash_uniforms"]
        seeds = torch.tensor([0, 9_007_199_254_740_991, -1])
        positions = torch.tensor([11, (1 << 33) + 3, 7])
        stock = torch.full((3, 8), .123)
        for stream in (0, 1, 2):
            actual = generate(stock=stock, seeds=seeds, positions=positions, stream=stream)
            expected = stock.clone()
            for row in (0, 1):
                for slot in range(8):
                    expected[row, slot] = self.scalar_philox(int(seeds[row]), int(positions[row]) + slot, stream)
            torch.testing.assert_close(actual, expected, atol=0, rtol=0)
            tail = generate(stock=stock[:, 3:], seeds=seeds, positions=positions + 3, stream=stream)
            torch.testing.assert_close(tail, actual[:, 3:], atol=0, rtol=0)
            reordered = generate(stock=stock[[2, 0, 1]], seeds=seeds[[2, 0, 1]], positions=positions[[2, 0, 1]], stream=stream)
            torch.testing.assert_close(reordered, actual[[2, 0, 1]], atol=0, rtol=0)
        self.assertIs(generate(stock=stock, seeds=None, positions=None, stream=0), stock)

    def run_kernel(self, candidates, target, draft, uniforms, final):
        bs, block = candidates.shape
        vocab = target.shape[-1]
        predicts = torch.full((bs * block,), -1, dtype=torch.int64)
        indices = torch.full((bs, block), -1, dtype=torch.int64)
        lengths = torch.zeros(bs, dtype=torch.int32)
        retrieve = torch.arange(bs * block).view(bs, block)
        args = [TensorPointer(t) for t in (predicts, indices, lengths, candidates, retrieve, uniforms, final, target, draft)]
        strides = [*candidates.stride(), *retrieve.stride(), *uniforms.stride(),
                   final.stride(0), final.stride(1) if final.ndim == 2 else 0,
                   *target.stride(), *draft.stride()]
        for row in range(bs):
            TritonCPU.program = row
            self.ns["speculative_sampling_classic_kernel"](*args, *strides,
                NUM_SLOTS=block, VOCAB_SIZE=vocab, BLOCK_V=4, BLOCK_VERIFICATION=False)
        return lengths, predicts[indices[torch.arange(bs), lengths.long()]]

    def test_actual_selector_proposal_q_and_repeatability(self):
        sampler = self.ns["sample_path"]
        generate = self.ns["seeded_dflash_uniforms"]
        bs, gamma, topk = 3, 4, 4
        candidates = torch.arange(topk).expand(bs, gamma, topk).contiguous()
        scores = torch.randn(bs, gamma, topk, topk, generator=torch.Generator().manual_seed(51))
        temperatures = torch.tensor([.4, 1., 1.8])
        greedy = torch.tensor([False, False, True])
        seeds, positions = torch.tensor([0, 42, 9_007_199_254_740_991]), torch.tensor([5, 17, 29])
        uniforms = generate(stock=torch.rand(bs, gamma), seeds=seeds, positions=positions, stream=0)
        tokens, q = sampler(SimpleNamespace(top_k=topk), candidate_ids=candidates, scores=scores,
                            uniforms=uniforms, temperatures=temperatures, greedy_mask=greedy)
        changed_stock = generate(stock=torch.rand(bs, gamma), seeds=seeds, positions=positions, stream=0)
        tokens_again, q_again = sampler(SimpleNamespace(top_k=topk), candidate_ids=candidates, scores=scores,
                                        uniforms=changed_stock, temperatures=temperatures, greedy_mask=greedy)
        torch.testing.assert_close(tokens, tokens_again)
        torch.testing.assert_close(q, q_again)
        for row in range(bs):
            for slot in range(gamma):
                predecessor = 0 if slot == 0 else int(tokens[row, slot - 1])
                if greedy[row]:
                    expected = torch.nn.functional.one_hot(tokens[row, slot], topk).float()
                else:
                    expected = torch.softmax(scores[row, slot, predecessor] / temperatures[row], -1)
                torch.testing.assert_close(q[row, slot], expected)

    def test_actual_kernel_final_position_and_stock_stride(self):
        candidates = torch.tensor([[2, 0, 1], [2, 0, 1]])
        target = torch.tensor([[[.8, .1, .1], [.45, .1, .45], [.1, .8, .1]]]).expand(2, -1, -1).contiguous()
        draft = torch.tensor([[[.5, .3, .2], [.1, .8, .1]]]).expand(2, -1, -1).contiguous()
        accept = torch.tensor([[.1, .9], [.1, .9]])
        final = torch.tensor([[.01, .99, .2], [.99, .01, .8]])
        length, bonus = self.run_kernel(candidates, target, draft, accept, final)
        self.assertEqual(length.tolist(), [1, 1])
        self.assertEqual(bonus.tolist(), [2, 0])
        # 1D final input preserves the exact stock layout/behavior.
        length_stock, bonus_stock = self.run_kernel(candidates, target, draft, accept, final[:, 1].contiguous())
        torch.testing.assert_close(length_stock, length)
        torch.testing.assert_close(bonus_stock, bonus)

    def test_actual_kernel_sequential_oracle_varied_shapes(self):
        rng = torch.Generator().manual_seed(661)
        for block in (1, 2, 5, 8):
            for vocab in (3, 7, 11):
                bs = 9
                p = torch.rand(bs, block, vocab, generator=rng)
                p /= p.sum(-1, keepdim=True)
                q = torch.rand(bs, block - 1, vocab, generator=rng)
                q /= q.sum(-1, keepdim=True)
                candidates = torch.randint(vocab, (bs, block), generator=rng)
                uniforms = torch.rand(bs, block - 1, generator=rng)
                finals = torch.rand(bs, block, generator=rng)
                expected_lengths, expected_bonus = [], []
                for row in range(bs):
                    accepted = 0
                    while accepted < block - 1:
                        token = candidates[row, accepted + 1]
                        if uniforms[row, accepted] * q[row, accepted, token] >= p[row, accepted, token]:
                            break
                        accepted += 1
                    weights = p[row, accepted].clone()
                    if accepted < block - 1:
                        weights = (weights - q[row, accepted]).clamp_min(0)
                    threshold = finals[row, accepted] * weights.sum()
                    bonus = int(torch.searchsorted(weights.cumsum(0), threshold, right=True))
                    expected_lengths.append(accepted)
                    expected_bonus.append(min(bonus, vocab - 1))
                lengths, bonus = self.run_kernel(candidates, p, q, uniforms, finals)
                self.assertEqual(lengths.tolist(), expected_lengths)
                self.assertEqual(bonus.tolist(), expected_bonus)

    def test_actual_kernel_q_corrected_target_marginal(self):
        # Synthetic, source-executed rejection sampler law test over independent
        # explicit seeds. Proposal q differs strongly from target p.
        count = 4096
        seeds = torch.arange(count)
        positions = torch.full((count,), 100)
        generate = self.ns["seeded_dflash_uniforms"]
        q = torch.tensor([.7, .2, .1])
        p = torch.tensor([.15, .3, .55])
        proposal = generate(stock=torch.zeros(count, 1), seeds=seeds, positions=positions, stream=0)
        tokens = (proposal >= q.cumsum(0)).sum(1).clamp_max(2)
        candidates = torch.stack((torch.full_like(tokens, 2), tokens), dim=1)
        accept = generate(stock=torch.zeros(count, 1), seeds=seeds, positions=positions, stream=1)
        final = generate(stock=torch.zeros(count, 2), seeds=seeds, positions=positions, stream=2)
        target = p.expand(count, 2, 3).contiguous()
        draft = q.expand(count, 1, 3).contiguous()
        lengths, bonus = self.run_kernel(candidates, target, draft, accept, final)
        first = torch.where(lengths > 0, tokens, bonus)
        observed = torch.bincount(first, minlength=3).float() / count
        torch.testing.assert_close(observed, p, atol=.035, rtol=0)
        self.assertLess(abs(float((lengths > 0).float().mean()) - float(torch.minimum(p, q).sum())), .035)

    def test_actual_accept_core_and_kernel_wrapper_wiring(self):
        ns = dict(self.ns)
        actual_kernel = ns["speculative_sampling_classic_kernel"]
        class Launch:
            def __getitem__(self, grid):
                def invoke(*args, num_warps=None, **kwargs):
                    pointers = [TensorPointer(t) for t in args[:9]]
                    for row in range(grid[0]):
                        TritonCPU.program = row
                        actual_kernel(*pointers, *args[9:], **kwargs)
                return invoke
        ns.update(speculative_sampling_classic_kernel=Launch(),
                  triton=SimpleNamespace(next_power_of_2=lambda n: 1 << (n - 1).bit_length()),
                  _is_npu=False, _DFLASH_CHAIN_VERIFY_BUFFERS={},
                  SoftmaxTemp=SimpleNamespace(execute=lambda logits, temperatures, rows_per_request:
                      torch.softmax(logits / temperatures.repeat_interleave(rows_per_request, 0), -1)))
        functions(self.utils_source, ["_get_or_create_chain_verify_buffers"], ns)
        functions(self.kernel_source, ["chain_speculative_sampling_triton"], ns)
        functions(self.accept_source, ["_accept_sampling_core", "accept_sampling"], ns)
        candidates = torch.tensor([[2, 0, 1], [2, 1, 0], [1, 2, 0]])
        logits = torch.tensor([[1., 2., 3.]]).expand(9, -1).contiguous()
        target = torch.softmax(logits, -1).reshape(3, 3, 3)
        draft = torch.tensor([.5, .3, .2]).expand(3, 2, 3).contiguous()
        seeds, positions = torch.tensor([0, -1, 23]), torch.tensor([11, 17, 19])
        accept_stock, final_stock = torch.full((3, 2), .35), torch.full((3, 3), .4)
        generate = ns["seeded_dflash_uniforms"]
        uniforms = generate(stock=accept_stock, seeds=seeds, positions=positions, stream=1)
        finals = generate(stock=final_stock, seeds=seeds, positions=positions, stream=2)
        expected_length, expected_bonus = self.run_kernel(candidates, target, draft, uniforms, finals)
        info = SimpleNamespace(sampling_seed=seeds, dflash_seed_positions=positions,
                               need_top_k_sampling=False, need_top_p_sampling=False,
                               temperatures=torch.ones(3, 1))
        with __import__("unittest.mock", fromlist=["patch"]).patch.object(
                torch, "rand", side_effect=[accept_stock, torch.zeros(3), final_stock]):
            length, bonus, cap = ns["accept_sampling"](
                candidates=candidates, target_logits=logits, draft_probs=draft,
                sampling_info=info, draft_input=object(), gamma=2, verify_num_draft_tokens=3)
        torch.testing.assert_close(length, expected_length)
        torch.testing.assert_close(bonus, expected_bonus)
        self.assertEqual(cap.tolist(), [0, 0, 0])

    def test_seed_guards_run_before_target_prefill_sampling(self):
        class SamplingReached(Exception):
            pass
        target = Mock()
        target.forward_batch_generation.side_effect = SamplingReached
        worker = SimpleNamespace(_hosts_draft=True, _block_verification=False,
                                 selector=object(), _selector_sampling_enabled=True,
                                 lilicorr=None, _lilicorr_sampling_enabled=False,
                                 target_worker=target, _join_aux=Mock(),
                                 _wait_for_fused_hicache_load=Mock())
        worker._validate_phase1_sampling_support = lambda batch: self.ns["_validate_phase1_sampling_support"](worker, batch)
        info = SimpleNamespace(is_all_greedy=False, sampling_seed=torch.tensor([0]))
        batch = SimpleNamespace(reqs=[request(sampling_seed=0)], sampling_info=info,
                                forward_mode=SimpleNamespace(is_extend=lambda: True),
                                is_extend_in_batch=False)
        self.ns["CaptureHiddenMode"] = SimpleNamespace(FULL="full")
        with self.assertRaises(SamplingReached):
            self.ns["forward_batch_generation"](worker, batch)
        target.forward_batch_generation.assert_called_once()
        target.reset_mock()
        for field, bad_value in (("_block_verification", True), ("selector", None),
                                 ("_selector_sampling_enabled", False)):
            old_value = getattr(worker, field)
            try:
                setattr(worker, field, bad_value)
                with self.assertRaises(RuntimeError):
                    self.ns["forward_batch_generation"](worker, batch)
                target.forward_batch_generation.assert_not_called()
            finally:
                setattr(worker, field, old_value)
        info.sampling_seed = None
        with self.assertRaisesRegex(RuntimeError, "materialized"):
            self.ns["forward_batch_generation"](worker, batch)
        target.forward_batch_generation.assert_not_called()

    def test_runtime_variant_rejects_and_seed_guard_retained(self):
        validate = self.ns["_validate_phase1_sampling_support"]
        batch = SimpleNamespace(reqs=[request(sampling_seed=0)], sampling_info=SimpleNamespace(is_all_greedy=False, sampling_seed=torch.tensor([0])))
        worker = SimpleNamespace(_block_verification=False, selector=object(), _selector_sampling_enabled=True,
                                 lilicorr=None, _lilicorr_sampling_enabled=False)
        validate(worker, batch)
        worker._block_verification = True
        with self.assertRaisesRegex(RuntimeError, "sequential"):
            validate(worker, batch)
        worker._block_verification = False
        type(self).megakernel = True
        try:
            with self.assertRaisesRegex(RuntimeError, "megakernel"):
                validate(worker, batch)
        finally:
            type(self).megakernel = False
        worker.selector = None
        with self.assertRaisesRegex(RuntimeError, "DFlash2"):
            validate(worker, batch)
        # The original correctness layer remains immutable and rejects seed;
        # the bounded final admission layer is exercised by its own tests.
        guarded = (PATCHES / "dflash-prefix-penalties.patch").read_text()
        self.assertIn("params.sampling_seed is not None", guarded)
        self.assertTrue(self.ns["_graph_proposal_unusable"](object(), SimpleNamespace(sampling_seed=torch.tensor([0]))))


class DFlashExperimentAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target = SOURCE / "sglang/srt/speculative/dflash_utils.py"
        cls.geometry = SimpleNamespace(tp_size=8, pp_size=1, dcp_size=8, ep_size=2)
        cls.spec = SimpleNamespace(speculative_num_draft_tokens=5, speculative_use_block_verification=False)
        cls.kernel = SimpleNamespace(enable_nvidia_megakernel=False)
        cls.available = True
        cls.ns = dict(get_parallel=lambda: cls.geometry, get_spec=lambda: cls.spec,
                      get_exec=lambda: SimpleNamespace(kernel=cls.kernel),
                      is_dflash_sampling_verify_available=lambda: cls.available)
        functions(target.read_text(), ["validate_dflash_request"], cls.ns)

    def test_valid_seed_admission_b5_b8_and_dcp8ep2(self):
        for block in (5, 8):
            self.spec.speculative_num_draft_tokens = block
            for seed in (0, 9_007_199_254_740_991):
                self.assertIsNone(self.ns["validate_dflash_request"](request(sampling_seed=seed), False))
        self.spec.speculative_num_draft_tokens = 5

    def test_unsafe_geometry_rejected_unseeded_unchanged(self):
        validate = self.ns["validate_dflash_request"]
        seeded = request(sampling_seed=0)
        self.assertIsNotNone(validate(seeded, True))
        for obj, field, value in ((self.geometry, "tp_size", 4), (self.geometry, "pp_size", 2),
                                  (self.spec, "speculative_num_draft_tokens", 3),
                                  (self.spec, "speculative_use_block_verification", True),
                                  (self.kernel, "enable_nvidia_megakernel", True)):
            old = getattr(obj, field)
            try:
                setattr(obj, field, value)
                self.assertIsNotNone(validate(seeded, False))
                self.assertIsNone(validate(request(), True))
            finally:
                setattr(obj, field, old)
        type(self).available = False
        try:
            self.assertIsNotNone(validate(request(sampling_seed=0, temperature=0), False))
        finally:
            type(self).available = True
        for field, value in (("min_p", .1), ("repetition_penalty", 1.1), ("min_new_tokens", 1)):
            self.assertIsNotNone(validate(request(sampling_seed=0, **{field: value}), False))
        self.assertIsNone(validate(request(sampling_seed=0, frequency_penalty=.7, presence_penalty=-.4), False))


if __name__ == "__main__":
    unittest.main()
