#!/usr/bin/env python3
import json
import shutil
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from validate_holdout import validate

def canonical(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def sha(v):
    import hashlib
    return hashlib.sha256(v).hexdigest()
def rehash(row):
    row["content_sha256"] = sha(canonical({k:v for k,v in row.items() if k != "content_sha256"}))
    return row

def rejects(mutator):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "project"; shutil.copytree(ROOT, root)
        mutator(root)
        try: validate(root)
        except ValueError: return
        raise AssertionError("mutation accepted")

def main():
    assert validate()["pass"]
    rejects(lambda root: (root / "sealed_holdout_v2" / "holdout.jsonl").write_text((root / "sealed_holdout_v2" / "holdout.jsonl").read_text().replace("aurora", "corrupted", 1)))
    def wrong_count(root):
        p=root / "sealed_holdout_v2" / "holdout.jsonl"; rows=p.read_text().splitlines(); row=json.loads(rows[0]); row["category"]="coding"; rows[0]=json.dumps(rehash(row),sort_keys=True,separators=(",",":")); p.write_text("\n".join(rows)+"\n")
    rejects(wrong_count)
    def overlap(root):
        p=root / "sealed_holdout_v2" / "holdout.jsonl"; rows=p.read_text().splitlines(); row=json.loads(rows[0]); row["teacher_forced_text"]="Quality calibration sentinel 1: exact schemas and retrieval values remain stable."; rows[0]=json.dumps(rehash(row),sort_keys=True,separators=(",",":")); p.write_text("\n".join(rows)+"\n")
    rejects(overlap)
    rejects(lambda root: (root / "POST_DEVELOPMENT_QUALITY_POLICY.json").write_text((root / "POST_DEVELOPMENT_QUALITY_POLICY.json").read_text().replace("10000", "9999", 1)))
    print(json.dumps({"pass":True,"mutations_rejected":4},sort_keys=True))

if __name__ == "__main__": main()
