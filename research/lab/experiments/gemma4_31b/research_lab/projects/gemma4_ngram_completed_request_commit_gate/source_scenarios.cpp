#include "param.h"
#include "result.h"
#include "trie.h"

#include <algorithm>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

namespace {

constexpr int32_t kDominant = 51935;

ngram::Param settings() {
  ngram::Param value;
  value.enable = true;
  value.enable_router_mode = false;
  value.min_bfs_breadth = 1;
  value.max_bfs_breadth = 10;
  value.max_trie_depth = 18;
  value.draft_token_num = 12;
  value.match_type = "BFS";
  return value;
}

void insertWindows(ngram::Trie& trie, const std::vector<int32_t>& output) {
  for (size_t end = 1; end <= output.size(); ++end) {
    const size_t begin = end > 18 ? end - 18 : 0;
    trie.insert(output.data() + begin, end - begin);
  }
}

ngram::Result query(
    const ngram::Trie& trie,
    const ngram::Param& param,
    bool frequency,
    const std::vector<int32_t>& context) {
  ngram::MatchState state;
  if (frequency) {
    return trie.buildFrequency(
        context.data(),
        context.size(),
        context.back(),
        param.draft_token_num - 1,
        param,
        state,
        context.size());
  }
  return trie.buildRecency(
      context.data(),
      context.size(),
      context.back(),
      param.draft_token_num - 1,
      param,
      state,
      context.size());
}

int acceptedDepth(const ngram::Result& result, int32_t target) {
  const int count = static_cast<int>(result.token.size());
  std::vector<int> depth(count, -1);
  depth[0] = 0;
  int best = 0;
  for (int row = 1; row < count; ++row) {
    int parent = -1;
    for (int column = row - 1; column >= 0; --column) {
      if (result.mask[row * count + column]) {
        parent = column;
        break;
      }
    }
    if (parent >= 0 && depth[parent] >= 0 && result.token[row] == target) {
      depth[row] = depth[parent] + 1;
      best = std::max(best, depth[row]);
    }
  }
  return best;
}

void emit(
    const std::string& scenario,
    const ngram::Trie& trie,
    const ngram::Param& param,
    const std::vector<int32_t>& context) {
  const auto bfs = query(trie, param, false, context);
  const auto frequency = query(trie, param, true, context);
  auto linear_param = param;
  linear_param.max_bfs_breadth = 1;
  const auto linear = query(trie, linear_param, false, context);
  std::cout << "{\"scenario\":\"" << scenario
            << "\",\"bfs_accepted_drafts\":" << acceptedDepth(bfs, kDominant)
            << ",\"prob_accepted_drafts\":"
            << acceptedDepth(frequency, kDominant)
            << ",\"linear_accepted_drafts\":"
            << acceptedDepth(linear, kDominant) << "}\n";
}

}  // namespace

int main() {
  const auto param = settings();
  const std::vector<int32_t> dominant(358, kDominant);
  const std::vector<int32_t> context(18, kDominant);
  auto transient = dominant;
  transient[289] = 25627;
  transient[290] = 1767;
  transient[291] = 1154;
  auto persistent = dominant;
  for (size_t index = 26; index < persistent.size(); ++index) {
    persistent[index] = 3055;
  }

  {
    ngram::Trie trie(100000, param);
    insertWindows(trie, dominant);
    emit("dominant_only", trie, param, context);
  }
  {
    ngram::Trie trie(100000, param);
    insertWindows(trie, dominant);
    insertWindows(trie, transient);
    insertWindows(trie, dominant);
    emit("three_token_transient", trie, param, context);
  }
  {
    ngram::Trie trie(100000, param);
    insertWindows(trie, dominant);
    insertWindows(trie, persistent);
    emit("persistent_alternate", trie, param, context);
    for (int repeat = 0; repeat < 4; ++repeat) {
      insertWindows(trie, dominant);
    }
    emit("persistent_alternate_after_four_normal", trie, param, context);
  }
}
