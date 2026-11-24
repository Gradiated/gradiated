from typing import Iterable, Tuple
import torch
from sglang.srt.models.qwen3_5_text import Qwen3_5ForCausalLM

# JevK5 names its weights model.language_model.*, as Qwen3.5's vision-language checkpoints do, but declares the
# text-only class, whose loader then matches none of them and leaves every layer uninitialised.
VL_PREFIX = 'model.language_model.'


class JevK5ForCausalLM(Qwen3_5ForCausalLM):
    def load_weights(self, weights: Iterable[Tuple[str, torch.Tensor]]):
        def renamed():
            for name, weight in weights:
                yield ('model.' + name[len(VL_PREFIX):] if name.startswith(VL_PREFIX) else name), weight

        loaded = set(super().load_weights(renamed()))
        missing = sorted(set(dict(self.named_parameters())) - loaded)
        if missing:
            raise RuntimeError(f'JevK5 left {len(missing)} parameters unloaded, such as {missing[:3]}')
        return loaded


EntryClass = JevK5ForCausalLM
