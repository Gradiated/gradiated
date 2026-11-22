"""Integer oracles and deterministic boundary fixtures for the exact divider."""

import random


DIVISOR = 45426
MAX_SIGNED = (1 << 63) - 1
MIN_SIGNED = -(1 << 63)
LOW_BITS = (6, 8, 32)
MOD64 = (1 << 64) - 1


def rounded_division(n, d):
    quotient, remainder = divmod(abs(n), d)
    increment = 2 * remainder > d or (2 * remainder == d and quotient & 1)
    return (-1 if n < 0 else 1) * (quotient + int(increment))


def recurrence(n, bits):
    """Model the existing two-bit recurrence starting at the guarded prefix."""
    magnitude = abs(n)
    prefix = magnitude >> bits
    if prefix >= DIVISOR:
        prefix, bits = 0, 64
    quotient, remainder = 0, prefix
    for shift in range(bits - 2, -1, -2):
        trial = (remainder << 2) | ((magnitude >> shift) & 3)
        digit = sum(trial >= count * DIVISOR for count in (1, 2, 3))
        quotient = (quotient << 2) | digit
        remainder = trial - digit * DIVISOR
    return quotient, remainder, bits // 2


def raw_cases(rng):
    # Domains follow the RTL's accepted exponential, including arbitrary valid tables.
    maxima = (1 << 20, (DIVISOR - 1) << 8, (1 << 31) * (DIVISOR - 1))
    for role, (bits, high) in enumerate(zip(LOW_BITS, maxima, strict=True)):
        threshold = DIVISOR << bits
        given = {0, 1, DIVISOR - 1, DIVISOR, DIVISOR + 1, high - 1, high, high + 1,
                 threshold - 1, threshold, threshold + 1, MAX_SIGNED, 1 << 63}
        for quotient in (0, 1, 2, 3, (high // DIVISOR) // 2, high // DIVISOR):
            given.update(quotient * DIVISOR + DIVISOR // 2 + delta for delta in (-1, 0, 1))
            given.update(quotient * DIVISOR + delta for delta in (-1, 0, 1) if quotient > 0)
        given.update(rng.randrange(high + 1) for _ in range(700))
        given.update(rng.getrandbits(63) for _ in range(700))
        for magnitude in sorted(given):
            for sign in (-1, 1):
                n = sign * magnitude
                if not MIN_SIGNED <= n <= MAX_SIGNED:
                    continue
                oracle = divmod(magnitude, DIVISOR)
                seen_q, seen_r, steps = recurrence(n, bits)
                if (seen_q, seen_r) != oracle:
                    raise ValueError("Analytical recurrence and independent divmod disagree")
                for round_even in (0, 1):
                    expected = rounded_division(n, DIVISOR) if round_even else sign * oracle[0]
                    yield n, role, round_even, *oracle, expected, steps


def exp_oracle(a, table):
    if a > 0 or a < -(1 << 62):
        return 0, 1, 0
    if a < -(1 << 20):
        return 0, 0, 0
    exponent, remainder = divmod(-a, DIVISOR)
    index, fraction = divmod(remainder << 8, DIVISOR)
    if index + 1 not in table or index not in table:
        return 0, 1, 57
    first, second = table[index], table[index + 1]
    delta = rounded_division((second - first) * fraction, DIVISOR)
    return rounded_division(first + delta, 1 << exponent), 0, 73


def interface_cases(rng):
    blank = {}
    for a in (MIN_SIGNED, -(1 << 62) - 1, -(1 << 62), -(1 << 20) - 1, -(1 << 20), -1, 0, 1, MAX_SIGNED):
        result, error, saving = exp_oracle(a, blank)
        yield 1, 3, a, 0, result, error, saving
    for table_number in range(3):
        table = {}
        if table_number:
            yield 2, 0, 0, 0, 0, 0, 0  # clear table-valid bits with reset
        for i in range(257):
            value = (rng.randint(0, 0x8000_0000) if table_number == 2
                     else (0x8000_0000 if (i + table_number) & 1 else 0))
            table[i] = value
            yield 0, 0, i, value, 0, 0, 0
        arguments = {-1, 0, -(1 << 20), -(1 << 20) - 1}
        for q in (0, 1, 2, 11, 23):
            arguments.update(-q * DIVISOR + d for d in (-1, 0, 1))
        arguments.update(-rng.randrange((1 << 20) + 1) for _ in range(540))
        for a in sorted(arguments):
            result, error, saving = exp_oracle(a, table)
            yield 1, 3, a, 0, result, error, saving
    for d in (0, -1, 1, DIVISOR, DIVISOR + 1, 1 << 62, (1 << 62) + 1):
        nums = {MIN_SIGNED, MAX_SIGNED, 0, -1, 1}
        nums.update(sign * (q * DIVISOR + DIVISOR // 2 + e)
                    for q in (0, 1, 2, 11) for e in (-1, 0, 1) for sign in (-1, 1))
        nums.update(rng.randrange(MIN_SIGNED, MAX_SIGNED + 1) for _ in range(55))
        for a in sorted(nums):
            valid = 0 < d <= 1 << 62
            yield 1, 1, a, d, rounded_division(a, d) if valid else 0, int(not valid), 0


def write_fixtures(folder):
    random_source = random.Random(45426)
    counts = {}
    for filename, rows in (("raw.hex", raw_cases(random_source)), ("interface.hex", interface_cases(random_source))):
        count = 0
        with (folder / filename).open("x", encoding="ascii") as file:
            for row in rows:
                file.write(" ".join(f"{value & MOD64:016x}" for value in row) + "\n")
                count += 1
        counts[filename] = count
    return counts
