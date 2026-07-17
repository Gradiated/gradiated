"""Bounded CPU-only validation for the immutable SGLang admission packet."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parent
hf = ROOT / "probes" / "hf"
src = ROOT / "probes" / "source"
target = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"

config = json.loads((hf / "config.json").read_text())
text = config["text_config"]
layers = text["layer_types"]
assert config["architectures"] == ["Gemma4ForConditionalGeneration"]
assert text["dtype"] == "bfloat16"
assert len(layers) == text["num_hidden_layers"] == 60
assert layers.count("sliding_attention") == 50
assert layers.count("full_attention") == 10
assert text["sliding_window"] == 1024
assert text["num_kv_shared_layers"] == 0
assert text["num_global_key_value_heads"] == 4
assert text["num_attention_heads"] == 32
assert text["num_key_value_heads"] == 16
assert text["hidden_size"] == 5376
assert text["vocab_size"] == 262144
assert (hf / "chat_template.jinja").read_text().find("enable_thinking") >= 0

server = (src / "server_args.py").read_text()
model = (src / "model_config.py").read_text()
gemma = (src / "gemma4_causal.py").read_text()
assert '"Gemma4ForConditionalGeneration"' in server and '"Gemma4ForConditionalGeneration"' in model
assert '"fp8_e5m2"' in server
assert "num_kv_shared_layers" in gemma and "save_kv_cache=not self.is_kv_shared_layer" in gemma
assert "self.served_model_name = self.model_path" in server
assert "self.tokenizer_path = self.model_path" in server
assert "enable_metrics" in server and "enable_cache_report" in server

hashes = {}
for path in sorted(hf.iterdir()):
    hashes[path.name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
for path in sorted(src.iterdir()):
    try:
        ast.parse(path.read_text())
    except SyntaxError as exc:
        raise AssertionError(f"source syntax failure: {path.name}: {exc}") from exc

result = {
    "classification": "cpu_safe_contract_pass",
    "target_revision": target,
    "config": {"architecture": config["architectures"][0], "dtype": text["dtype"],
               "layers": len(layers), "sliding_layers": layers.count("sliding_attention"),
               "full_layers": layers.count("full_attention"), "sliding_window": text["sliding_window"],
               "kv_shared_layers": text["num_kv_shared_layers"], "global_kv_heads": text["num_global_key_value_heads"],
               "attention_heads": text["num_attention_heads"], "kv_heads": text["num_key_value_heads"],
               "hidden_size": text["hidden_size"], "vocab_size": text["vocab_size"]},
    "source": {"ast_parse": "pass", "gemma4_registration": "pass", "shared_kv_path": "pass",
               "fp8_e5m2_option": "pass", "metrics_and_cache_hooks": "pass", "served_model_default": "pass"},
    "file_hashes": hashes,
}
(ROOT / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
