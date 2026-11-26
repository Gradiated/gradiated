import hashlib
import json

import pytest
from repair_resume import validate_origin_identity


def test_unchanged_train_script_does_not_bless_modified_helpers(monkeypatch):
    identity = {
        "executable_sources_sha256": {
            "runner/train.py": "frozen",
            "runner/distributed.py": "reviewed",
        }
    }
    expected = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    monkeypatch.setattr("repair_resume.MEASURED_IDENTITY_SHA256", expected)
    validate_origin_identity(identity)
    identity["executable_sources_sha256"]["runner/distributed.py"] = "locally modified"
    with pytest.raises(ValueError, match="complete measured"):
        validate_origin_identity(identity)
