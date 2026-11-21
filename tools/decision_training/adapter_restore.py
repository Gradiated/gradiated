"""Restore only exact LoRA parameter names; avoid PEFT's weight_proj key rewrite."""

import argparse
import json
import re


def saved_key(name):
    value, count = re.subn(r"\.(lora_[AB])\.default\.weight$", r".\1.weight", name)
    if count != 1:
        raise ValueError("unsupported trainable adapter parameter: " + name)
    return value


def restore_adapter(model, saved):
    import torch

    parameters = {}
    for name, parameter in model.named_parameters():
        if parameter.requires_grad:
            key = saved_key(name)
            if key in parameters:
                raise ValueError("duplicate canonical adapter parameter")
            parameters[key] = parameter
    if set(parameters) != set(saved):
        raise ValueError("adapter payload does not cover every trainable parameter")
    for key, parameter in parameters.items():
        if parameter.shape != saved[key].shape or parameter.dtype != saved[key].dtype:
            raise ValueError("adapter shape or dtype differs: " + key)
    with torch.no_grad():
        for key, parameter in parameters.items():
            parameter.copy_(saved[key].to(device=parameter.device))
    for key, parameter in parameters.items():
        if not torch.equal(parameter.detach().cpu(), saved[key].cpu()):
            raise ValueError("adapter restore is not bitwise exact: " + key)
    return {"adapter_tensors_restored": len(parameters), "bitwise_exact": True}


def main():
    parser = argparse.ArgumentParser(
        description="Exercise exact adapter restore on a real PEFT weight_proj module using CPU only"
    )
    parser.parse_args()
    import torch
    from peft import LoraConfig, get_peft_model, get_peft_model_state_dict

    class Tiny(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight_proj = torch.nn.Linear(5, 3, bias=False)
            self.config = {"model_type": "custom"}

        def forward(self, value):
            return self.weight_proj(value)

    def fresh():
        torch.manual_seed(17)
        return get_peft_model(
            Tiny().double(),
            LoraConfig(
                r=2, lora_alpha=4, target_modules=["weight_proj"], lora_dropout=0
            ),
        )

    original = fresh()
    with torch.no_grad():
        for parameter in original.parameters():
            if parameter.requires_grad:
                parameter.uniform_(-0.2, 0.2)
    inputs = torch.arange(15, dtype=torch.float64).reshape(3, 5) / 10
    expected = original(inputs)
    expected.square().mean().backward()
    gradients = {
        name: parameter.grad.clone()
        for name, parameter in original.named_parameters()
        if parameter.requires_grad
    }
    saved = {
        name: value.detach().clone()
        for name, value in get_peft_model_state_dict(
            original, save_embedding_layers=False
        ).items()
    }
    restored = fresh()
    result = restore_adapter(restored, saved)
    actual = restored(inputs)
    actual.square().mean().backward()
    delta = max(
        (parameter.grad - gradients[name]).abs().max().item()
        for name, parameter in restored.named_parameters()
        if parameter.requires_grad
    )
    assert torch.equal(expected, actual) and delta == 0
    print(
        json.dumps(
            {
                **result,
                "cpu_weight_proj_logits_delta": 0.0,
                "cpu_weight_proj_gradient_delta": delta,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
