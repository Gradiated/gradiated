"""Extract the frozen bank 4 matrix for the KV260 DDR4 comparison."""
import argparse
import hashlib
import struct
from pathlib import Path

# Frozen physical-acceptance image and its row-major 32 x 32 output projection.
IMAGE_SHA256 = "698df2e177b8e478088fffe9b02af09cd10c9ac0afbe252f3b031f133262e055"
MATRIX_SHA256 = "a470ed9570d1ebf01a5431fda805d02e0e11b88dcb0e06785e324bdd37c57e89"
# The loader sends one 32-bit word per entry in E, Q, K, V and then O.
FIRST_WEIGHT_WORD = 320 * 32 + 3 * 32 * 32


def extract(image):
    if hashlib.sha256(image).hexdigest() != IMAGE_SHA256:
        raise ValueError("Expected the frozen text-input model loader image")
    words = struct.unpack_from("<1024I", image, FIRST_WEIGHT_WORD * 4)
    # Signed coefficients already occupy the low 16 bits in two's complement.
    matrix = struct.pack("<1024H", *words)
    if hashlib.sha256(matrix).hexdigest() != MATRIX_SHA256:
        raise ValueError("Output-projection weight digest differs")
    return matrix


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="frozen model-words.bin")
    parser.add_argument("output", type=Path, help="new file for the packed weights")
    args = parser.parse_args()
    matrix = extract(args.image.read_bytes())
    with args.output.open("xb") as stream:
        stream.write(matrix)
    print(f"{len(matrix)} bytes, SHA-256 {MATRIX_SHA256}")
