"""Independent arithmetic oracle for the directed output-projection fixture."""

import struct


def hex_words(path, width, words):
    mask = (1 << width) - 1
    path.write_text("".join(f"{word & mask:0{(width + 3) // 4}x}\n" for word in words))


def dense_cases(matrix, output):
    activations = [1, -32768] + [(6197 * index % 65536) - 32768 for index in range(2, 32)]
    frozen = [value for (value,) in struct.iter_unpack("<h", matrix)]
    positive_clip = [32767 if value >= 0 else -32768 for value in activations]
    negative_clip = [-32768 if value >= 0 else 32767 for value in activations]
    directed = [positive_clip, negative_clip]
    directed.extend([0, weight] + [0] * 30 for weight in (-1, -3, 1, 3, 101))
    original = [weight for row in directed for weight in row] + frozen[len(directed) * 32:]
    for arm in range(3):
        path = output / f"dense-{arm}"
        path.mkdir()
        weights = original.copy()
        if arm == 2:
            weights[6 * 32 + 1] = 105
        products, sums, rows = [], [], []
        for row in range(32):
            total = 0
            for index, activation in enumerate(activations):
                product = activation * weights[row * 32 + index]
                total += product
                products.append(product)
                sums.append(total)
            # The denominator is an exact power of two and these sums fit
            # within the exact integer range of binary64.
            rounded = round(total / 65536)
            clipped = max(-32768, min(32767, rounded))
            rows.append((int(clipped != rounded) << 16) | (clipped & 0xffff))
        assert rows[:7] == [0x17fff, 0x18000, 0, 2, 0, 0xfffe, 0xffcc if arm == 2 else 0xffce]
        beats = [beat for (beat,) in struct.iter_unpack("<Q", struct.pack("<1024h", *weights))]
        for name, width, data in (("x", 16, activations), ("w", 16, weights), ("bram", 16, original),
                                  ("p", 32, products), ("sum", 48, sums), ("y", 17, rows), ("ddr", 64, beats)):
            hex_words(path / (name + ".hex"), width, data)
        yield path, arm
