#include "param.h"
#include "result.h"
#include "trie.h"

#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

namespace {

constexpr int32_t kDominantToken = 51935;

int acceptedDraftDepth(const ngram::Result& result, int32_t target_token) {
  const int n = static_cast<int>(result.token.size());
  std::vector<int> depth(n, -1);
  depth[0] = 0;
  int best = 0;
  for (int row = 1; row < n; ++row) {
    int parent = -1;
    for (int col = row - 1; col >= 0; --col) {
      if (result.mask[row * n + col]) {
        parent = col;
        break;
      }
    }
    if (parent >= 0 && depth[parent] >= 0 && result.token[row] == target_token) {
      depth[row] = depth[parent] + 1;
      if (depth[row] > best) {
        best = depth[row];
      }
    }
  }
  return best;
}

ngram::Result query(
    const ngram::Trie& trie,
    const ngram::Param& param,
    bool frequency,
    const std::vector<int32_t>& context,
    size_t total_len) {
  ngram::MatchState state;
  if (frequency) {
    return trie.buildFrequency(
        context.data(),
        context.size(),
        context.back(),
        param.draft_token_num - 1,
        param,
        state,
        total_len);
  }
  return trie.buildRecency(
      context.data(),
      context.size(),
      context.back(),
      param.draft_token_num - 1,
      param,
      state,
      total_len);
}

void emit(
    const std::string& scenario,
    const ngram::Trie& trie,
    const ngram::Param& param,
    const std::vector<int32_t>& context) {
  const auto bfs = query(trie, param, false, context, context.size());
  const auto prob = query(trie, param, true, context, context.size());
  auto linear_param = param;
  linear_param.max_bfs_breadth = 1;
  const auto linear = query(trie, linear_param, false, context, context.size());
  std::cout << "{\"scenario\":\"" << scenario
            << "\",\"bfs_accepted_drafts\":" << acceptedDraftDepth(bfs, kDominantToken)
            << ",\"prob_accepted_drafts\":" << acceptedDraftDepth(prob, kDominantToken)
            << ",\"linear_accepted_drafts\":" << acceptedDraftDepth(linear, kDominantToken)
            << ",\"bfs_tokens\":[";
  for (size_t i = 0; i < bfs.token.size(); ++i) {
    if (i) {
      std::cout << ",";
    }
    std::cout << bfs.token[i];
  }
  std::cout << "],\"prob_tokens\":[";
  for (size_t i = 0; i < prob.token.size(); ++i) {
    if (i) {
      std::cout << ",";
    }
    std::cout << prob.token[i];
  }
  std::cout << "],\"linear_tokens\":[";
  for (size_t i = 0; i < linear.token.size(); ++i) {
    if (i) {
      std::cout << ",";
    }
    std::cout << linear.token[i];
  }
  std::cout << "]}\n";
}

void insertDecodeWindows(ngram::Trie& trie, const std::vector<int32_t>& output) {
  for (size_t end = 1; end <= output.size(); ++end) {
    const size_t begin = end > 18 ? end - 18 : 0;
    trie.insert(output.data() + begin, end - begin);
  }
}

}  // namespace

int main() {
  ngram::Param param;
  param.enable = true;
  param.enable_router_mode = false;
  param.min_bfs_breadth = 1;
  param.max_bfs_breadth = 10;
  param.max_trie_depth = 18;
  param.draft_token_num = 12;
  param.match_type = "BFS";

  const std::vector<int32_t> dominant(358, kDominantToken);
  const std::vector<int32_t> context(18, kDominantToken);

  {
    ngram::Trie trie(100000, param);
    insertDecodeWindows(trie, dominant);
    emit("dominant_only", trie, param, context);
  }

  auto transient = dominant;
  transient[289] = 25627;
  transient[290] = 1767;
  transient[291] = 1154;
  {
    ngram::Trie trie(100000, param);
    insertDecodeWindows(trie, dominant);
    insertDecodeWindows(trie, transient);
    insertDecodeWindows(trie, dominant);
    emit("three_token_transient", trie, param, context);
  }

  auto persistent = dominant;
  for (size_t i = 26; i < persistent.size(); ++i) {
    persistent[i] = 3055;
  }
  {
    ngram::Trie trie(100000, param);
    insertDecodeWindows(trie, dominant);
    insertDecodeWindows(trie, persistent);
    emit("persistent_alternate", trie, param, context);
    for (int i = 0; i < 4; ++i) {
      insertDecodeWindows(trie, dominant);
    }
    emit("persistent_alternate_after_four_normal", trie, param, context);
  }
}
