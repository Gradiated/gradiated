import pytest
from adapter_restore import saved_key


def test_weight_proj_is_preserved_when_removing_only_the_adapter_suffix():
    assert (
        saved_key("base.self_attn.sconv.weight_proj.lora_B.default.weight")
        == "base.self_attn.sconv.weight_proj.lora_B.weight"
    )
    with pytest.raises(ValueError, match="unsupported"):
        saved_key("base.self_attn.weight_proj.weight")
