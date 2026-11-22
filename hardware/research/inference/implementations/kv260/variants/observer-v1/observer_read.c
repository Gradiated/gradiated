/* Observation-only companion library. Caller owns and validates the existing
 * UIO mapping and observer firmware. No device open, mapping, reset or write.
 * Invoke only after sampling has stopped and no token can be submitted.
 * A host watchdog still owns the absolute limit for a stalled bus access. */
#include <stdint.h>
#include <stddef.h>

static uint32_t observe_read(volatile uint32_t *base, size_t offset)
{
    uint32_t value;
#if defined(__aarch64__)
    __asm__ __volatile__("dsb sy" ::: "memory");
    value = base[offset / 4];
    __asm__ __volatile__("dsb sy" ::: "memory");
#else
#error "Observer MMIO requires AArch64"
#endif
    return value;
}

/* out[0]=ABI, [1]=status, [2]=overflow, [3..34]=counters.
 * Returns 0 only if two complete idle snapshots agree and none overflowed.
 * A nonzero return makes the partial buffer diagnostic only. */
int observer_snapshot(void *mapping, uint32_t *out, size_t words)
{
    volatile uint32_t *base = mapping;
    size_t i;
    uint32_t again;
    if (!mapping || ((uintptr_t)mapping & 3) || !out || words != 35) return -1;
    out[0] = observe_read(base, 0x24);
    out[1] = observe_read(base, 0x28);
    if (out[0] != UINT32_C(0x4b563031) || out[1] != 0) return -2;
    out[2] = observe_read(base, 0x2c);
    if (out[2] != 0) return -3;
    for (i = 0; i < 32; ++i) out[3+i] = observe_read(base, 0x40 + 4*i);
    for (i = 0; i < 35; ++i) {
        again = observe_read(base, i < 3 ? 0x24 + 4*i : 0x40 + 4*(i-3));
        if (again != out[i]) return -4;
    }
    if (observe_read(base, 0x28) != 0 || observe_read(base, 0x2c) != 0) return -5;
    return 0;
}
