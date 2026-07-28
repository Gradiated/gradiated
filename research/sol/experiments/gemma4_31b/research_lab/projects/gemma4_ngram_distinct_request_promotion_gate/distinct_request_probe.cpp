#include "param.h"
#include "result.h"
#include "trie.h"

#include <cstdint>
#include <cstring>
#include <deque>
#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

constexpr int32_t kDominant = 51935;

class Gate {
 public:
  explicit Gate(size_t capacity) : capacity_(capacity) {}

  bool admit(const std::string& rid, const std::vector<int32_t>& suffix) {
    std::string key(
        reinterpret_cast<const char*>(suffix.data()),
        suffix.size() * sizeof(int32_t));
    auto found = first_rid_.find(key);
    if (found == first_rid_.end()) {
      first_rid_.emplace(key, rid);
      order_.push_back(key);
      if (first_rid_.size() > capacity_) {
        first_rid_.erase(order_.front());
        order_.pop_front();
        ++evicted_;
      }
      return false;
    }
    if (found->second == rid) {
      ++same_request_repeats_;
      return false;
    }
    first_rid_.erase(found);
    ++admitted_;
    return true;
  }

  size_t probation() const { return first_rid_.size(); }
  size_t admitted() const { return admitted_; }
  size_t evicted() const { return evicted_; }
  size_t same_request_repeats() const { return same_request_repeats_; }

 private:
  size_t capacity_;
  std::unordered_map<std::string, std::string> first_rid_;
  std::deque<std::string> order_;
  size_t admitted_ = 0;
  size_t evicted_ = 0;
  size_t same_request_repeats_ = 0;
};

void gatedDecode(
    Gate& gate,
    ngram::Trie& trie,
    const std::string& rid,
    const std::vector<int32_t>& output) {
  for (size_t end = 1; end <= output.size(); ++end) {
    const size_t begin = end > 18 ? end - 18 : 0;
    std::vector<int32_t> suffix(output.begin() + begin, output.begin() + end);
    if (gate.admit(rid, suffix)) {
      trie.insert(suffix.data(), suffix.size());
    }
  }
}

int acceptedDepth(
    const ngram::Trie& trie,
    const ngram::Param& param,
    int32_t target) {
  const std::vector<int32_t> context(18, target);
  ngram::MatchState state;
  const auto result = trie.buildRecency(
      context.data(),
      context.size(),
      context.back(),
      param.draft_token_num - 1,
      param,
      state,
      context.size());
  const int n = static_cast<int>(result.token.size());
  std::vector<int> depth(n, -1);
  depth[0] = 0;
  int best = 0;
  for (int row = 1; row < n; ++row) {
    int parent = -1;
    for (int column = row - 1; column >= 0; --column) {
      if (result.mask[row * n + column]) {
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
    const Gate& gate) {
  std::cout << "{\"scenario\":\"" << scenario
            << "\",\"dominant_accepted_drafts\":"
            << acceptedDepth(trie, param, kDominant)
            << ",\"alternate_accepted_drafts\":"
            << acceptedDepth(trie, param, 3055)
            << ",\"probation_entries\":" << gate.probation()
            << ",\"admitted\":" << gate.admitted()
            << ",\"same_request_repeats\":" << gate.same_request_repeats()
            << ",\"evicted\":" << gate.evicted() << "}\n";
}

ngram::Param param() {
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

}  // namespace

int main() {
  const auto settings = param();
  const std::vector<int32_t> dominant(358, kDominant);
  auto transient = dominant;
  transient[289] = 25627;
  transient[290] = 1767;
  transient[291] = 1154;
  auto persistent = dominant;
  for (size_t index = 26; index < persistent.size(); ++index) {
    persistent[index] = 3055;
  }

  {
    ngram::Trie trie(100000, settings);
    Gate gate(16384);
    gatedDecode(gate, trie, "request-0", dominant);
    gatedDecode(gate, trie, "request-1", dominant);
    emit("dominant_support_two", trie, settings, gate);
  }
  {
    ngram::Trie trie(100000, settings);
    Gate gate(16384);
    gatedDecode(gate, trie, "request-0", dominant);
    gatedDecode(gate, trie, "request-1", dominant);
    gatedDecode(gate, trie, "request-32", transient);
    emit("request_32_transient_quarantined", trie, settings, gate);
  }
  {
    ngram::Trie trie(100000, settings);
    Gate gate(16384);
    gatedDecode(gate, trie, "request-0", dominant);
    gatedDecode(gate, trie, "request-1", dominant);
    for (int repeat = 0; repeat < 5; ++repeat) {
      gatedDecode(gate, trie, "request-790", persistent);
    }
    emit("request_790_self_repeat_quarantined", trie, settings, gate);
  }
}

