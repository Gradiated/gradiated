"""Pack the frozen tied embedding in the DDR logits reader's order."""

import argparse
from hashlib import sha256
from pathlib import Path
import struct


IMAGE_SHA256 = "698df2e177b8e478088fffe9b02af09cd10c9ac0afbe252f3b031f133262e055"
MATRIX_SHA256 = "7a77c0b9cd6f66e1f68d6905c5f2962bf58d92543fbb5e5dbb18980ee9f4a787"


def extract(image):
    if sha256(image).hexdigest() != IMAGE_SHA256:
        raise ValueError("Expected the frozen conditioned loader image")
    weights = struct.unpack_from("<10240I", image)
    packed = struct.pack("<10240H", *(
        weights[(group * 8 + lane) * 32 + coordinate]
        for group in range(40) for coordinate in range(32) for lane in range(8)
    ))
    if sha256(packed).hexdigest() != MATRIX_SHA256:
        raise ValueError("Packed tied-embedding weights differ")
    return packed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = extract(args.image.read_bytes())
    with args.output.open("xb") as stream:
        stream.write(data)
    print(f"{len(data)} bytes, SHA-256 {sha256(data).hexdigest()}")
