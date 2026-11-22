/* Linux AArch64 adapter for the existing portable host API. No device opens,
 * address mapping, FPGA programming or sampling happen in this library.
 * The Python caller verifies payload hashes and the UIO/clock preconditions.
 * A bus access that never completes cannot be interrupted by this deadline;
 * run in a supervised child only after the PS/PL setup is independently checked.
 */
#include "host.h"

/* Stable Linux AArch64 LP64 clock_gettime ABI; avoids importing a sysroot or
 * development packages onto the board. Linked dynamically against its libc. */
struct board_timespec { long seconds; long nanoseconds; };
extern int clock_gettime(int clock_id, struct board_timespec *value);
_Static_assert(sizeof(long) == 8, "Linux LP64 required");

static uint64_t now_ns(void *unused)
{
    struct board_timespec value;
    (void)unused;
    if (clock_gettime(1, &value) != 0) return UINT64_MAX;
    return (uint64_t)value.seconds * UINT64_C(1000000000) +
           (uint64_t)value.nanoseconds;
}

static void barrier(void)
{
#if defined(__aarch64__)
    __asm__ __volatile__("dsb sy" ::: "memory");
#else
#error "The real MMIO adapter requires AArch64"
#endif
}

static int read32(void *context, uint32_t offset, uint32_t *value,
                  uint64_t deadline)
{
    volatile uint32_t *base = context;
    if ((offset & 3) || offset > FPGA_REG_CONTEXT_COUNT || now_ns(0) >= deadline)
        return -1;
    barrier();
    *value = base[offset / 4];
    barrier();
    return 0;
}

static int write32(void *context, uint32_t offset, uint32_t value,
                   uint64_t deadline)
{
    volatile uint32_t *base = context;
    if ((offset & 3) || offset > FPGA_REG_CONTEXT_COUNT || now_ns(0) >= deadline)
        return -1;
    barrier();
    base[offset / 4] = value;
    barrier();
    return 0;
}

/* result[0]=API result, [1]=words loaded, [2]=logits read, [3]=context count,
 * [4]=saturation. On failure, all output remains diagnostic and must not sample.
 * image_verified is an explicit assertion by the hash-verifying Python caller. */
int board_bos(void *base, const uint8_t *image, size_t bytes, int image_verified,
              uint64_t budget_ns, int32_t *logits, uint32_t *result)
{
    struct fpga_host host;
    struct fpga_host_frame frame;
    struct fpga_host_io io = {base, read32, write32, now_ns, 0, 0};
    struct fpga_host_image model = {image, bytes, FPGA_HOST_MODEL_WORDS,
                                   image_verified == 1};
    uint64_t start, deadline;
    int rc;
    size_t i;
    if (!base || ((uintptr_t)base & 3) || !image || !logits || !result ||
        budget_ns == 0 || budget_ns > UINT64_C(30000000000)) return -1;
    for (i = 0; i < 5; ++i) result[i] = 0;
    /* Reject a bad image before reset or any other MMIO. */
    if (!model.sha256_verified || bytes != FPGA_HOST_MODEL_BYTES) return -2;
    start = now_ns(0);
    if (start == UINT64_MAX || UINT64_MAX - start < budget_ns) return -3;
    deadline = start + budget_ns;
    rc = fpga_host_init(&host, &io);
    if (rc == 0) rc = fpga_host_reset(&host, deadline);
    if (rc == 0) rc = fpga_host_load_model(&host, &model, deadline);
    if (rc == 0) rc = fpga_host_step(&host, FPGA_HOST_BOS, &frame, deadline);
    result[0] = (uint32_t)rc;
    result[1] = (uint32_t)host.model_words_written;
    result[2] = (uint32_t)host.logits_received;
    result[3] = host.context_count;
    if (rc == 0) {
        result[4] = frame.saturated;
        for (i = 0; i < FPGA_HOST_LOGITS; ++i) logits[i] = frame.logits[i];
    }
    return rc;
}

/* Opaque, caller-owned storage. Calls remain serialized under one UIO flock;
 * begin explicitly resets and loads, clear retains weights, step retains KV.
 * No operation retries or repairs a failed host session. */
size_t board_session_bytes(void)
{
    return sizeof(struct fpga_host);
}

static int session_deadline(uint64_t budget_ns, uint64_t *deadline)
{
    uint64_t start;
    if (!budget_ns || budget_ns > UINT64_C(30000000000))
        return FPGA_HOST_E_ARGUMENT;
    start = now_ns(0);
    if (start == UINT64_MAX || UINT64_MAX - start < budget_ns)
        return FPGA_HOST_E_CLOCK;
    *deadline = start + budget_ns;
    return 0;
}

static struct fpga_host *session_storage(void *storage, size_t bytes)
{
    if (!storage || bytes != sizeof(struct fpga_host) ||
        (uintptr_t)storage % _Alignof(struct fpga_host)) return 0;
    return storage;
}

static int session_result(struct fpga_host *host, int rc, uint32_t *result)
{
    result[0] = (uint32_t)rc;
    result[1] = (uint32_t)host->model_words_written;
    result[2] = (uint32_t)host->logits_received;
    result[3] = host->context_count;
    result[4] = 0;
    return rc;
}

int board_session_begin(void *storage, size_t storage_bytes, void *base,
                        const uint8_t *image, size_t bytes, int image_verified,
                        uint64_t budget_ns, uint32_t *result)
{
    struct fpga_host *host = session_storage(storage, storage_bytes);
    struct fpga_host_io io = {base, read32, write32, now_ns, 0, 0};
    struct fpga_host_image model = {image, bytes, FPGA_HOST_MODEL_WORDS,
                                   image_verified == 1};
    uint64_t deadline;
    int rc;
    if (!host || !base || ((uintptr_t)base & 3) || !image || !result)
        return FPGA_HOST_E_ARGUMENT;
    if (!model.sha256_verified || bytes != FPGA_HOST_MODEL_BYTES)
        return FPGA_HOST_E_UNVERIFIED;
    rc = session_deadline(budget_ns, &deadline);
    if (rc) return rc;
    rc = fpga_host_init(host, &io);
    if (!rc) rc = fpga_host_reset(host, deadline);
    if (!rc) rc = fpga_host_load_model(host, &model, deadline);
    return session_result(host, rc, result);
}

int board_session_step(void *storage, size_t storage_bytes, uint16_t token,
                       uint64_t budget_ns, int32_t *logits, uint32_t *result)
{
    struct fpga_host *host = session_storage(storage, storage_bytes);
    struct fpga_host_frame frame;
    uint64_t deadline;
    size_t i;
    int rc;
    if (!host || !logits || !result) return FPGA_HOST_E_ARGUMENT;
    rc = session_deadline(budget_ns, &deadline);
    if (rc) return rc;
    rc = fpga_host_step(host, token, &frame, deadline);
    session_result(host, rc, result);
    if (!rc) {
        result[4] = frame.saturated;
        for (i = 0; i < FPGA_HOST_LOGITS; ++i) logits[i] = frame.logits[i];
    }
    return rc;
}

int board_session_clear(void *storage, size_t storage_bytes,
                        uint64_t budget_ns, uint32_t *result)
{
    struct fpga_host *host = session_storage(storage, storage_bytes);
    uint64_t deadline;
    int rc;
    if (!host || !result) return FPGA_HOST_E_ARGUMENT;
    rc = session_deadline(budget_ns, &deadline);
    if (rc) return rc;
    rc = fpga_host_clear_context(host, deadline);
    return session_result(host, rc, result);
}
