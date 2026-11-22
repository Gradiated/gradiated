#ifndef GRADIATED_FPGA_HOST_H
#define GRADIATED_FPGA_HOST_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Register offsets and fields match rtl/axi_transformer.sv. */
enum fpga_host_register {
    FPGA_REG_STATUS = 0x00,
    FPGA_REG_MODEL_BANK = 0x04,
    FPGA_REG_MODEL_ADDRESS = 0x08,
    FPGA_REG_MODEL_DATA = 0x0c,
    FPGA_REG_TOKEN = 0x10,
    FPGA_REG_LOGIT_INDEX = 0x14,
    FPGA_REG_LOGIT_DATA = 0x18,
    FPGA_REG_CONTROL = 0x1c,
    FPGA_REG_CONTEXT_COUNT = 0x20
};

#define FPGA_STATUS_CONFIGURED      (UINT32_C(1) << 0)
#define FPGA_STATUS_BUSY            (UINT32_C(1) << 1)
#define FPGA_STATUS_ERROR           (UINT32_C(1) << 2)
#define FPGA_STATUS_SATURATED       (UINT32_C(1) << 3)
#define FPGA_STATUS_LOGIT_VALID     (UINT32_C(1) << 4)
#define FPGA_STATUS_TOKEN_CAPACITY  (UINT32_C(1) << 5)
#define FPGA_STATUS_MODEL_CAPACITY  (UINT32_C(1) << 6)
#define FPGA_STATUS_KNOWN_BITS      UINT32_C(0x7f)

#define FPGA_CONTROL_CLEAR_CONTEXT UINT32_C(1)
#define FPGA_CONTROL_RESET         UINT32_C(2)
#define FPGA_HOST_MODEL_WORDS      UINT32_C(29281)
#define FPGA_HOST_MODEL_BYTES      ((size_t)117124)
#define FPGA_HOST_MODEL_BANKS       ((size_t)14)
#define FPGA_HOST_VOCABULARY        UINT16_C(320)
#define FPGA_HOST_BOS               UINT16_C(256)
#define FPGA_HOST_CONTEXT_LIMIT     UINT16_C(256)
#define FPGA_HOST_LOGITS            ((size_t)320)
/* Real score = encoded signed32 logit * 2^-16. Sampling remains external. */
#define FPGA_HOST_LOGIT_EXPONENT    (-16)
#define FPGA_HOST_DEFAULT_POLL_LIMIT UINT32_C(1000000)

enum fpga_host_result {
    FPGA_HOST_OK = 0,
    FPGA_HOST_E_ARGUMENT = -1,
    FPGA_HOST_E_UNVERIFIED = -2,
    FPGA_HOST_E_IMAGE = -3,
    FPGA_HOST_E_STATE = -4,
    FPGA_HOST_E_TIMEOUT = -5,
    FPGA_HOST_E_IO = -6,
    FPGA_HOST_E_CORE = -7,
    FPGA_HOST_E_LOGIT_INDEX = -8,
    FPGA_HOST_E_CONTEXT_FULL = -9,
    FPGA_HOST_E_BOS_REQUIRED = -10,
    FPGA_HOST_E_PROTOCOL = -11,
    FPGA_HOST_E_CLOCK = -12,
    FPGA_HOST_E_POLL_LIMIT = -13,
    FPGA_HOST_E_TOKEN_RANGE = -14
};

enum fpga_host_state {
    FPGA_HOST_UNKNOWN = 0,
    FPGA_HOST_EMPTY,
    FPGA_HOST_READY,
    FPGA_HOST_WAITING_LOGITS,
    FPGA_HOST_NEEDS_RESET
};

/* These callbacks represent completed, ordered 32-bit bus transactions. A
 * nonzero return reports a bus failure, including AXI SLVERR. They must enforce
 * the supplied absolute monotonic deadline and must not leave an outstanding
 * transaction when they return. The eventual board adapter owns mapping and
 * memory barriers; this library opens no device and assumes no board address.
 * now_ns must be monotonic. poll_wait is optional and must also honor deadline.
 * The finite poll limit protects against an accidentally nonadvancing clock. */
struct fpga_host_io {
    void *context;
    int (*read32)(void *context, uint32_t offset, uint32_t *value,
                  uint64_t deadline_ns);
    int (*write32)(void *context, uint32_t offset, uint32_t value,
                   uint64_t deadline_ns);
    uint64_t (*now_ns)(void *context);
    int (*poll_wait)(void *context, uint64_t deadline_ns);
    uint32_t poll_limit; /* Zero selects FPGA_HOST_DEFAULT_POLL_LIMIT. */
};

struct fpga_host_model_bank {
    uint8_t bank;
    uint32_t word_count;
    uint32_t image_word_offset;
};

extern const struct fpga_host_model_bank
    fpga_host_model_banks[FPGA_HOST_MODEL_BANKS];

/* The caller must verify these exact little-endian image bytes against its
 * trusted export manifest before setting sha256_verified. The driver does not
 * compute or authenticate SHA256: this flag is the caller's explicit assertion.
 * Each model word occupies four bytes, including packed cosine/sine in bank11.
 * Weight, table, arithmetic and source provenance belong to the export manifest. */
struct fpga_host_image {
    const uint8_t *little_endian_bytes;
    size_t byte_count;
    uint32_t word_count;
    bool sha256_verified;
};

struct fpga_host_status {
    uint32_t raw;
    uint16_t context_count;
    bool configured;
    bool busy;
    bool error;
    bool saturated;
    bool logit_valid;
    bool token_capacity;
    bool model_capacity;
};

struct fpga_host_frame {
    int32_t logits[FPGA_HOST_LOGITS];
    size_t received;
    bool complete;
    bool saturated;
};

/* One driver must exclusively own the adapter; calls must be serialized.
 * init does no I/O. Reset and a
 * verified full load establish ownership; probe never adopts unknown weights.
 * Failed/late I/O or invalid device sequencing requires an explicit reset and
 * reload. No function silently retries a token, clears context or samples text.
 * Public diagnostic fields report only confirmed observations/transactions. */
struct fpga_host {
    struct fpga_host_io io;
    enum fpga_host_state state;
    enum fpga_host_result last_error;
    enum fpga_host_result fault; /* First invalidating cause; explicit successful reset clears it. */
    uint32_t last_status;
    uint32_t last_context_count;
    uint32_t last_logit_index;
    int last_io_error;
    size_t model_words_written;
    size_t logits_received;
    uint16_t context_count;
    uint16_t pending_token;
    uint64_t last_now_ns;
    bool clock_seen;
};

enum fpga_host_result fpga_host_init(struct fpga_host *host,
                                     const struct fpga_host_io *io);
enum fpga_host_result fpga_host_probe(struct fpga_host *host,
                                      struct fpga_host_status *status,
                                      uint64_t deadline_ns);
enum fpga_host_result fpga_host_reset(struct fpga_host *host,
                                      uint64_t deadline_ns);
enum fpga_host_result fpga_host_load_model(struct fpga_host *host,
                                           const struct fpga_host_image *image,
                                           uint64_t deadline_ns);
enum fpga_host_result fpga_host_start_token(struct fpga_host *host,
                                            uint16_t token,
                                            uint64_t deadline_ns);
/* complete is true only after all 320 signed logits, in index order, and final
 * idle/context confirmation. A failed frame remains partial and must not be
 * sampled. The array is never filtered, normalized, sampled or regenerated. */
enum fpga_host_result fpga_host_read_logits(struct fpga_host *host,
                                            struct fpga_host_frame *frame,
                                            uint64_t deadline_ns);
enum fpga_host_result fpga_host_step(struct fpga_host *host, uint16_t token,
                                     struct fpga_host_frame *frame,
                                     uint64_t deadline_ns);
enum fpga_host_result fpga_host_clear_context(struct fpga_host *host,
                                              uint64_t deadline_ns);
const char *fpga_host_result_string(enum fpga_host_result result);

#ifdef __cplusplus
}
#endif
#endif
