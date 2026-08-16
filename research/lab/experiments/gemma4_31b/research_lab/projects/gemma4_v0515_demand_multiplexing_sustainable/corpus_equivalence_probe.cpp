#include "ngram.h"

#include <algorithm>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {

constexpr int32_t kOutputToken = 51935;
constexpr size_t kPromptTokens = 4214;
constexpr size_t kCompletionTokens = 358;
constexpr size_t kTailDepth = 18;
constexpr size_t kDraftTokens = 12;

const std::vector<int32_t> kPromptTail = {
    163902, 12988,  182525, 53777, 127692, 72127,
    245048, 236336, 113206, 40317, 206408, 206837,
    162676, 14926,  120444, 7251,  245256, 51935,
};

std::vector<int32_t> tail_after(size_t completion_count) {
  std::vector<int32_t> sequence = kPromptTail;
  sequence.insert(sequence.end(), completion_count, kOutputToken);
  const auto begin = sequence.size() > kTailDepth ? sequence.end() - kTailDepth
                                                  : sequence.begin();
  return {begin, sequence.end()};
}

ngram::Param make_param() {
  ngram::Param param;
  param.enable = true;
  param.enable_router_mode = false;
  param.min_bfs_breadth = 1;
  param.max_bfs_breadth = 10;
  param.max_trie_depth = kTailDepth;
  param.draft_token_num = kDraftTokens;
  param.match_type = "BFS";
  return param;
}

void calibrate(ngram::Ngram& corpus) {
  std::vector<std::vector<int32_t>> tails;
  tails.reserve(kCompletionTokens);
  for (size_t step = 1; step <= kCompletionTokens; ++step) {
    tails.push_back(tail_after(step));
  }
  corpus.asyncInsert(std::move(tails));
  corpus.synchronize();
}

void require_equal_slice(
    const ngram::Result& isolated,
    const ngram::Result& multiplexed,
    size_t token_offset,
    size_t mask_offset) {
  if (isolated.token.size() != kDraftTokens ||
      isolated.mask.size() != kDraftTokens * kDraftTokens) {
    throw std::runtime_error("unexpected isolated result geometry");
  }
  if (!std::equal(
          isolated.token.begin(),
          isolated.token.end(),
          multiplexed.token.begin() + token_offset) ||
      !std::equal(
          isolated.mask.begin(),
          isolated.mask.end(),
          multiplexed.mask.begin() + mask_offset)) {
    throw std::runtime_error("cross-stream proposal divergence");
  }
}

}  // namespace

int main() {
  ngram::Ngram isolated_a(10000, make_param());
  ngram::Ngram isolated_b(10000, make_param());
  ngram::Ngram multiplexed(10000, make_param());
  calibrate(isolated_a);
  calibrate(isolated_b);
  calibrate(multiplexed);

  for (size_t step = 1; step <= kCompletionTokens; ++step) {
    auto tail = tail_after(step);
    const size_t total_len = kPromptTokens + step;
    auto result_a = isolated_a.batchMatch({100}, {tail}, {total_len});
    auto result_b = isolated_b.batchMatch({200}, {tail}, {total_len});
    auto result_multiplex =
        multiplexed.batchMatch({100, 200}, {tail, tail}, {total_len, total_len});

    require_equal_slice(result_a, result_multiplex, 0, 0);
    require_equal_slice(
        result_b,
        result_multiplex,
        kDraftTokens,
        kDraftTokens * kDraftTokens);

    isolated_a.asyncInsert({tail});
    isolated_b.asyncInsert({tail});
    multiplexed.asyncInsert({tail, tail});
    isolated_a.synchronize();
    isolated_b.synchronize();
    multiplexed.synchronize();
  }

  std::cout
      << "{\"algorithm\":\"official_v0.5.15_ngram_cpp\","
      << "\"calibrated_completion_steps\":358,"
      << "\"compared_completion_steps\":358,"
      << "\"draft_tokens_per_request\":12,"
      << "\"match_type\":\"BFS\","
      << "\"max_trie_depth\":18,"
      << "\"result\":\"isolated_and_two_stream_proposals_exact\"}"
      << std::endl;
}
