#include "host.h"

#include <limits.h>
#include <string.h>

_Static_assert(CHAR_BIT == 8, "The packed model image uses 8-bit bytes");
_Static_assert(UINT32_MAX == UINT32_C(0xffffffff), "32-bit words required");

const struct fpga_host_model_bank fpga_host_model_banks[FPGA_HOST_MODEL_BANKS] = {
    {0, 10240, 0}, {1, 1024, 10240}, {2, 1024, 11264}, {3, 1024, 12288},
    {4, 1024, 13312}, {5, 4096, 14336}, {6, 4096, 18432}, {7, 4096, 22528},
    {8, 32, 26624}, {9, 32, 26656}, {10, 32, 26688}, {11, 2048, 26720},
    {13, 257, 28768}, {14, 256, 29025}
};

struct operation {
    uint64_t deadline;
    uint32_t polls;
};

static bool valid_host(const struct fpga_host *host)
{
    return host != NULL && host->io.read32 != NULL &&
           host->io.write32 != NULL && host->io.now_ns != NULL &&
           host->io.poll_limit != 0;
}

static enum fpga_host_result finish(struct fpga_host *host,
                                     enum fpga_host_result result, bool invalidate)
{
    if (host != NULL) {
        host->last_error = result;
        if (invalidate) {
            if (host->fault == FPGA_HOST_OK) {
                host->fault = result;
            }
            host->state = FPGA_HOST_NEEDS_RESET;
        }
    }
    return result;
}

static enum fpga_host_result check_time(struct fpga_host *host,
                                         const struct operation *operation)
{
    uint64_t now = host->io.now_ns(host->io.context);
    if (host->clock_seen && now < host->last_now_ns) {
        return FPGA_HOST_E_CLOCK;
    }
    host->clock_seen = true;
    host->last_now_ns = now;
    return now >= operation->deadline ? FPGA_HOST_E_TIMEOUT : FPGA_HOST_OK;
}

static enum fpga_host_result read_word(struct fpga_host *host,
                                        const struct operation *operation,
                                        uint32_t offset, uint32_t *value)
{
    enum fpga_host_result result = check_time(host, operation);
    int error;
    if (result != FPGA_HOST_OK) {
        return result;
    }
    error = host->io.read32(host->io.context, offset, value, operation->deadline);
    host->last_io_error = error;
    if (error != 0) {
        return FPGA_HOST_E_IO;
    }
    return check_time(host, operation);
}

static enum fpga_host_result write_word(struct fpga_host *host,
                                         const struct operation *operation,
                                         uint32_t offset, uint32_t value)
{
    enum fpga_host_result result = check_time(host, operation);
    int error;
    if (result != FPGA_HOST_OK) {
        return result;
    }
    error = host->io.write32(host->io.context, offset, value, operation->deadline);
    host->last_io_error = error;
    if (error != 0) {
        return FPGA_HOST_E_IO;
    }
    return check_time(host, operation);
}

static enum fpga_host_result wait_poll(struct fpga_host *host,
                                        const struct operation *operation)
{
    enum fpga_host_result result = check_time(host, operation);
    int error;
    if (result != FPGA_HOST_OK || host->io.poll_wait == NULL) {
        return result;
    }
    error = host->io.poll_wait(host->io.context, operation->deadline);
    host->last_io_error = error;
    if (error != 0) {
        return FPGA_HOST_E_IO;
    }
    return check_time(host, operation);
}

static enum fpga_host_result read_status(struct fpga_host *host,
                                          struct operation *operation,
                                          uint32_t *status)
{
    enum fpga_host_result result;
    if (operation->polls >= host->io.poll_limit) {
        return FPGA_HOST_E_POLL_LIMIT;
    }
    operation->polls++;
    result = read_word(host, operation, FPGA_REG_STATUS, status);
    if (result != FPGA_HOST_OK) {
        return result;
    }
    host->last_status = *status;
    return (*status & ~FPGA_STATUS_KNOWN_BITS) != 0 ?
           FPGA_HOST_E_PROTOCOL : FPGA_HOST_OK;
}

static enum fpga_host_result read_count(struct fpga_host *host,
                                         const struct operation *operation,
                                         uint32_t *count)
{
    enum fpga_host_result result = read_word(host, operation,
                                              FPGA_REG_CONTEXT_COUNT, count);
    if (result != FPGA_HOST_OK) {
        return result;
    }
    host->last_context_count = *count;
    return *count > FPGA_HOST_CONTEXT_LIMIT ? FPGA_HOST_E_PROTOCOL : FPGA_HOST_OK;
}

static uint32_t little_endian_word(const uint8_t *bytes)
{
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8) |
           ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}

enum fpga_host_result fpga_host_init(struct fpga_host *host,
                                     const struct fpga_host_io *io)
{
    struct fpga_host_io saved;
    if (host == NULL || io == NULL || io->read32 == NULL ||
        io->write32 == NULL || io->now_ns == NULL) {
        return FPGA_HOST_E_ARGUMENT;
    }
    saved = *io;
    memset(host, 0, sizeof(*host));
    host->io = saved;
    if (host->io.poll_limit == 0) {
        host->io.poll_limit = FPGA_HOST_DEFAULT_POLL_LIMIT;
    }
    host->state = FPGA_HOST_UNKNOWN;
    return FPGA_HOST_OK;
}

enum fpga_host_result fpga_host_probe(struct fpga_host *host,
                                      struct fpga_host_status *status,
                                      uint64_t deadline_ns)
{
    struct operation operation = {deadline_ns, 0};
    uint32_t raw = 0;
    uint32_t count = 0;
    enum fpga_host_result result;
    if (!valid_host(host) || status == NULL) {
        return finish(host, FPGA_HOST_E_ARGUMENT, false);
    }
    result = read_status(host, &operation, &raw);
    if (result == FPGA_HOST_OK) {
        result = read_count(host, &operation, &count);
    }
    if (result != FPGA_HOST_OK) {
        return finish(host, result, true);
    }
    status->raw = raw;
    status->context_count = (uint16_t)count;
    status->configured = (raw & FPGA_STATUS_CONFIGURED) != 0;
    status->busy = (raw & FPGA_STATUS_BUSY) != 0;
    status->error = (raw & FPGA_STATUS_ERROR) != 0;
    status->saturated = (raw & FPGA_STATUS_SATURATED) != 0;
    status->logit_valid = (raw & FPGA_STATUS_LOGIT_VALID) != 0;
    status->token_capacity = (raw & FPGA_STATUS_TOKEN_CAPACITY) != 0;
    status->model_capacity = (raw & FPGA_STATUS_MODEL_CAPACITY) != 0;
    return finish(host, FPGA_HOST_OK, false);
}

enum fpga_host_result fpga_host_reset(struct fpga_host *host,
                                      uint64_t deadline_ns)
{
    struct operation operation = {deadline_ns, 0};
    enum fpga_host_result result;
    uint32_t status, count, bank, address;
    if (!valid_host(host)) {
        return finish(host, FPGA_HOST_E_ARGUMENT, false);
    }
    result = write_word(host, &operation, FPGA_REG_CONTROL, FPGA_CONTROL_RESET);
    while (result == FPGA_HOST_OK) {
        result = read_status(host, &operation, &status);
        if (result != FPGA_HOST_OK) {
            break;
        }
        if ((status & (FPGA_STATUS_CONFIGURED | FPGA_STATUS_BUSY |
                       FPGA_STATUS_ERROR | FPGA_STATUS_LOGIT_VALID)) == 0 &&
            (status & FPGA_STATUS_MODEL_CAPACITY) != 0) {
            result = read_count(host, &operation, &count);
            if (result == FPGA_HOST_OK) {
                result = read_word(host, &operation, FPGA_REG_MODEL_BANK, &bank);
            }
            if (result == FPGA_HOST_OK) {
                result = read_word(host, &operation, FPGA_REG_MODEL_ADDRESS, &address);
            }
            if (result == FPGA_HOST_OK && (count != 0 || bank != 0 || address != 0)) {
                result = FPGA_HOST_E_PROTOCOL;
            }
            if (result == FPGA_HOST_OK) {
                host->state = FPGA_HOST_EMPTY;
                host->fault = FPGA_HOST_OK;
                host->model_words_written = 0;
                host->logits_received = 0;
                host->context_count = 0;
                host->pending_token = 0;
                return finish(host, FPGA_HOST_OK, false);
            }
            break;
        }
        result = wait_poll(host, &operation);
    }
    return finish(host, result, true);
}

enum fpga_host_result fpga_host_load_model(struct fpga_host *host,
                                           const struct fpga_host_image *image,
                                           uint64_t deadline_ns)
{
    struct operation operation = {deadline_ns, 0};
    enum fpga_host_result result;
    uint32_t status, bank, address;
    size_t i;
    if (!valid_host(host) || image == NULL || image->little_endian_bytes == NULL) {
        return finish(host, FPGA_HOST_E_ARGUMENT, false);
    }
    if (!image->sha256_verified) {
        return finish(host, FPGA_HOST_E_UNVERIFIED, false);
    }
    if (image->byte_count != FPGA_HOST_MODEL_BYTES || image->word_count != FPGA_HOST_MODEL_WORDS) {
        return finish(host, FPGA_HOST_E_IMAGE, false);
    }
    if (host->state != FPGA_HOST_EMPTY || host->model_words_written != 0) {
        return finish(host, FPGA_HOST_E_STATE, false);
    }
    for (i = 0; i < FPGA_HOST_MODEL_BANKS; i++) {
        const struct fpga_host_model_bank *layout = &fpga_host_model_banks[i];
        for (;;) {
            result = read_status(host, &operation, &status);
            if (result != FPGA_HOST_OK || (status & FPGA_STATUS_ERROR) != 0) {
                return finish(host, result != FPGA_HOST_OK ? result : FPGA_HOST_E_CORE, true);
            }
            if ((status & FPGA_STATUS_CONFIGURED) != 0) {
                return finish(host, FPGA_HOST_E_PROTOCOL, true);
            }
            if ((status & FPGA_STATUS_MODEL_CAPACITY) != 0 && (status & FPGA_STATUS_BUSY) == 0) {
                break;
            }
            result = wait_poll(host, &operation);
            if (result != FPGA_HOST_OK) {
                return finish(host, result, true);
            }
        }
        result = write_word(host, &operation, FPGA_REG_MODEL_BANK, layout->bank);
        if (result == FPGA_HOST_OK) {
            result = write_word(host, &operation, FPGA_REG_MODEL_ADDRESS, 0);
        }
        if (result != FPGA_HOST_OK) {
            return finish(host, result, true);
        }
        for (address = 0; address < layout->word_count; address++) {
            size_t word_index = (size_t)layout->image_word_offset + address;
            uint32_t word = little_endian_word(image->little_endian_bytes + 4 * word_index);
            result = write_word(host, &operation, FPGA_REG_MODEL_DATA, word);
            if (result != FPGA_HOST_OK) {
                return finish(host, result, true);
            }
            host->model_words_written++;
        }
        result = read_word(host, &operation, FPGA_REG_MODEL_BANK, &bank);
        if (result == FPGA_HOST_OK) {
            result = read_word(host, &operation, FPGA_REG_MODEL_ADDRESS, &address);
        }
        if (result != FPGA_HOST_OK || bank != layout->bank || address != layout->word_count) {
            return finish(host, result != FPGA_HOST_OK ? result : FPGA_HOST_E_PROTOCOL, true);
        }
    }
    for (;;) {
        result = read_status(host, &operation, &status);
        if (result != FPGA_HOST_OK || (status & FPGA_STATUS_ERROR) != 0) {
            return finish(host, result != FPGA_HOST_OK ? result : FPGA_HOST_E_CORE, true);
        }
        if ((status & FPGA_STATUS_CONFIGURED) != 0 &&
            (status & (FPGA_STATUS_BUSY | FPGA_STATUS_LOGIT_VALID)) == 0) {
            uint32_t count;
            result = read_count(host, &operation, &count);
            if (result != FPGA_HOST_OK || count != 0) {
                return finish(host, result != FPGA_HOST_OK ? result : FPGA_HOST_E_PROTOCOL, true);
            }
            host->state = FPGA_HOST_READY;
            host->context_count = 0;
            return finish(host, FPGA_HOST_OK, false);
        }
        result = wait_poll(host, &operation);
        if (result != FPGA_HOST_OK) {
            return finish(host, result, true);
        }
    }
}

enum fpga_host_result fpga_host_start_token(struct fpga_host *host,
                                            uint16_t token,
                                            uint64_t deadline_ns)
{
    struct operation operation = {deadline_ns, 0};
    enum fpga_host_result result;
    uint32_t status, count;
    if (!valid_host(host)) {
        return finish(host, FPGA_HOST_E_ARGUMENT, false);
    }
    if (token >= FPGA_HOST_VOCABULARY) {
        return finish(host, FPGA_HOST_E_TOKEN_RANGE, false);
    }
    if (host->state != FPGA_HOST_READY) {
        return finish(host, FPGA_HOST_E_STATE, false);
    }
    if (host->context_count == 0 && token != FPGA_HOST_BOS) {
        return finish(host, FPGA_HOST_E_BOS_REQUIRED, false);
    }
    for (;;) {
        result = read_status(host, &operation, &status);
        if (result != FPGA_HOST_OK || (status & FPGA_STATUS_ERROR) != 0) {
            return finish(host, result != FPGA_HOST_OK ? result : FPGA_HOST_E_CORE, true);
        }
        if ((status & FPGA_STATUS_CONFIGURED) == 0) {
            return finish(host, FPGA_HOST_E_PROTOCOL, true);
        }
        result = read_count(host, &operation, &count);
        if (result != FPGA_HOST_OK || count != host->context_count) {
            return finish(host, result != FPGA_HOST_OK ? result : FPGA_HOST_E_PROTOCOL, true);
        }
        if (count == FPGA_HOST_CONTEXT_LIMIT) {
            return finish(host, FPGA_HOST_E_CONTEXT_FULL, false);
        }
        if ((status & FPGA_STATUS_TOKEN_CAPACITY) != 0) {
            if ((status & (FPGA_STATUS_BUSY | FPGA_STATUS_LOGIT_VALID)) != 0) {
                return finish(host, FPGA_HOST_E_PROTOCOL, true);
            }
            break;
        }
        result = wait_poll(host, &operation);
        if (result != FPGA_HOST_OK) {
            return finish(host, result, true);
        }
    }
    result = write_word(host, &operation, FPGA_REG_TOKEN, token);
    if (result != FPGA_HOST_OK) {
        return finish(host, result, true);
    }
    host->pending_token = token;
    host->logits_received = 0;
    host->state = FPGA_HOST_WAITING_LOGITS;
    return finish(host, FPGA_HOST_OK, false);
}

enum fpga_host_result fpga_host_read_logits(struct fpga_host *host,
                                            struct fpga_host_frame *frame,
                                            uint64_t deadline_ns)
{
    struct operation operation = {deadline_ns, 0};
    enum fpga_host_result result;
    uint32_t status, index, raw, count;
    size_t i;
    if (frame != NULL) {
        frame->received = 0;
        frame->complete = false;
        frame->saturated = false;
    }
    if (!valid_host(host) || frame == NULL) {
        return finish(host, FPGA_HOST_E_ARGUMENT, false);
    }
    if (host->state != FPGA_HOST_WAITING_LOGITS || host->logits_received != 0) {
        return finish(host, FPGA_HOST_E_STATE, false);
    }
    for (i = 0; i < FPGA_HOST_LOGITS; i++) {
        for (;;) {
            result = read_status(host, &operation, &status);
            if (result != FPGA_HOST_OK || (status & FPGA_STATUS_ERROR) != 0) {
                return finish(host, result != FPGA_HOST_OK ? result : FPGA_HOST_E_CORE, true);
            }
            if ((status & FPGA_STATUS_CONFIGURED) == 0) {
                return finish(host, FPGA_HOST_E_PROTOCOL, true);
            }
            frame->saturated = frame->saturated || (status & FPGA_STATUS_SATURATED) != 0;
            if ((status & FPGA_STATUS_LOGIT_VALID) != 0) {
                break;
            }
            result = wait_poll(host, &operation);
            if (result != FPGA_HOST_OK) {
                return finish(host, result, true);
            }
        }
        result = read_word(host, &operation, FPGA_REG_LOGIT_INDEX, &index);
        if (result != FPGA_HOST_OK) {
            return finish(host, result, true);
        }
        host->last_logit_index = index;
        if (index != i) {
            return finish(host, FPGA_HOST_E_LOGIT_INDEX, true);
        }
        result = read_word(host, &operation, FPGA_REG_LOGIT_DATA, &raw);
        if (result != FPGA_HOST_OK) {
            return finish(host, result, true);
        }
        /* Avoid implementation-defined unsigned-to-signed narrowing. */
        frame->logits[i] = (int32_t)(raw <= INT32_MAX ? (int64_t)raw :
                            (int64_t)raw - (INT64_C(1) << 32));
        frame->received++;
        host->logits_received++;
    }
    for (;;) {
        result = read_status(host, &operation, &status);
        if (result != FPGA_HOST_OK || (status & FPGA_STATUS_ERROR) != 0) {
            return finish(host, result != FPGA_HOST_OK ? result : FPGA_HOST_E_CORE, true);
        }
        if ((status & FPGA_STATUS_CONFIGURED) == 0) {
            return finish(host, FPGA_HOST_E_PROTOCOL, true);
        }
        frame->saturated = frame->saturated || (status & FPGA_STATUS_SATURATED) != 0;
        if ((status & (FPGA_STATUS_BUSY | FPGA_STATUS_LOGIT_VALID)) == 0) {
            result = read_count(host, &operation, &count);
            if (result != FPGA_HOST_OK || count != (uint32_t)host->context_count + 1) {
                return finish(host, result != FPGA_HOST_OK ? result : FPGA_HOST_E_PROTOCOL, true);
            }
            host->context_count = (uint16_t)count;
            host->state = FPGA_HOST_READY;
            frame->complete = true;
            return finish(host, FPGA_HOST_OK, false);
        }
        result = wait_poll(host, &operation);
        if (result != FPGA_HOST_OK) {
            return finish(host, result, true);
        }
    }
}

enum fpga_host_result fpga_host_step(struct fpga_host *host, uint16_t token,
                                     struct fpga_host_frame *frame,
                                     uint64_t deadline_ns)
{
    enum fpga_host_result result;
    if (frame == NULL) {
        return finish(host, FPGA_HOST_E_ARGUMENT, false);
    }
    frame->received = 0;
    frame->complete = false;
    frame->saturated = false;
    result = fpga_host_start_token(host, token, deadline_ns);
    if (result != FPGA_HOST_OK) {
        return result;
    }
    return fpga_host_read_logits(host, frame, deadline_ns);
}

enum fpga_host_result fpga_host_clear_context(struct fpga_host *host,
                                              uint64_t deadline_ns)
{
    struct operation operation = {deadline_ns, 0};
    enum fpga_host_result result;
    uint32_t status, count;
    if (!valid_host(host)) {
        return finish(host, FPGA_HOST_E_ARGUMENT, false);
    }
    if (host->state != FPGA_HOST_READY) {
        return finish(host, FPGA_HOST_E_STATE, false);
    }
    result = read_status(host, &operation, &status);
    if (result != FPGA_HOST_OK || (status & FPGA_STATUS_ERROR) != 0) {
        return finish(host, result != FPGA_HOST_OK ? result : FPGA_HOST_E_CORE, true);
    }
    if ((status & FPGA_STATUS_CONFIGURED) == 0 ||
        (status & (FPGA_STATUS_BUSY | FPGA_STATUS_LOGIT_VALID)) != 0) {
        return finish(host, FPGA_HOST_E_STATE, false);
    }
    result = write_word(host, &operation, FPGA_REG_CONTROL, FPGA_CONTROL_CLEAR_CONTEXT);
    while (result == FPGA_HOST_OK) {
        result = read_status(host, &operation, &status);
        if (result != FPGA_HOST_OK || (status & FPGA_STATUS_ERROR) != 0) {
            return finish(host, result != FPGA_HOST_OK ? result : FPGA_HOST_E_CORE, true);
        }
        if ((status & FPGA_STATUS_CONFIGURED) == 0) {
            return finish(host, FPGA_HOST_E_PROTOCOL, true);
        }
        result = read_count(host, &operation, &count);
        if (result != FPGA_HOST_OK) {
            return finish(host, result, true);
        }
        if (count == 0 && (status & (FPGA_STATUS_BUSY | FPGA_STATUS_LOGIT_VALID)) == 0) {
            host->context_count = 0;
            host->logits_received = 0;
            return finish(host, FPGA_HOST_OK, false);
        }
        result = wait_poll(host, &operation);
    }
    return finish(host, result, true);
}

const char *fpga_host_result_string(enum fpga_host_result result)
{
    switch (result) {
    case FPGA_HOST_OK: return "complete";
    case FPGA_HOST_E_ARGUMENT: return "invalid argument or callback";
    case FPGA_HOST_E_UNVERIFIED: return "model image lacks caller SHA256 verification";
    case FPGA_HOST_E_IMAGE: return "model image length or word count differs";
    case FPGA_HOST_E_STATE: return "operation is invalid in the current state";
    case FPGA_HOST_E_TIMEOUT: return "absolute deadline reached";
    case FPGA_HOST_E_IO: return "MMIO callback reported a bus failure";
    case FPGA_HOST_E_CORE: return "transformer reported an arithmetic or state fault";
    case FPGA_HOST_E_LOGIT_INDEX: return "logit index differs; data was not consumed";
    case FPGA_HOST_E_CONTEXT_FULL: return "context contains 256 tokens";
    case FPGA_HOST_E_BOS_REQUIRED: return "the first token must be BOS 256";
    case FPGA_HOST_E_PROTOCOL: return "device metadata or state sequence differs";
    case FPGA_HOST_E_CLOCK: return "monotonic clock moved backwards";
    case FPGA_HOST_E_POLL_LIMIT: return "finite status poll limit reached";
    case FPGA_HOST_E_TOKEN_RANGE: return "token is outside the 320-entry vocabulary";
    default: return "unknown host result";
    }
}
