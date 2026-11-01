"""Fail-closed audit admission and cache identity, shared by auditing and synthesis."""

from __future__ import annotations

import hashlib
import json


SNAPSHOT_KEYS = ("twin_id", "team_id", "loaded_now_utc", "shift_days")
AUDIT_VERSION = 3


def parse_reply(text: str, keys: tuple[str, ...], prefer_queries: bool = False) -> dict:
    decoder, position, found, queries = json.JSONDecoder(), 0, None, []
    while (start := text.find("{", position)) >= 0:
        try:
            value, end = decoder.raw_decode(text, start)
            position = end
            if isinstance(value, dict) and any(k in value for k in keys):
                found = value
                if isinstance(value.get("queries"), list):
                    queries.extend(q for q in value["queries"] if isinstance(q, dict) and q.get("sql"))
        except ValueError:
            position = start + 1
    if found is None:
        raise ValueError("No structured model reply with the required keys")
    if prefer_queries and queries:
        return {"queries": queries}
    return found


def snapshot(base: dict) -> dict:
    return {k: base.get(k) for k in SNAPSHOT_KEYS}


def cache_key(base: dict, model: str) -> str:
    value = {"snapshot": snapshot(base), "model": model, "version": AUDIT_VERSION}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def valid_verdict(rec: dict) -> bool:
    verdict, defects = rec.get("verdict"), rec.get("defects")
    if verdict not in ("CLEAN", "MINOR", "MATERIAL") or not isinstance(defects, list):
        return False
    if any(not isinstance(d, dict) or d.get("severity") not in ("minor", "material")
           or not str(d.get("what") or "").strip() or not str(d.get("evidence") or "").strip() for d in defects):
        return False
    expected = "MATERIAL" if any(d["severity"] == "material" for d in defects) else "MINOR" if defects else "CLEAN"
    return verdict == expected


def completed(rec: dict) -> bool:
    return not rec.get("error") and valid_verdict(rec) and any(
        isinstance(r, dict) and isinstance(r.get("result"), str) and r["result"].strip()
        and not r["result"].startswith(("ERROR", "REJECTED")) for r in rec.get("queries_run") or [])


def reusable(rec: dict, base: dict, model: str) -> bool:
    return rec.get("cache_key") == cache_key(base, model) and completed(rec)


def admissible(rec: dict, base: dict) -> bool:
    return (completed(rec) and rec.get("snapshot") == snapshot(base)
            and rec.get("verdict") in ("CLEAN", "MINOR"))
