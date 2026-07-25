#include "param.h"
#include "result.h"
#include "trie.h"

#include <algorithm>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace {

constexpr int32_t kDominant = 51935;
constexpr int32_t kAlternate = 3055;

struct State {
  std::string owner;
  size_t max_rows;
  std::vector<std::vector<int32_t>> rows;
};

class Buffer {
 public:
  explicit Buffer(size_t max_active) : max_active_(max_active) {}

  void stage(
      const std::string& rid,
      const std::string& owner,
      std::vector<int32_t> row,
      size_t max_rows) {
    auto found = states_.find(rid);
    if (found != states_.end() && found->second.owner != owner) {
      discarded_rows_ += found->second.rows.size();
      states_.erase(found);
      ++id_reuses_;
      found = states_.end();
    }
    if (found == states_.end()) {
      if (states_.size() >= max_active_) {
        throw std::overflow_error("active request bound");
      }
      found = states_.emplace(rid, State{owner, max_rows, {}}).first;
    }
    if (found->second.rows.size() >= found->second.max_rows) {
      throw std::overflow_error("request row bound");
    }
    found->second.rows.push_back(std::move(row));
  }

  size_t finish(
      ngram::Trie& trie,
      const std::string& rid,
      const std::string& owner,
      bool aborted) {
    auto found = states_.find(rid);
    if (found == states_.end() || found->second.owner != owner) {
      return 0;
    }
    auto rows = std::move(found->second.rows);
    states_.erase(found);
    if (aborted) {
      discarded_rows_ += rows.size();
      return 0;
    }
    for (const auto& row : rows) {
      trie.insert(row.data(), row.size());
    }
    return rows.size();
  }

  size_t active() const { return states_.size(); }
  size_t discardedRows() const { return discarded_rows_; }
  size_t idReuses() const { return id_reuses_; }

 private:
  size_t max_active_;
  std::unordered_map<std::string, State> states_;
  size_t discarded_rows_ = 0;
  size_t id_reuses_ = 0;
};

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

std::vector<std::vector<int32_t>> windows(const std::vector<int32_t>& output) {
  std::vector<std::vector<int32_t>> rows;
  for (size_t end = 1; end <= output.size(); ++end) {
    const size_t begin = end > 18 ? end - 18 : 0;
    rows.emplace_back(output.begin() + begin, output.begin() + end);
  }
  return rows;
}

void stageAll(
    Buffer& buffer,
    const std::string& rid,
    const std::string& owner,
    const std::vector<int32_t>& output) {
  for (auto row : windows(output)) {
    buffer.stage(rid, owner, std::move(row), output.size());
  }
}

int acceptedDepth(const ngram::Trie& trie, int32_t target) {
  const auto param = settings();
  const std::vector<int32_t> context(18, kDominant);
  ngram::MatchState state;
  const auto result = trie.buildRecency(
      context.data(),
      context.size(),
      context.back(),
      param.draft_token_num - 1,
      param,
      state,
      context.size());
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
    const Buffer& buffer,
    size_t committed_rows) {
  std::cout << "{\"scenario\":\"" << scenario
            << "\",\"dominant_accepted_drafts\":" << acceptedDepth(trie, kDominant)
            << ",\"alternate_accepted_drafts\":" << acceptedDepth(trie, kAlternate)
            << ",\"active_requests\":" << buffer.active()
            << ",\"committed_rows\":" << committed_rows
            << ",\"discarded_rows\":" << buffer.discardedRows()
            << ",\"id_reuses\":" << buffer.idReuses() << "}\n";
}

}  // namespace

int main() {
  const auto param = settings();
  const std::vector<int32_t> dominant(358, kDominant);
  auto transient = dominant;
  transient[289] = 25627;
  transient[290] = 1767;
  transient[291] = 1154;
  auto persistent = dominant;
  for (size_t index = 26; index < persistent.size(); ++index) {
    persistent[index] = kAlternate;
  }

  {
    ngram::Trie trie(100000, param);
    Buffer buffer(32);
    stageAll(buffer, "historical", "owner-h", dominant);
    buffer.finish(trie, "historical", "owner-h", false);
    stageAll(buffer, "request-32", "owner-32", transient);
    emit("request_32_inflight_isolated", trie, buffer, 0);
    const auto committed =
        buffer.finish(trie, "request-32", "owner-32", false);
    emit("request_32_post_completion_visible", trie, buffer, committed);
  }
  {
    ngram::Trie trie(100000, param);
    Buffer buffer(32);
    stageAll(buffer, "historical", "owner-h", dominant);
    buffer.finish(trie, "historical", "owner-h", false);
    stageAll(buffer, "request-790", "owner-790", persistent);
    const auto committed =
        buffer.finish(trie, "request-790", "owner-790", true);
    emit("request_790_abort_discarded", trie, buffer, committed);
  }
  {
    ngram::Trie trie(100000, param);
    Buffer buffer(32);
    stageAll(buffer, "historical", "owner-h", dominant);
    buffer.finish(trie, "historical", "owner-h", false);
    stageAll(buffer, "reused", "old-owner", persistent);
    buffer.stage("reused", "new-owner", {kDominant}, dominant.size());
    const auto committed = buffer.finish(trie, "reused", "new-owner", true);
    emit("request_id_reuse_discards_old_owner", trie, buffer, committed);
  }
  {
    ngram::Trie trie(100000, param);
    Buffer buffer(32);
    stageAll(buffer, "single", "owner", dominant);
    const auto committed = buffer.finish(trie, "single", "owner", false);
    const auto duplicate = buffer.finish(trie, "single", "owner", false);
    emit("single_completion_exactly_once", trie, buffer, committed + duplicate);
  }
}
