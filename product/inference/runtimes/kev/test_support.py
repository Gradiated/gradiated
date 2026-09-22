"""CPU-only API/encoder doubles; never used by the serving runtime."""
from types import SimpleNamespace


def model_validate(data):
    return SimpleNamespace(**{**data, "questions": {
        key: SimpleNamespace(**{**q, "criteria": q.get("criteria")})
        for key, q in data["questions"].items()}})


def to_record(req):
    questions, meta = [], []
    for key, q in req.questions.items():
        keys = (list(q.criteria) if q.type == "choice" else ["false", "true"]
                if q.type == "noul" else [str(i) for i in range(len(q.criteria))])
        options = ([f"{k}: {v}" for k, v in q.criteria.items()] if q.type == "choice"
                   else ["no", "yes"] if q.type == "noul" else q.criteria)
        questions.append({"instr": q.instructions, "options": options, "label": 0})
        meta.append({"id": key, "type": q.type, "keys": keys, "legend": dict(zip(keys, options))})
    return {"state": req.state, "questions": questions}, meta


def to_answers(probabilities, meta):
    result = {}
    for p, m in zip(probabilities, meta):
        answer = {"type": m["type"]}
        if m["type"] == "noul":
            answer["noul"] = p[1]
        else:
            answer.update(probabilities=dict(zip(m["keys"], p)), confidence=0.0)
            if m["type"] == "choice":
                answer["choice"] = m["keys"][p.index(max(p))]
            else:
                answer.update(score=sum(i * v for i, v in enumerate(p)), legend=m["legend"])
        result[m["id"]] = answer
    return result


api = SimpleNamespace(SystemOneRequest=SimpleNamespace(model_validate=model_validate),
                      to_record=to_record, to_answers=to_answers)


def encode(tok, rec, *, max_state, max_branch, strict, option_isolation):
    assert strict is True
    ids = [100000] + tok(rec["state"]).input_ids
    state_length = len(ids)
    if state_length > max_state:
        raise ValueError("state exceeds limit")
    segments, options = [0] * state_length, []
    for i, question in enumerate(rec["questions"], 1):
        branch = [100001] + tok(question["instr"]).input_ids
        offsets = []
        for option in question["options"]:
            branch += [100002] + tok(option).input_ids + [100003]
            offsets.append(len(ids) + len(branch) - 1)
        branch += [100004]
        if state_length + len(branch) > max_branch:
            raise ValueError("branch exceeds limit")
        ids.extend(branch)
        segments.extend([i] * len(branch))
        options.append(offsets)
    return {"ids": ids, "seg": segments, "opt_idx": options, "option_isolation": option_isolation}
