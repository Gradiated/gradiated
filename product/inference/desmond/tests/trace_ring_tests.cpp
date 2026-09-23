#include "desmond/trace.h"

#include "test_support.h"

#include <cstdint>
#include <fstream>
#include <string>

#include <fcntl.h>
#include <sys/wait.h>
#include <unistd.h>

namespace {

using desmond::testing::TempDirectory;
using desmond::testing::throws;

constexpr off_t magic_offset = 0;
constexpr off_t version_offset = 8;
constexpr off_t event_bytes_offset = 12;
constexpr off_t capacity_offset = 16;

template <typename Value>
void overwrite_header(const std::string &path, const off_t offset, const Value value) {
  const int descriptor = open(path.c_str(), O_WRONLY);
  CHECK(descriptor >= 0);
  CHECK(pwrite(descriptor, &value, sizeof(value), offset) == static_cast<ssize_t>(sizeof(value)));
  close(descriptor);
}

bool open_throws(const std::string &path) {
  return throws([&] { static_cast<void>(desmond::SharedTraceRing::open_existing(path)); });
}

DESMOND_TEST(shared_trace_ring_preserves_order_and_counts_drops_across_mappings) {
  const TempDirectory directory;
  const auto path = directory.file("ring");
  auto consumer = desmond::SharedTraceRing::create(path, 2);
  auto producer = desmond::SharedTraceRing::open_existing(path);

  CHECK(producer->try_push({.request_id_low = 21, .type = desmond::TraceEventType::prefill_batch}));
  CHECK(producer->try_push({.request_id_low = 22, .type = desmond::TraceEventType::decode_batch}));
  CHECK(!producer->try_push({.request_id_low = 23}));
  CHECK(consumer->dropped() == 1);

  desmond::TraceEvent output;
  CHECK(consumer->try_pop(output) && output.request_id_low == 21);
  CHECK(consumer->try_pop(output) && output.request_id_low == 22);
  CHECK(!consumer->try_pop(output));
}

DESMOND_TEST(shared_trace_ring_carries_events_across_processes) {
  const TempDirectory directory;
  const auto path = directory.file("ring");
  auto consumer = desmond::SharedTraceRing::create(path, 8);

  const pid_t child = fork();
  CHECK(child >= 0);
  if (child == 0) {
    try {
      auto producer = desmond::SharedTraceRing::open_existing(path);
      const bool pushed = producer->try_push(
          {.request_id_low = 31, .type = desmond::TraceEventType::request_finished});
      _exit(pushed ? 0 : 1);
    } catch (...) {
      _exit(2);
    }
  }

  int status = 0;
  CHECK(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
  desmond::TraceEvent output;
  CHECK(consumer->try_pop(output) && output.request_id_low == 31);
}

DESMOND_TEST(shared_trace_ring_ignores_capacity_rewritten_after_open) {
  const TempDirectory directory;
  const auto path = directory.file("ring");
  auto consumer = desmond::SharedTraceRing::create(path, 2);
  auto producer = desmond::SharedTraceRing::open_existing(path);

  overwrite_header(path, capacity_offset, std::uint64_t{1} << 20);

  for (std::uint64_t round = 0; round < 3; ++round) {
    CHECK(producer->try_push({.request_id_low = 2 * round + 1}));
    CHECK(producer->try_push({.request_id_low = 2 * round + 2}));
    CHECK(!producer->try_push({.request_id_low = 99}));

    desmond::TraceEvent output;
    CHECK(consumer->try_pop(output) && output.request_id_low == 2 * round + 1);
    CHECK(consumer->try_pop(output) && output.request_id_low == 2 * round + 2);
    CHECK(!consumer->try_pop(output));
  }
  CHECK(consumer->dropped() == 3);
}

DESMOND_TEST(shared_trace_ring_creator_unlinks_and_opener_does_not) {
  const TempDirectory directory;
  const auto path = directory.file("ring");
  auto creator = desmond::SharedTraceRing::create(path, 2);

  desmond::SharedTraceRing::open_existing(path).reset();
  CHECK(access(path.c_str(), F_OK) == 0);

  creator.reset();
  CHECK(access(path.c_str(), F_OK) != 0);
}

DESMOND_TEST(shared_trace_ring_create_refuses_existing_file) {
  const TempDirectory directory;
  const auto path = directory.file("ring");
  auto first = desmond::SharedTraceRing::create(path, 2);

  CHECK(throws([&] { static_cast<void>(desmond::SharedTraceRing::create(path, 2)); }));
}

DESMOND_TEST(shared_trace_ring_create_rejects_invalid_capacity) {
  const TempDirectory directory;

  for (const std::size_t capacity :
       {std::size_t{0}, std::size_t{1}, std::size_t{3}, std::size_t{8'388'608}}) {
    CHECK(throws([&] {
      static_cast<void>(desmond::SharedTraceRing::create(directory.file("ring"), capacity));
    }));
  }
}

DESMOND_TEST(shared_trace_ring_open_rejects_missing_or_short_files) {
  const TempDirectory directory;
  const auto short_file = directory.file("short");
  std::ofstream(short_file) << "x";

  CHECK(open_throws(directory.file("missing")));
  CHECK(open_throws(short_file));
}

DESMOND_TEST(shared_trace_ring_open_rejects_incompatible_headers) {
  const TempDirectory directory;
  const auto path = directory.file("ring");
  auto creator = desmond::SharedTraceRing::create(path, 4);
  CHECK(!open_throws(path));

  overwrite_header(path, magic_offset, std::uint64_t{0});
  CHECK(open_throws(path));
  creator.reset();

  const auto corrupt = [&](const off_t offset, const auto value) {
    auto ring = desmond::SharedTraceRing::create(path, 4);
    overwrite_header(path, offset, value);
    return open_throws(path);
  };
  CHECK(corrupt(version_offset, std::uint32_t{2}));
  CHECK(corrupt(event_bytes_offset, std::uint32_t{1}));
  CHECK(corrupt(capacity_offset, std::uint64_t{3}));
  CHECK(corrupt(capacity_offset, std::uint64_t{8}));
}

DESMOND_TEST(shared_trace_ring_open_rejects_a_size_that_does_not_match_capacity) {
  const TempDirectory directory;
  const auto path = directory.file("ring");
  auto creator = desmond::SharedTraceRing::create(path, 4);

  const int descriptor = open(path.c_str(), O_WRONLY);
  CHECK(descriptor >= 0 && ftruncate(descriptor, 1 << 20) == 0);
  close(descriptor);

  CHECK(open_throws(path));
}

DESMOND_TEST(trace_event_types_have_stable_names) {
  CHECK(std::string(desmond::trace_event_type_name(desmond::TraceEventType::request_admitted)) ==
        "request.admitted");
  CHECK(std::string(desmond::trace_event_type_name(desmond::TraceEventType::kv_cache_allocate)) ==
        "kv_cache.allocate");
  CHECK(std::string(desmond::trace_event_type_name(desmond::TraceEventType::request_cancelled)) ==
        "request.cancelled");
  CHECK(std::string(desmond::trace_event_type_name(static_cast<desmond::TraceEventType>(999))) ==
        "unknown");
}

} // namespace
