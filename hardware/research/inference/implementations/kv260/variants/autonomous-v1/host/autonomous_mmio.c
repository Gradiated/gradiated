/* Uses the owned KV260 UIO mapping. Supervise independently: a stalled
 * device bus transaction cannot be interrupted by a userspace deadline. */
#include <stddef.h>
#include <stdint.h>

struct clock_value { long seconds; long nanoseconds; };
extern int clock_gettime(int id, struct clock_value *value);
_Static_assert(sizeof(long) == 8, "Linux LP64 required");

struct autonomous_event {
    uint64_t observed_ns;
    uint32_t status;
    uint32_t token;
};

enum {
    AU_STATUS = 0x28,
    AU_PROMPT_APPEND = 0x30,
    AU_MAX_OUTPUT = 0x34,
    AU_START = 0x38,
    AU_OUTPUT_DATA = 0x40,
    AU_ACTIVE = 1,
    AU_DONE = 2,
    AU_FAULT = 4,
    AU_OUTPUT_AVAILABLE = 8
};

static uint64_t monotonic_ns(void)
{
    struct clock_value now;
    if (clock_gettime(1, &now) != 0) return UINT64_MAX;
    return (uint64_t)now.seconds * UINT64_C(1000000000) + (uint64_t)now.nanoseconds;
}

static void barrier(void)
{
#if defined(__aarch64__)
    __asm__ __volatile__("dsb sy" ::: "memory");
#else
#error "The autonomous MMIO adapter requires AArch64"
#endif
}

static int aligned_mapping(const void *mapping)
{
    return mapping != NULL && (uintptr_t)mapping % 4 == 0;
}

static uint32_t read_word(volatile uint32_t *base, uint32_t offset)
{
    uint32_t value;
    barrier();
    value = base[offset / 4];
    barrier();
    return value;
}

int autonomous_read(void *mapping, uint32_t offset, uint32_t *value)
{
    if (!aligned_mapping(mapping) || value == NULL) return -1;
    switch (offset) {
    case 0x00: case 0x20: case 0x24: case AU_STATUS: case 0x2c:
    case AU_MAX_OUTPUT: case 0x3c: case 0x44: case 0x48: case 0x4c:
    case 0x50: case 0x54: case 0x58:
        *value = read_word(mapping, offset);
        return 0;
    default:
        return -1;
    }
}

static void write_word(volatile uint32_t *base, uint32_t offset, uint32_t value)
{
    barrier();
    base[offset / 4] = value;
    barrier();
}

/* Writes only the extension registers after validating the whole request and
 * checking the verified mapping's ABI and freshly cleared state. */
int autonomous_start(void *mapping, const uint16_t *prefix, size_t count,
                     uint32_t max_output, uint64_t deadline)
{
    volatile uint32_t *base = mapping;
    size_t index;
    if (!aligned_mapping(mapping) || prefix == NULL ||
        count < 1 || count > 256 || max_output > 255 || prefix[0] != 256)
        return -1;
    for (index = 0; index < count; ++index) {
        if (prefix[index] >= 320) return -1;
    }
    if (monotonic_ns() >= deadline) return -2;
    if (read_word(base, 0x24) != UINT32_C(0x41553031) ||
        read_word(base, AU_STATUS) != 0 || read_word(base, 0x2c) != 0 ||
        read_word(base, 0x20) != 0)
        return -3;
    for (index = 0; index < count; ++index) {
        if (monotonic_ns() >= deadline) return -2;
        write_word(base, AU_PROMPT_APPEND, prefix[index]);
    }
    if (read_word(base, 0x2c) != count) return -3;
    if (monotonic_ns() >= deadline) return -2;
    write_word(base, AU_MAX_OUTPUT, max_output);
    if (read_word(base, AU_MAX_OUTPUT) != max_output) return -3;
    write_word(base, AU_START, 1);
    return 0;
}

/* Returns 1 for an observed token and 0 for completion once drained. On a
 * failed read/protocol/deadline, previously completed events remain evidence. */
int autonomous_wait(void *mapping, uint64_t deadline,
                    struct autonomous_event *event)
{
    volatile uint32_t *base = mapping;
    if (!aligned_mapping(mapping) || event == NULL) return -1;
    while (monotonic_ns() < deadline) {
        uint32_t status = read_word(base, AU_STATUS);
        event->status = status;
        if (status & AU_FAULT) return -4;
        if ((status & (AU_ACTIVE | AU_DONE)) != AU_ACTIVE &&
            (status & (AU_ACTIVE | AU_DONE)) != AU_DONE) return -3;
        if (status & AU_OUTPUT_AVAILABLE) {
            event->token = read_word(base, AU_OUTPUT_DATA);
            event->observed_ns = monotonic_ns();
            if (event->observed_ns >= deadline) return -2;
            if (event->token >= 320 || event->token == 257) return -3;
            return 1;
        }
        if (status & AU_DONE) {
            event->observed_ns = monotonic_ns();
            return event->observed_ns < deadline ? 0 : -2;
        }
    }
    return -2;
}
