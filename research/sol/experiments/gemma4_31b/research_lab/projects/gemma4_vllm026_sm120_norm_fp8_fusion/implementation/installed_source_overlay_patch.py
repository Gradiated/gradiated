#!/usr/bin/env python3
"""Apply the admitted fusion edits to an isolated installed-vLLM overlay."""

from __future__ import annotations

import sys
from pathlib import Path


def replace_once(path: Path, before: str, after: str) -> None:
    text = path.read_text()
    if text.count(before) != 1:
        raise RuntimeError(f"installed_source_context_mismatch:{path}")
    path.write_text(text.replace(before, after, 1))


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    cutlass = root / "model_executor/kernels/linear/scaled_mm/cutlass.py"
    replace_once(
        cutlass,
        "    kFp8StaticTensorSym,\n",
        "    kFp8DynamicTokenSym,\n    kFp8StaticTensorSym,\n",
    )
    replace_once(
        cutlass,
        '''    def input_quant_key(self) -> QuantKey | None:
        \"\"\"Only static per-tensor activation quantization is supported for external
        quantization.\"\"\"
        if self.config.activation_quant_key == kFp8StaticTensorSym:
            return kFp8StaticTensorSym
        return None
''',
        '''    def input_quant_key(self) -> QuantKey | None:
        \"\"\"Return activation layouts accepted by the unchanged CUTLASS GEMM.\"\"\"
        if self.config.activation_quant_key in (
            kFp8StaticTensorSym,
            kFp8DynamicTokenSym,
        ):
            return self.config.activation_quant_key
        return None
''',
    )
    activation = root / "model_executor/layers/fusion/quant_activation.py"
    replace_once(
        activation,
        "from vllm.model_executor.layers.quantization.utils.quant_utils import QuantKey\n",
        '''from vllm import _custom_ops as ops
from vllm import envs
from vllm.model_executor.layers.layernorm import RMSNorm
from vllm.model_executor.layers.quantization.utils.quant_utils import (
    QuantKey,
    kFp8DynamicTokenSym,
)
''',
    )
    replace_once(
        activation,
        "    return x\n",
        '''    return x


def rms_norm_to_fp8_linear(
    norm: RMSNorm,
    x: torch.Tensor,
    consumer: torch.nn.Module,
) -> "torch.Tensor | QuantizedActivation":
    quant_key = getattr(consumer, "input_quant_key", None)
    can_fuse = (
        quant_key == kFp8DynamicTokenSym
        and not envs.VLLM_BATCH_INVARIANT
        and norm.pass_weight
        and norm.variance_size_override is None
        and norm.weight.dtype == x.dtype
        and x.stride(-1) == 1
    )
    if not can_fuse:
        return norm(x)
    data, scale = ops.rms_norm_dynamic_per_token_quant(
        x, norm.weight.data, norm.variance_epsilon, quant_key.dtype
    )
    return QuantizedActivation(
        data=data,
        scale=scale,
        orig_dtype=x.dtype,
        orig_shape=x.shape,
        quant_key=quant_key,
    )
''',
    )
    fp8 = root / "model_executor/layers/quantization/online/fp8.py"
    replace_once(
        fp8,
        "from vllm.model_executor.layers.fused_moe import RoutedExperts\n",
        '''from vllm.model_executor.layers.fused_moe import RoutedExperts
from vllm.model_executor.layers.fusion.quant_activation import (
    expose_input_quant_key,
)
''',
    )
    replace_once(
        fp8,
        "        self.use_marlin = isinstance(self.fp8_linear, MarlinFP8ScaledMMLinearKernel)\n",
        '''        expose_input_quant_key(layer, self.fp8_linear)
        self.use_marlin = isinstance(self.fp8_linear, MarlinFP8ScaledMMLinearKernel)
''',
    )
    gemma = root / "model_executor/models/gemma4.py"
    replace_once(
        gemma,
        ")\nfrom vllm.model_executor.layers.layernorm import RMSNorm\n",
        ''')
from vllm.model_executor.layers.fusion.quant_activation import (
    rms_norm_to_fp8_linear,
)
from vllm.model_executor.layers.layernorm import RMSNorm
''',
    )
    replace_once(
        gemma,
        "        hidden_states = self.input_layernorm(residual)\n",
        '''        hidden_states = rms_norm_to_fp8_linear(
            self.input_layernorm,
            residual,
            self.self_attn.qkv_proj,
        )
''',
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
