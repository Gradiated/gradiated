"""Independently verify the sealed UART payload against the new and reused byte pins."""

import argparse
import base64
import gzip
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tarfile


def digest(payload):
    return {"bytes": len(payload), "sha256": sha256(payload).hexdigest()}


def verify(run, packet, previous, discovery):
    invocation = json.loads((run / "invocation.json").read_bytes())
    outer = (run / "board-transfer.gz").read_bytes()
    assert digest(outer) == {"bytes": invocation["archive_bytes"], "sha256": invocation["archive_sha256"]}
    wrapped = json.loads(gzip.decompress(outer))
    assert set(wrapped) == {"packet.tar.gz"}
    inner = base64.b64decode(wrapped["packet.tar.gz"], validate=True)
    assert sha256(inner).hexdigest() == invocation["inner_sha256"]
    with tarfile.open(fileobj=BytesIO(inner), mode="r:gz") as archive:
        members = archive.getmembers()
        assert len(members) == len({m.name for m in members}) and all(m.isfile() for m in members)
        fields = {m.name: archive.extractfile(m).read() for m in members}
    original = fields.pop("configuration.json")
    assert sha256(original).hexdigest() == invocation["config_sha256"]
    assert original == (packet / "config.json").read_bytes()
    assert json.loads(original)["pins"] == invocation["sources"]
    prior = json.loads(previous.read_bytes())
    readback = json.loads(discovery.read_bytes())
    assert prior["boot"] == invocation["boot"] == readback["boot"]
    reuse = json.loads(fields.pop("reuse.json"))
    retained = reuse["pins"]
    assert prior["board"] == reuse["directory"] == invocation["reused_from"]
    assert sorted(retained) == invocation["reused_files"]
    assert set(retained) <= set(readback["reusable"])
    assert all(prior["sources"][name] == pin for name, pin in retained.items())
    raw = {name: digest(payload) for name, payload in fields.items()}
    assert not set(raw) & set(retained) and raw | retained == invocation["sources"]
    assert all(digest((packet / name).read_bytes()) == pin for name, pin in invocation["sources"].items())
    return {"config_sha256": invocation["config_sha256"], "archive_sha256": invocation["archive_sha256"],
            "new_members": sorted(raw), "reused_members": sorted(retained), "verified": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "packet", "previous", "discovery"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.run, args.packet, args.previous, args.discovery), indent=2, sort_keys=True))
