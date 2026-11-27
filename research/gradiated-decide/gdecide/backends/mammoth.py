"""mammoth-1 / elephant-1 (Base Labs) through their own release runtime: OneJev's qev DecisionEngine @81ce62f with the
checkpoint's serve.patch, installed by the checkpoint's setup.sh into its own environment (``vm/setup-mammoth.sh``).

The engine prefills the shared prefix once per request and reads every question in one batched forward, exactly as
the checkpoint's ``engine.py`` (its Decision Index engine) does, including the sequential fallback for the largest
multi-question requests. Requests over the trained length limit are reported as unsupported, never truncated.
"""

from __future__ import annotations


class Unsupported(ValueError):
    pass


FIELDS = {"choice": {"type", "choice", "probabilities"}, "noul": {"type", "noul"},
          "score": {"type", "score", "probabilities"}}


class MammothDecider:
    unsupported = (Unsupported,)

    def __init__(self, checkpoint: str, device: str):
        from qev.engine import DecisionEngine

        self.engine = DecisionEngine(checkpoint, device=device)
        info = self.engine.info
        self.settings = {"runtime": "OneJev qev @81ce62f + serve.patch", "fork_mode": info.fork_mode,
                         "attention": info.extra.get("attention"), "readout": info.extra.get("readout"),
                         "calibration": info.extra.get("calibration")}
        self.temperature = 1.0

    def one(self, request: dict) -> dict:
        from qev.schema import SystemOneRequest

        for q in request["questions"].values():
            if q.get("type") not in FIELDS:
                raise Unsupported(f"question type {q.get('type')}")
        sr = SystemOneRequest(state=request["state"], questions=request["questions"])
        try:
            resp, _ = self.engine.decide(sr)
        except ValueError as e:
            if "limit is" in str(e):
                raise Unsupported(str(e)) from e
            raise
        except RuntimeError as e:
            if "32BitIndexMath" not in str(e):
                raise
            mode, self.engine.info.fork_mode = self.engine.info.fork_mode, "sequential"
            try:
                resp, _ = self.engine.decide(sr)
            finally:
                self.engine.info.fork_mode = mode
        answers = {k: a.model_dump(include=FIELDS[a.type]) for k, a in resp.answers.items()}
        return {"answers": answers, "usage": {}}

    def decide(self, requests, temperature: float | None = None):
        if isinstance(requests, dict):
            return self.one(requests)
        return [self.one(r) for r in requests]
