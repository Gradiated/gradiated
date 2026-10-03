"""Numerical regression for the pinned MLA LoRA backport.

The CPU bundle check runs the same float32 oracle. Set
GRADIATED_GLM_LORA_GPU_TEST=1 on a reserved GPU to also check Triton and graph replay.
"""

import os
import unittest
from types import MethodType, SimpleNamespace
from unittest import mock

try:
    import torch
    from vllm.lora.ops.triton_ops.mla_kv_b_lora import (
        mla_kv_b_lora_linear,
        mla_kv_b_lora_q,
        mla_kv_b_lora_v,
    )
except ImportError:
    if os.environ.get("GRADIATED_REQUIRE_GLM_LORA") == "1":
        raise
    torch = None


@unittest.skipIf(torch is None, "requires the pinned GLM runtime bundle")
class MLALoraTests(unittest.TestCase):
    def test_materialized_kv_applies_one_delta_with_base_or_wrapped_projection(self):
        from vllm.model_executor.layers.attention.sparse_mla_attention import (
            SparseMLACommonImpl,
        )

        device = (
            "cuda" if os.environ.get("GRADIATED_GLM_LORA_GPU_TEST") == "1" else "cpu"
        )
        x = torch.ones(4, 3, device=device)
        weight = torch.ones(4, 3, device=device)
        mapping = torch.tensor([-1, 0, -1, 0], device=device)
        delta = torch.where((mapping >= 0)[:, None], 2.0, 0.0).expand(-1, 4)

        def base_projection(value):
            return value @ weight.T, None

        wrapped = mock.Mock(
            side_effect=lambda value: (base_projection(value)[0] + delta, None)
        )
        wrapped.base_layer = base_projection
        correction = SimpleNamespace(
            apply_mla_kv_b_lora_linear=lambda value, output, indices: output.add_(
                delta.view_as(output)
            )
        )
        expected = (base_projection(x)[0] + delta).view(4, 1, 4)
        for projection in [base_projection, wrapped]:
            backend = SimpleNamespace(
                kv_b_proj=projection,
                num_heads=1,
                qk_nope_head_dim=2,
                v_head_dim=2,
                _concat_k_nope_k_pe=lambda k, pe: k,
            )
            k, v = SparseMLACommonImpl._project_kv(
                backend, x, torch.empty(4, 1, 0, device=device), correction, mapping
            )
            torch.testing.assert_close(
                torch.cat([k, v], dim=-1), expected, rtol=0, atol=0
            )
        wrapped.assert_not_called()

    @unittest.skipUnless(
        os.environ.get("GRADIATED_GLM_LORA_GPU_TEST") == "1",
        "requires CUDA opaque custom-op dispatch",
    )
    def test_opaque_cuda_dispatch_preserves_layer_lora_state(self):
        from vllm.model_executor.layers.attention import mla_attention as mla
        from vllm.platforms import current_platform

        self.assertTrue(current_platform.opaque_attention_op())
        mapping = torch.tensor([-1, 0, 1, 0], device="cuda")
        projection = SimpleNamespace(
            punica_wrapper=SimpleNamespace(token_lora_indices=mapping),
            apply_mla_kv_b_lora_q=mock.Mock(),
            apply_mla_kv_b_lora_v=mock.Mock(),
        )
        layer = SimpleNamespace(
            kv_b_proj=projection,
            num_heads=1,
            v_head_dim=2,
            qk_nope_head_dim=2,
            qk_rope_head_dim=0,
            kv_lora_rank=3,
            kv_cache_dtype="auto",
            use_pcp=False,
            prefill_backend=None,
            q_pad_num_heads=None,
            is_aiter_triton_fp4_bmm_enabled=False,
            is_aiter_triton_fp8_bmm_enabled=False,
            is_amx_bmm_enabled=False,
            _k_scale=torch.ones((), device="cuda"),
            W_UK_T=torch.ones(1, 2, 3, device="cuda"),
            W_UV=torch.ones(1, 3, 2, device="cuda"),
        )
        for name in ["forward_impl", "_kv_b_proj_lora_mapping", "_v_up_proj"]:
            setattr(layer, name, MethodType(getattr(mla.MLAAttention, name), layer))
        mha = mock.Mock(side_effect=lambda *args, **kwargs: kwargs["output"].zero_())
        mqa = mock.Mock(return_value=(torch.ones(4, 1, 3, device="cuda"), None))
        layer.impl = SimpleNamespace(
            is_sparse=False, dcp_world_size=1, forward_mha=mha, forward_mqa=mqa
        )
        q = torch.ones(4, 1, 2, device="cuda")
        latent = torch.ones(4, 3, device="cuda")
        pe = torch.empty(4, 1, 0, device="cuda")
        cache = torch.empty(1, device="cuda")
        output = torch.empty(4, 2, device="cuda")
        for decode in [False, True]:
            metadata = SimpleNamespace(
                num_actual_tokens=4,
                num_decode_tokens=4 if decode else 0,
                num_decodes=4 if decode else 0,
                num_prefills=0 if decode else 1,
                decode=SimpleNamespace(),
            )
            with mock.patch.object(
                mla,
                "get_attention_context",
                return_value=(metadata, layer, cache, None),
            ):
                torch.ops.vllm.unified_mla_attention_with_output(
                    q, latent, pe, output, "qualification"
                )
            if decode:
                projection.apply_mla_kv_b_lora_q.assert_called_once()
                projection.apply_mla_kv_b_lora_v.assert_called_once()
                for operation in [
                    projection.apply_mla_kv_b_lora_q,
                    projection.apply_mla_kv_b_lora_v,
                ]:
                    self.assertTrue(torch.equal(operation.call_args.args[2], mapping))
            else:
                mha.assert_called_once()
                self.assertIs(mha.call_args.kwargs["kv_b_proj_lora"], projection)
                self.assertTrue(
                    torch.equal(mha.call_args.kwargs["token_lora_mapping"], mapping)
                )

    def test_full_projection_and_absorbed_corrections_match_float32_oracle(self):
        self.device = (
            "cuda" if os.environ.get("GRADIATED_GLM_LORA_GPU_TEST") == "1" else "cpu"
        )
        old_threads = torch.get_num_threads()
        torch.set_num_threads(1)
        self.addCleanup(torch.set_num_threads, old_threads)
        torch.manual_seed(42)
        if self.device == "cpu":
            dispatch = mock.patch(
                "vllm.lora.ops.triton_ops.routed_lora_matmul.current_platform.is_cuda_alike",
                return_value=False,
            )
            dispatch.start()
            self.addCleanup(dispatch.stop)
            from vllm.lora.ops.triton_ops.routed_lora_matmul import (
                _routed_lora_two_stage,
            )

            cpu_op = mock.patch(
                "vllm.lora.ops.triton_ops.mla_kv_b_lora.routed_lora_two_stage",
                _routed_lora_two_stage,
            )
            cpu_op.start()
            self.addCleanup(cpu_op.stop)
        for heads in [32, 16]:
            for rank in [2, 8]:
                tokens = 17
                latent = 512
                key = value = 256
                slots = 3
                mapping = torch.tensor(
                    [-1, 0, 1, 2, 0, -1, 2, 1, 0, 2, -1, 1, 2, 0, 1, -1, 2],
                    device=self.device,
                )
                a = (
                    torch.randn(
                        slots, 1, rank, latent, device=self.device, dtype=torch.bfloat16
                    )
                    * 0.01
                )
                b = (
                    torch.randn(
                        slots,
                        1,
                        heads * (key + value),
                        rank,
                        device=self.device,
                        dtype=torch.bfloat16,
                    )
                    * 0.01
                )
                no_lora = torch.tensor(False, device="cpu")
                x = torch.randn(
                    tokens, latent + 64, device=self.device, dtype=torch.bfloat16
                )[:, :latent]
                q = torch.randn(
                    tokens, heads, key, device=self.device, dtype=torch.bfloat16
                )
                z = torch.randn(
                    tokens, heads, latent, device=self.device, dtype=torch.bfloat16
                )
                dense = torch.randn(
                    tokens, heads, key + value, device=self.device, dtype=torch.bfloat16
                )
                query = torch.randn_like(z)
                values = torch.randn(
                    tokens, heads, value, device=self.device, dtype=torch.bfloat16
                )
                expected = [dense.clone(), query.clone(), values.clone()]
                bh = b[:, 0].view(slots, heads, key + value, rank)
                for i, slot in enumerate(mapping.tolist()):
                    if slot < 0:
                        continue
                    expected[0][i] = (
                        expected[0][i].float()
                        + (
                            x[i].float() @ a[slot, 0].float().T @ b[slot, 0].float().T
                        ).view(heads, key + value)
                    ).to(torch.bfloat16)
                    expected[1][i] = (
                        expected[1][i].float()
                        + torch.einsum(
                            "hp,hpr,rl->hl",
                            q[i].float(),
                            bh[slot, :, :key].float(),
                            a[slot, 0].float(),
                        )
                    ).to(torch.bfloat16)
                    expected[2][i] = (
                        expected[2][i].float()
                        + torch.einsum(
                            "hl,rl,hvr->hv",
                            z[i].float(),
                            a[slot, 0].float(),
                            bh[slot, :, key:].float(),
                        )
                    ).to(torch.bfloat16)
                mla_kv_b_lora_linear(x, a, b, dense, mapping, no_lora)
                mla_kv_b_lora_q(q, a, b, query, mapping, no_lora, value)
                mla_kv_b_lora_v(z, a, b, values, mapping, no_lora, key)
                errors = []
                for out, ref in zip([dense, query, values], expected):
                    torch.testing.assert_close(out, ref, rtol=0.01, atol=0.01)
                    errors.append(float((out.float() - ref.float()).abs().max()))
                    assert torch.equal(out[mapping < 0], ref[mapping < 0])
                if self.device == "cuda":
                    # Capture with no adapter, then replay with one: CPU flags must not bake residency.
                    mapping.fill_(-1)
                    no_lora.fill_(True)
                    snapshot = [t.clone() for t in [dense, query, values]]
                    graph = torch.cuda.CUDAGraph()
                    with torch.cuda.graph(graph):
                        mla_kv_b_lora_linear(x, a, b, dense, mapping, no_lora)
                        mla_kv_b_lora_q(q, a, b, query, mapping, no_lora, value)
                        mla_kv_b_lora_v(z, a, b, values, mapping, no_lora, key)
                    graph.replay()
                    torch.cuda.synchronize()
                    assert all(
                        torch.equal(t, r)
                        for t, r in zip([dense, query, values], snapshot)
                    )
                    mapping.fill_(1)
                    no_lora.fill_(False)
                    graph.replay()
                    torch.cuda.synchronize()
                    assert all(
                        not torch.equal(out, ref)
                        for out, ref in zip([dense, query, values], snapshot)
                    )


if __name__ == "__main__":
    unittest.main()
