#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

enum {
  ROWS = 384,
  REQUESTS = 32,
  DRAFT_TOKENS = 12,
  VOCAB = 262144,
  VOCAB_TILE = 256
};

static int argmax_control(const float *row) {
  int best_token = 0;
  float best_value = row[0];
  for (int token = 1; token < VOCAB; ++token) {
    if (row[token] > best_value) {
      best_value = row[token];
      best_token = token;
    }
  }
  return best_token;
}

static int argmax_tiled(const float *row) {
  int best_token = 0;
  float best_value = row[0];
  for (int tile = 0; tile < VOCAB; tile += VOCAB_TILE) {
    for (int token = tile; token < tile + VOCAB_TILE; ++token) {
      float value = row[token];
      if (value > best_value || (value == best_value && token < best_token)) {
        best_value = value;
        best_token = token;
      }
    }
  }
  return best_token;
}

int main(void) {
  size_t elements = (size_t)ROWS * VOCAB;
  float *logits = (float *)malloc(elements * sizeof(float));
  if (logits == NULL) {
    fputs("{\"error\":\"allocation_failed\"}\n", stdout);
    return 2;
  }
  for (int row = 0; row < ROWS; ++row) {
    float *values = logits + (size_t)row * VOCAB;
    for (int token = 0; token < VOCAB; ++token) {
      values[token] = -1000.0f - (float)((token + row * 17) % 997);
    }
    int winner = (row * 104729 + 769) % VOCAB;
    values[winner] = 17.0f + (float)(row % 13);
    if (row % 7 == 0) {
      int lower_tie = winner > 256 ? winner - 256 : winner + 256;
      values[lower_tie] = values[winner];
    }
  }

  int mismatches = 0;
  uint64_t digest = UINT64_C(1469598103934665603);
  int accepted_drafts = 0;
  int committed_tokens = 0;
  int freed_tokens = 0;
  for (int row = 0; row < ROWS; ++row) {
    const float *values = logits + (size_t)row * VOCAB;
    int control = argmax_control(values);
    int candidate = argmax_tiled(values);
    if (control != candidate) {
      ++mismatches;
    }
    digest ^= (uint32_t)candidate;
    digest *= UINT64_C(1099511628211);
  }
  for (int request = 0; request < REQUESTS; ++request) {
    int accepted = request % DRAFT_TOKENS;
    accepted_drafts += accepted;
    committed_tokens += accepted + 1;
    freed_tokens += DRAFT_TOKENS - accepted - 1;
  }
  free(logits);
  printf(
      "{\"rows\":%d,\"vocab\":%d,\"vocab_tile\":%d,"
      "\"mismatches\":%d,\"selection_digest\":\"%016llx\","
      "\"accepted_drafts\":%d,\"committed_tokens\":%d,\"freed_tokens\":%d,"
      "\"materialized_bytes\":%zu}\n",
      ROWS,
      VOCAB,
      VOCAB_TILE,
      mismatches,
      (unsigned long long)digest,
      accepted_drafts,
      committed_tokens,
      freed_tokens,
      elements * sizeof(float));
  return mismatches == 0 ? 0 : 1;
}
