import random

from gdecide.prepare import NONE_KEY, abstain, augmented, reserialize


def row(expected="b", crit=None):
    crit = crit or {"a": "apple", "b": "banana", "c": "cherry"}
    return {"id": "1", "source": "s", "state": {"fruit": "yellow", "n": 2},
            "questions": {"q": {"type": "choice", "instructions": "Which?", "criteria": crit},
                          "y": {"type": "noul", "instructions": "Yes?"}},
            "expected": {"q": expected, "y": 1.0}}


def test_abstain_keeps_or_removes_gold():
    kept = removed = 0
    for i in range(400):
        out = abstain(row(), random.Random(i), p=1.0, remove=0.5)
        crit, target = out["questions"]["q"]["criteria"], out["expected"]["q"]
        assert NONE_KEY in crit and out["expected"]["y"] == 1.0
        if target == NONE_KEY:
            removed += 1
            assert "b" not in crit and len(crit) == 3
        else:
            kept += 1
            assert target == "b" and len(crit) == 4
    assert 120 < removed < 280 and kept > 120


def test_abstain_skips_soft_existing_and_two_option_removal():
    assert abstain(row({"a": 0.5, "b": 0.5}), random.Random(0), 1.0, 1.0)["questions"]["q"]["criteria"] == {"a": "apple", "b": "banana", "c": "cherry"}
    r = row("a", {"a": "yes", "other": "Something else"})
    assert abstain(r, random.Random(0), 1.0, 1.0) is r
    out = abstain(row("a", {"a": "apple", "b": "banana"}), random.Random(0), 1.0, 1.0)
    assert out["expected"]["q"] == "a" and len(out["questions"]["q"]["criteria"]) == 3
    soft = abstain(row({"a": 0.95, "b": 0.05}), random.Random(1), 1.0, 1.0)
    assert soft["expected"]["q"] == NONE_KEY and "a" not in soft["questions"]["q"]["criteria"]


def test_reserialize_and_noop_default():
    styles = {reserialize(row(), random.Random(i), 1.0)["state"].split("\n")[0] for i in range(50)}
    assert len(styles) >= 3 and all(isinstance(s, str) for s in styles)
    r = row()
    assert augmented(r, random.Random(0), 0.0, {}) == r
