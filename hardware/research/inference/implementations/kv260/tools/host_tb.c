/* Synthetic MMIO protocol tests only. No device is opened and no model runs. */
#include "host.h"

#include <limits.h>
#include <stdio.h>
#include <string.h>

#define CHECK(expression) do { \
    if (!(expression)) { \
        fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #expression); \
        return 1; \
    } \
} while (0)

static const uint8_t expected_banks[14] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14};
static const uint32_t expected_sizes[14] = {
    10240, 1024, 1024, 1024, 1024, 4096, 4096, 4096, 32, 32, 32, 2048, 257, 256
};
static uint8_t image_bytes[117124];
static const uint64_t long_deadline = UINT64_C(1000000000);

struct mock {
    bool configured, busy, error, saturated, valid, peeked, first_reply;
    bool freeze, bad_address, bad_count, final_saturation;
    uint32_t bank, address, count;
    size_t model_words, bank_index, bank_word, index;
    size_t reads, writes, status_reads, data_reads, index_reads;
    size_t token_writes, clear_writes, reset_writes, wait_calls;
    size_t fail_model_word, wrong_index, fault_after;
    uint32_t delay;
    uint64_t now, clock_step, last_deadline;
};

static uint32_t model_word(size_t index)
{
    if (index < 26720) {
        return (uint32_t)(index * 37 + 0x1234) & UINT32_C(0xffff);
    }
    if (index < 28768) {
        uint32_t value = (uint32_t)(index - 26720);
        return ((UINT32_C(0xabcd) + 13 * value) << 16) |
               ((UINT32_C(0x1234) + 7 * value) & UINT32_C(0xffff));
    }
    if (index < 29025) {
        return UINT32_C(0x80000000) - (uint32_t)(index - 28768) * UINT32_C(0x200000);
    }
    return UINT32_C(0x40000000) - (uint32_t)(index - 29025) * UINT32_C(0x100000);
}

static uint32_t logit_word(size_t index)
{
    static const uint32_t extrema[6] = {
        UINT32_C(0x80000000), UINT32_C(0x7fffffff), UINT32_C(0xffffffff),
        0, 1, UINT32_C(0xffff0001)
    };
    return index < 6 ? extrema[index] : (uint32_t)index * UINT32_C(0x9e3779b9);
}

static void mock_init(struct mock *mock)
{
    memset(mock, 0, sizeof(*mock));
    mock->fail_model_word = SIZE_MAX;
    mock->wrong_index = SIZE_MAX;
    mock->fault_after = SIZE_MAX;
    mock->clock_step = 1;
}

static void mock_reset_core(struct mock *mock)
{
    mock->configured = false;
    mock->busy = false;
    mock->error = false;
    mock->saturated = false;
    mock->valid = false;
    mock->peeked = false;
    mock->first_reply = false;
    mock->bank = mock->address = mock->count = 0;
    mock->model_words = mock->bank_index = mock->bank_word = mock->index = 0;
    mock->delay = 0;
}

static uint64_t mock_now(void *context)
{
    struct mock *mock = context;
    uint64_t now = mock->now;
    mock->now += mock->clock_step;
    return now;
}

static int mock_wait(void *context, uint64_t deadline)
{
    struct mock *mock = context;
    mock->wait_calls++;
    mock->last_deadline = deadline;
    return 0;
}

static uint32_t mock_status(struct mock *mock)
{
    uint32_t status = 0;
    if (mock->busy && !mock->freeze && !mock->error) {
        if (mock->index == mock->fault_after) {
            mock->error = true;
            mock->valid = true;
        } else if (!mock->valid) {
            if (mock->delay != 0) {
                mock->delay--;
            } else {
                mock->valid = true;
                if (mock->first_reply) {
                    mock->count++;
                    mock->first_reply = false;
                }
            }
        }
    }
    if (mock->configured) status |= FPGA_STATUS_CONFIGURED;
    if (mock->busy) status |= FPGA_STATUS_BUSY;
    if (mock->error) status |= FPGA_STATUS_ERROR;
    if (mock->saturated) status |= FPGA_STATUS_SATURATED;
    if (mock->valid) status |= FPGA_STATUS_LOGIT_VALID;
    if (mock->configured && !mock->busy && !mock->error && mock->count < 256) {
        status |= FPGA_STATUS_TOKEN_CAPACITY;
    }
    if (!mock->configured && !mock->busy) status |= FPGA_STATUS_MODEL_CAPACITY;
    return status;
}

static int mock_read(void *context, uint32_t offset, uint32_t *value, uint64_t deadline)
{
    struct mock *mock = context;
    mock->reads++;
    mock->last_deadline = deadline;
    switch (offset) {
    case FPGA_REG_STATUS:
        mock->status_reads++;
        *value = mock_status(mock);
        return 0;
    case FPGA_REG_MODEL_BANK: *value = mock->bank; return 0;
    case FPGA_REG_MODEL_ADDRESS:
        *value = mock->address + (mock->bad_address ? 1U : 0U);
        return 0;
    case FPGA_REG_CONTEXT_COUNT:
        *value = mock->count + (mock->bad_count && !mock->busy ? 1U : 0U);
        return 0;
    case FPGA_REG_LOGIT_INDEX:
        mock->index_reads++;
        *value = (uint32_t)mock->index + (mock->index == mock->wrong_index ? 1U : 0U);
        mock->peeked = true;
        return 0;
    case FPGA_REG_LOGIT_DATA:
        if (!mock->valid || !mock->peeked || mock->error || mock->index >= 320) return 2;
        *value = logit_word(mock->index);
        mock->index++;
        mock->data_reads++;
        mock->peeked = false;
        mock->valid = false;
        if (mock->index == 320) {
            mock->busy = false;
            mock->saturated = mock->saturated || mock->final_saturation;
        } else {
            mock->delay = (uint32_t)mock->index % 3;
        }
        return 0;
    default: return 2;
    }
}

static int mock_write(void *context, uint32_t offset, uint32_t value, uint64_t deadline)
{
    struct mock *mock = context;
    mock->writes++;
    mock->last_deadline = deadline;
    switch (offset) {
    case FPGA_REG_CONTROL:
        if (value == 2) {
            mock->reset_writes++;
            mock_reset_core(mock);
            return 0;
        }
        if (value == 1 && mock->configured && !mock->busy && !mock->error && !mock->valid) {
            mock->clear_writes++;
            mock->count = 0;
            return 0;
        }
        return 2;
    case FPGA_REG_MODEL_BANK:
        if (value >= 15 || value == 12) return 2;
        mock->bank = value;
        return 0;
    case FPGA_REG_MODEL_ADDRESS:
        if (value > UINT16_MAX) return 2;
        mock->address = value;
        return 0;
    case FPGA_REG_MODEL_DATA:
        if (mock->configured || mock->busy || mock->bank_index >= 14 ||
            mock->bank != expected_banks[mock->bank_index] || mock->address != mock->bank_word ||
            value != model_word(mock->model_words) || mock->model_words == mock->fail_model_word) {
            return 2;
        }
        mock->model_words++;
        mock->address++;
        mock->bank_word++;
        if (mock->bank_word == expected_sizes[mock->bank_index]) {
            mock->bank_word = 0;
            mock->bank_index++;
            if (mock->bank_index == 14) mock->configured = true;
        }
        return 0;
    case FPGA_REG_TOKEN:
        if (!mock->configured || mock->busy || mock->error || mock->count >= 256 ||
            value >= 320 || (mock->count == 0 && value != 256)) return 2;
        mock->token_writes++;
        mock->busy = true;
        mock->valid = false;
        mock->first_reply = true;
        mock->index = 0;
        mock->delay = 3;
        mock->saturated = false;
        return 0;
    default: return 2;
    }
}

static int setup(struct mock *mock, struct fpga_host *host)
{
    struct fpga_host_io io;
    mock_init(mock);
    io = (struct fpga_host_io){mock, mock_read, mock_write, mock_now, mock_wait, 1000000};
    return fpga_host_init(host, &io);
}

static struct fpga_host_image image(void)
{
    return (struct fpga_host_image){image_bytes, sizeof(image_bytes), 29281, true};
}

static int configured(struct mock *mock, struct fpga_host *host)
{
    struct fpga_host_image data = image();
    CHECK(setup(mock, host) == FPGA_HOST_OK);
    CHECK(fpga_host_reset(host, long_deadline) == FPGA_HOST_OK);
    CHECK(fpga_host_load_model(host, &data, long_deadline) == FPGA_HOST_OK);
    return 0;
}

static int test_model_metadata_and_verified_load(void)
{
    struct mock mock;
    struct fpga_host host;
    struct fpga_host_status status;
    struct fpga_host_image data = image();
    uint32_t words = 0;
    size_t i, before;
    CHECK(setup(&mock, &host) == FPGA_HOST_OK);
    CHECK(mock.reads == 0 && mock.writes == 0);
    CHECK(fpga_host_probe(&host, &status, long_deadline) == FPGA_HOST_OK);
    CHECK(status.raw == 0x40 && status.context_count == 0 && host.state == FPGA_HOST_UNKNOWN);
    CHECK(fpga_host_load_model(&host, &data, long_deadline) == FPGA_HOST_E_STATE);
    CHECK(fpga_host_reset(&host, long_deadline) == FPGA_HOST_OK);
    before = mock.writes;
    data.sha256_verified = false;
    CHECK(fpga_host_load_model(&host, &data, long_deadline) == FPGA_HOST_E_UNVERIFIED);
    data.sha256_verified = true;
    data.byte_count--;
    CHECK(fpga_host_load_model(&host, &data, long_deadline) == FPGA_HOST_E_IMAGE);
    data = image(); data.word_count--;
    CHECK(fpga_host_load_model(&host, &data, long_deadline) == FPGA_HOST_E_IMAGE);
    CHECK(mock.writes == before);
    data = image();
    for (i = 0; i < 14; i++) {
        CHECK(fpga_host_model_banks[i].bank == expected_banks[i]);
        CHECK(fpga_host_model_banks[i].word_count == expected_sizes[i]);
        CHECK(fpga_host_model_banks[i].image_word_offset == words);
        words += expected_sizes[i];
    }
    CHECK(words == 29281 && sizeof(image_bytes) == 4 * words);
    CHECK(fpga_host_load_model(&host, &data, long_deadline) == FPGA_HOST_OK);
    CHECK(mock.model_words == 29281 && host.model_words_written == 29281);
    CHECK(mock.bank_index == 14 && mock.bank == 14 && mock.address == 256);
    CHECK(host.state == FPGA_HOST_READY && mock.token_writes == 0);
    CHECK(mock.writes - before == 29281 + 2 * 14);
    CHECK(mock.last_deadline == long_deadline);
    CHECK(fpga_host_probe(&host, &status, long_deadline) == FPGA_HOST_OK);
    CHECK(status.raw == 0x21 && status.configured && status.token_capacity && !status.model_capacity);
    return 0;
}

static int test_all_signed_logits_bos_and_explicit_clear(void)
{
    struct mock mock;
    struct fpga_host host;
    struct fpga_host_frame frame;
    size_t i, writes;
    CHECK(configured(&mock, &host) == 0);
    writes = mock.writes;
    CHECK(fpga_host_start_token(&host, 320, long_deadline) == FPGA_HOST_E_TOKEN_RANGE);
    CHECK(fpga_host_start_token(&host, 511, long_deadline) == FPGA_HOST_E_TOKEN_RANGE);
    CHECK(fpga_host_start_token(&host, 65535, long_deadline) == FPGA_HOST_E_TOKEN_RANGE);
    CHECK(fpga_host_start_token(&host, 0, long_deadline) == FPGA_HOST_E_BOS_REQUIRED);
    CHECK(mock.writes == writes && host.state == FPGA_HOST_READY);
    mock.final_saturation = true;
    CHECK(fpga_host_step(&host, 256, &frame, long_deadline) == FPGA_HOST_OK);
    CHECK(frame.received == 320 && frame.complete && frame.saturated);
    for (i = 0; i < 320; i++) {
        uint32_t raw = logit_word(i);
        int64_t expected = raw <= INT32_MAX ? (int64_t)raw : (int64_t)raw - (INT64_C(1) << 32);
        CHECK(frame.logits[i] == expected);
    }
    CHECK(mock.token_writes == 1 && mock.data_reads == 320 && mock.index_reads == 320);
    CHECK(host.context_count == 1 && host.logits_received == 320 && host.state == FPGA_HOST_READY);
    CHECK(fpga_host_read_logits(&host, &frame, long_deadline) == FPGA_HOST_E_STATE);
    CHECK(mock.data_reads == 320 && !frame.complete);
    CHECK(fpga_host_step(&host, 319, &frame, long_deadline) == FPGA_HOST_OK);
    CHECK(fpga_host_step(&host, 257, &frame, long_deadline) == FPGA_HOST_OK);
    CHECK(host.context_count == 3 && mock.token_writes == 3);
    CHECK(fpga_host_clear_context(&host, long_deadline) == FPGA_HOST_OK);
    CHECK(mock.clear_writes == 1 && mock.reset_writes == 1 && mock.configured);
    CHECK(host.context_count == 0 && mock.model_words == 29281);
    CHECK(fpga_host_start_token(&host, 319, long_deadline) == FPGA_HOST_E_BOS_REQUIRED);
    CHECK(mock.token_writes == 3);
    return 0;
}

static int test_index_fault_and_bus_fault_never_retry(void)
{
    struct mock mock;
    struct fpga_host host;
    struct fpga_host_frame frame;
    size_t writes;
    struct fpga_host_image data = image();
    CHECK(configured(&mock, &host) == 0);
    mock.wrong_index = 17;
    CHECK(fpga_host_step(&host, 256, &frame, long_deadline) == FPGA_HOST_E_LOGIT_INDEX);
    CHECK(frame.received == 17 && !frame.complete && mock.data_reads == 17 && mock.index_reads == 18);
    CHECK(host.state == FPGA_HOST_NEEDS_RESET && mock.token_writes == 1 && mock.clear_writes == 0);
    CHECK(host.fault == FPGA_HOST_E_LOGIT_INDEX);
    writes = mock.writes;
    CHECK(fpga_host_start_token(&host, 256, long_deadline) == FPGA_HOST_E_STATE);
    CHECK(fpga_host_load_model(&host, &data, long_deadline) == FPGA_HOST_E_STATE);
    CHECK(mock.writes == writes);
    CHECK(host.fault == FPGA_HOST_E_LOGIT_INDEX);
    mock.wrong_index = SIZE_MAX;
    CHECK(fpga_host_reset(&host, long_deadline) == FPGA_HOST_OK);
    CHECK(host.fault == FPGA_HOST_OK);
    CHECK(fpga_host_load_model(&host, &data, long_deadline) == FPGA_HOST_OK);
    mock.fault_after = 9;
    CHECK(fpga_host_step(&host, 256, &frame, long_deadline) == FPGA_HOST_E_CORE);
    CHECK(frame.received == 9 && !frame.complete && host.state == FPGA_HOST_NEEDS_RESET);
    CHECK(mock.token_writes == 2 && mock.clear_writes == 0);
    CHECK(setup(&mock, &host) == FPGA_HOST_OK);
    CHECK(fpga_host_reset(&host, long_deadline) == FPGA_HOST_OK);
    mock.fail_model_word = 5;
    CHECK(fpga_host_load_model(&host, &data, long_deadline) == FPGA_HOST_E_IO);
    CHECK(host.last_io_error == 2 && host.model_words_written == 5 && mock.model_words == 5);
    writes = mock.writes;
    CHECK(fpga_host_load_model(&host, &data, long_deadline) == FPGA_HOST_E_STATE);
    CHECK(mock.writes == writes && host.state == FPGA_HOST_NEEDS_RESET);
    return 0;
}

static int test_deadline_poll_budget_and_clock(void)
{
    struct mock mock;
    struct fpga_host host;
    struct fpga_host_frame frame;
    struct fpga_host_status status;
    size_t writes, status_reads;
    uint64_t deadline;
    CHECK(configured(&mock, &host) == 0);
    CHECK(fpga_host_start_token(&host, 256, long_deadline) == FPGA_HOST_OK);
    writes = mock.writes;
    mock.freeze = true;
    deadline = mock.now + 30;
    CHECK(fpga_host_read_logits(&host, &frame, deadline) == FPGA_HOST_E_TIMEOUT);
    CHECK(!frame.complete && frame.received == 0 && mock.writes == writes && host.state == FPGA_HOST_NEEDS_RESET);
    CHECK(mock.token_writes == 1 && mock.clear_writes == 0 && mock.last_deadline == deadline);
    CHECK(configured(&mock, &host) == 0);
    CHECK(fpga_host_start_token(&host, 256, long_deadline) == FPGA_HOST_OK);
    mock.freeze = true;
    mock.clock_step = 0;
    host.io.poll_limit = 5;
    status_reads = mock.status_reads;
    CHECK(fpga_host_read_logits(&host, &frame, long_deadline) == FPGA_HOST_E_POLL_LIMIT);
    CHECK(mock.status_reads - status_reads == 5 && !frame.complete && mock.token_writes == 1);
    CHECK(configured(&mock, &host) == 0);
    mock.now = 0;
    writes = mock.writes;
    CHECK(fpga_host_probe(&host, &status, long_deadline) == FPGA_HOST_E_CLOCK);
    CHECK(mock.writes == writes && host.state == FPGA_HOST_NEEDS_RESET);
    CHECK(setup(&mock, &host) == FPGA_HOST_OK);
    CHECK(fpga_host_reset(&host, 0) == FPGA_HOST_E_TIMEOUT);
    CHECK(mock.writes == 0);
    return 0;
}

static int test_full_context_preserves_all_vocabulary_entries(void)
{
    struct mock mock;
    struct fpga_host host;
    struct fpga_host_frame frame;
    struct fpga_host_status status;
    size_t i, writes;
    CHECK(configured(&mock, &host) == 0);
    for (i = 0; i < 256; i++) {
        uint16_t token = i == 0 ? 256 : (uint16_t)((i * 73) % 320);
        CHECK(fpga_host_step(&host, token, &frame, long_deadline) == FPGA_HOST_OK);
        CHECK(frame.complete && frame.received == 320 && host.context_count == i + 1);
    }
    CHECK(mock.token_writes == 256 && mock.data_reads == 256 * 320 && mock.index_reads == 256 * 320);
    CHECK(fpga_host_probe(&host, &status, long_deadline) == FPGA_HOST_OK);
    CHECK(status.context_count == 256 && status.raw == 1 && !status.token_capacity);
    writes = mock.writes;
    CHECK(fpga_host_start_token(&host, 0, long_deadline) == FPGA_HOST_E_CONTEXT_FULL);
    CHECK(mock.writes == writes && host.state == FPGA_HOST_READY && mock.clear_writes == 0);
    CHECK(fpga_host_clear_context(&host, long_deadline) == FPGA_HOST_OK);
    CHECK(fpga_host_step(&host, 256, &frame, long_deadline) == FPGA_HOST_OK);
    CHECK(frame.complete && mock.token_writes == 257 && mock.clear_writes == 1 && mock.reset_writes == 1);
    return 0;
}

static int test_metadata_mismatch_and_exclusive_ownership(void)
{
    struct mock mock;
    struct fpga_host host;
    struct fpga_host_frame frame;
    struct fpga_host_image data = image();
    size_t writes;
    CHECK(setup(&mock, &host) == FPGA_HOST_OK);
    CHECK(fpga_host_reset(&host, long_deadline) == FPGA_HOST_OK);
    mock.bad_address = true;
    CHECK(fpga_host_load_model(&host, &data, long_deadline) == FPGA_HOST_E_PROTOCOL);
    CHECK(host.state == FPGA_HOST_NEEDS_RESET && mock.model_words == 10240 && mock.bank_index == 1);
    CHECK(configured(&mock, &host) == 0);
    mock.count = 1;
    writes = mock.writes;
    CHECK(fpga_host_start_token(&host, 256, long_deadline) == FPGA_HOST_E_PROTOCOL);
    CHECK(mock.writes == writes && mock.token_writes == 0);
    CHECK(configured(&mock, &host) == 0);
    mock.bad_count = true;
    CHECK(fpga_host_start_token(&host, 256, long_deadline) == FPGA_HOST_E_PROTOCOL);
    mock.bad_count = false;
    CHECK(configured(&mock, &host) == 0);
    CHECK(fpga_host_start_token(&host, 256, long_deadline) == FPGA_HOST_OK);
    mock.bad_count = true;
    CHECK(fpga_host_read_logits(&host, &frame, long_deadline) == FPGA_HOST_E_PROTOCOL);
    CHECK(frame.received == 320 && !frame.complete && host.state == FPGA_HOST_NEEDS_RESET);
    return 0;
}

int main(void)
{
    size_t i;
    int (*const tests[])(void) = {
        test_model_metadata_and_verified_load,
        test_all_signed_logits_bos_and_explicit_clear,
        test_index_fault_and_bus_fault_never_retry,
        test_deadline_poll_budget_and_clock,
        test_full_context_preserves_all_vocabulary_entries,
        test_metadata_mismatch_and_exclusive_ownership
    };
    for (i = 0; i < 29281; i++) {
        uint32_t value = model_word(i);
        image_bytes[4 * i] = (uint8_t)value;
        image_bytes[4 * i + 1] = (uint8_t)(value >> 8);
        image_bytes[4 * i + 2] = (uint8_t)(value >> 16);
        image_bytes[4 * i + 3] = (uint8_t)(value >> 24);
    }
    for (i = 0; i < sizeof(tests) / sizeof(tests[0]); i++) {
        if (tests[i]() != 0) return 1;
    }
    printf("PASS host mock suites=%zu model_words=29281 vocabulary=320 context_limit=256\n",
           sizeof(tests) / sizeof(tests[0]));
    return 0;
}
