#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define DEFAULT_BASE 0xA0000000ULL
#define MAP_SIZE 0x10000U
#define REG_ID 0x0000U
#define REG_CONTROL 0x0004U
#define REG_STATUS 0x0008U
#define REG_CYCLES 0x000cU
#define REG_HEAD_DIM 0x0010U
#define REG_LANES 0x0014U
#define REG_BETA 0x0018U
#define Q_BASE 0x1000U
#define K_BASE 0x1400U
#define V_BASE 0x1800U
#define ALPHA_BASE 0x1c00U
#define OUTPUT_BASE 0x2000U
#define STATE_WIDTH 24
#define STATE_FRAC 18
#define VECTOR_FRAC 6
#define GATE_FRAC 8

typedef struct {
    int8_t *q;
    int8_t *k;
    int8_t *v;
    uint8_t *alpha;
    uint8_t beta;
} token_inputs;

static uint32_t lcg_step(uint32_t *state) {
    *state = *state * 1664525U + 1013904223U;
    return *state;
}

static int64_t arithmetic_shift_right(int64_t value, unsigned shift) {
    if (value >= 0) return value >> shift;
    return -(((-value) + ((1LL << shift) - 1)) >> shift);
}

static int32_t saturate_signed(int64_t value, unsigned width) {
    int64_t minimum = -(1LL << (width - 1));
    int64_t maximum = (1LL << (width - 1)) - 1;
    if (value < minimum) return (int32_t)minimum;
    if (value > maximum) return (int32_t)maximum;
    return (int32_t)value;
}

static void generate_token(token_inputs *token, uint32_t *seed, unsigned head_dim) {
    int8_t *vectors[] = {token->q, token->k, token->v};
    for (unsigned vector = 0; vector < 3; vector++) {
        for (unsigned index = 0; index < head_dim; index++) {
            uint32_t value = lcg_step(seed);
            vectors[vector][index] = (int8_t)((int)((value >> 28) & 0xfU) - 8);
        }
    }
    for (unsigned index = 0; index < head_dim; index++) {
        uint32_t value = lcg_step(seed);
        token->alpha[index] = (uint8_t)(224U + ((value >> 27) & 0x1fU));
    }
    token->beta = (uint8_t)(1U + ((lcg_step(seed) >> 28) & 0xfU));
}

static void reference_step(const token_inputs *token, int32_t *state, int32_t *output, unsigned head_dim) {
    int32_t *scaled = calloc(head_dim, sizeof(*scaled));
    int32_t *next_column = calloc(head_dim, sizeof(*next_column));
    if (!scaled || !next_column) {
        fprintf(stderr, "reference allocation failed\n");
        exit(2);
    }
    for (unsigned column = 0; column < head_dim; column++) {
        int64_t dot = 0;
        for (unsigned row = 0; row < head_dim; row++) {
            int64_t value = arithmetic_shift_right((int64_t)state[row * head_dim + column] * token->alpha[row], GATE_FRAC);
            scaled[row] = saturate_signed(value, STATE_WIDTH);
            dot += (int64_t)token->k[row] * scaled[row];
        }
        int64_t projection = arithmetic_shift_right(dot, VECTOR_FRAC);
        int64_t delta = (int64_t)token->v[column] * (1LL << (STATE_FRAC - VECTOR_FRAC)) - projection;
        int64_t output_sum = 0;
        for (unsigned row = 0; row < head_dim; row++) {
            int64_t update = arithmetic_shift_right((int64_t)token->beta * token->k[row] * delta, GATE_FRAC + VECTOR_FRAC);
            next_column[row] = saturate_signed((int64_t)scaled[row] + update, STATE_WIDTH);
            state[row * head_dim + column] = next_column[row];
            output_sum += (int64_t)token->q[row] * next_column[row];
        }
        output[column] = saturate_signed(arithmetic_shift_right(output_sum, VECTOR_FRAC), 32);
    }
    free(scaled);
    free(next_column);
}

static inline void mmio_write(volatile uint32_t *base, unsigned offset, uint32_t value) {
    base[offset / 4] = value;
    __sync_synchronize();
}

static inline uint32_t mmio_read(volatile uint32_t *base, unsigned offset) {
    uint32_t value = base[offset / 4];
    __sync_synchronize();
    return value;
}

static bool wait_done(volatile uint32_t *base, uint64_t timeout_ns) {
    struct timespec start;
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &start);
    for (;;) {
        uint32_t status = mmio_read(base, REG_STATUS);
        if ((status & 3U) == 2U) return true;
        clock_gettime(CLOCK_MONOTONIC, &now);
        uint64_t elapsed = (uint64_t)(now.tv_sec - start.tv_sec) * 1000000000ULL + (uint64_t)(now.tv_nsec - start.tv_nsec);
        if (elapsed > timeout_ns) return false;
    }
}

static uint64_t monotonic_ns(void) {
    struct timespec value;
    clock_gettime(CLOCK_MONOTONIC, &value);
    return (uint64_t)value.tv_sec * 1000000000ULL + (uint64_t)value.tv_nsec;
}

static int run_reference_only(unsigned head_dim, unsigned token_count, uint32_t seed) {
    token_inputs token = {
        .q = calloc(head_dim, sizeof(int8_t)),
        .k = calloc(head_dim, sizeof(int8_t)),
        .v = calloc(head_dim, sizeof(int8_t)),
        .alpha = calloc(head_dim, sizeof(uint8_t)),
        .beta = 0,
    };
    int32_t *state = calloc((size_t)head_dim * head_dim, sizeof(int32_t));
    int32_t *output = calloc(head_dim, sizeof(int32_t));
    if (!token.q || !token.k || !token.v || !token.alpha || !state || !output) return 2;

    printf("{\"head_dim\":%u,\"outputs\":[", head_dim);
    for (unsigned token_index = 0; token_index < token_count; token_index++) {
        generate_token(&token, &seed, head_dim);
        reference_step(&token, state, output, head_dim);
        if (token_index) putchar(',');
        putchar('[');
        for (unsigned index = 0; index < head_dim; index++) {
            if (index) putchar(',');
            printf("%d", output[index]);
        }
        putchar(']');
    }
    printf("]}\n");

    free(token.q);
    free(token.k);
    free(token.v);
    free(token.alpha);
    free(state);
    free(output);
    return 0;
}

int main(int argc, char **argv) {
    uint64_t physical_base = DEFAULT_BASE;
    unsigned token_count = 8;
    unsigned reference_head_dim = 16;
    uint32_t seed = 0x4b444131U;
    bool reference_only = false;
    for (int arg = 1; arg < argc; arg++) {
        if (!strcmp(argv[arg], "--base") && arg + 1 < argc) physical_base = strtoull(argv[++arg], NULL, 0);
        else if (!strcmp(argv[arg], "--tokens") && arg + 1 < argc) token_count = (unsigned)strtoul(argv[++arg], NULL, 0);
        else if (!strcmp(argv[arg], "--seed") && arg + 1 < argc) seed = (uint32_t)strtoul(argv[++arg], NULL, 0);
        else if (!strcmp(argv[arg], "--head-dim") && arg + 1 < argc) reference_head_dim = (unsigned)strtoul(argv[++arg], NULL, 0);
        else if (!strcmp(argv[arg], "--reference-only")) reference_only = true;
        else {
            fprintf(stderr, "usage: %s [--base address] [--tokens count] [--seed value] [--reference-only --head-dim value]\n", argv[0]);
            return 2;
        }
    }
    if (reference_only) return run_reference_only(reference_head_dim, token_count, seed);

    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) {
        fprintf(stderr, "open /dev/mem failed: %s\n", strerror(errno));
        return 2;
    }
    void *mapping = mmap(NULL, MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, (off_t)physical_base);
    if (mapping == MAP_FAILED) {
        fprintf(stderr, "mmap failed: %s\n", strerror(errno));
        close(fd);
        return 2;
    }
    volatile uint32_t *mmio = mapping;
    uint32_t id = mmio_read(mmio, REG_ID);
    if (id != 0x4b444131U) {
        fprintf(stderr, "KDA ID mismatch at 0x%" PRIx64 ": got 0x%08x\n", physical_base, id);
        munmap(mapping, MAP_SIZE);
        close(fd);
        return 3;
    }
    unsigned head_dim = mmio_read(mmio, REG_HEAD_DIM);
    unsigned lanes = mmio_read(mmio, REG_LANES);
    if (head_dim == 0 || head_dim > 256 || lanes == 0 || head_dim % lanes != 0) {
        fprintf(stderr, "invalid hardware configuration head_dim=%u lanes=%u\n", head_dim, lanes);
        return 3;
    }

    token_inputs token = {
        .q = calloc(head_dim, sizeof(int8_t)),
        .k = calloc(head_dim, sizeof(int8_t)),
        .v = calloc(head_dim, sizeof(int8_t)),
        .alpha = calloc(head_dim, sizeof(uint8_t)),
        .beta = 0,
    };
    int32_t *state = calloc((size_t)head_dim * head_dim, sizeof(int32_t));
    int32_t *expected = calloc(head_dim, sizeof(int32_t));
    if (!token.q || !token.k || !token.v || !token.alpha || !state || !expected) {
        fprintf(stderr, "test allocation failed\n");
        return 2;
    }

    mmio_write(mmio, REG_CONTROL, 2U);
    if (!wait_done(mmio, 1000000000ULL)) {
        fprintf(stderr, "state clear timed out status=0x%08x cycles=%u\n",
                mmio_read(mmio, REG_STATUS), mmio_read(mmio, REG_CYCLES));
        return 4;
    }

    unsigned mismatches = 0;
    uint64_t total_wall_ns = 0;
    uint64_t total_cycles = 0;
    for (unsigned token_index = 0; token_index < token_count; token_index++) {
        generate_token(&token, &seed, head_dim);
        reference_step(&token, state, expected, head_dim);
        for (unsigned index = 0; index < head_dim; index++) {
            mmio_write(mmio, Q_BASE + index * 4, (uint8_t)token.q[index]);
            mmio_write(mmio, K_BASE + index * 4, (uint8_t)token.k[index]);
            mmio_write(mmio, V_BASE + index * 4, (uint8_t)token.v[index]);
            mmio_write(mmio, ALPHA_BASE + index * 4, token.alpha[index]);
        }
        mmio_write(mmio, REG_BETA, token.beta);
        uint64_t start_ns = monotonic_ns();
        mmio_write(mmio, REG_CONTROL, 1U);
        if (!wait_done(mmio, 1000000000ULL)) {
            fprintf(stderr, "token %u timed out status=0x%08x cycles=%u\n",
                    token_index, mmio_read(mmio, REG_STATUS), mmio_read(mmio, REG_CYCLES));
            return 4;
        }
        uint64_t elapsed_ns = monotonic_ns() - start_ns;
        uint32_t measured_cycles = mmio_read(mmio, REG_CYCLES);
        total_wall_ns += elapsed_ns;
        total_cycles += measured_cycles;
        for (unsigned index = 0; index < head_dim; index++) {
            int32_t actual = (int32_t)mmio_read(mmio, OUTPUT_BASE + index * 4);
            if (actual != expected[index]) {
                if (mismatches < 10) fprintf(stderr, "mismatch token=%u index=%u actual=%d expected=%d\n", token_index, index, actual, expected[index]);
                mismatches++;
            }
        }
    }

    printf("{\"evidence_class\":\"measured_fpga\",\"id\":\"0x%08x\",\"head_dim\":%u,\"lanes\":%u,\"tokens\":%u,\"mismatches\":%u,\"cycles_per_token\":%.2f,\"host_wall_us_per_token\":%.2f}\n",
           id, head_dim, lanes, token_count, mismatches,
           token_count ? (double)total_cycles / token_count : 0.0,
           token_count ? (double)total_wall_ns / token_count / 1000.0 : 0.0);

    free(token.q);
    free(token.k);
    free(token.v);
    free(token.alpha);
    free(state);
    free(expected);
    munmap(mapping, MAP_SIZE);
    close(fd);
    return mismatches ? 5 : 0;
}
