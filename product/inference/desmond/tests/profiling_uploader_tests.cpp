#include "desmond/profiling.h"

#include "test_support.h"

#include <chrono>
#include <sstream>
#include <string>
#include <thread>

namespace {

using namespace std::chrono_literals;
using desmond::testing::contains;
using desmond::testing::eventually;
using desmond::testing::RecordingServer;
using desmond::testing::TestHttpServer;
using desmond::testing::throws;

desmond::ProfilingUploaderConfig config_for(const std::uint16_t port) {
  return {
      .url = desmond::testing::local_url(port, "/v1/profiling-events"),
      .token = "profiling-test-token-with-at-least-32-characters",
      .deployment_id = "00000000-0000-4000-8000-000000000001",
      .model_id = "test/model",
      .runtime_revision = "test",
      .batch_size = 1,
      .flush_interval = 1s,
      .retry_initial = 100ms,
      .retry_maximum = 100ms,
      .stop_flush_deadline = 1s,
  };
}

std::size_t event_count(const std::string &body) {
  std::size_t count = 0;
  for (auto offset = body.find("\"event_type\""); offset != std::string::npos;
       offset = body.find("\"event_type\"", offset + 1)) {
    ++count;
  }
  return count;
}

DESMOND_TEST(profiling_uploader_posts_batch_with_identity_and_events) {
  const RecordingServer ingest;
  std::ostringstream log;
  desmond::ProfilingUploader uploader(config_for(ingest.port()), log);

  uploader.enqueue("runtime.test", "{\"value\":1}");

  REQUIRE(eventually([&] {
    return contains(uploader.prometheus(), "desmond_profiling_uploaded_events_total 1\n");
  }));

  const auto request = ingest.log().requests().front();
  CHECK(request.path == "/v1/profiling-events");
  CHECK(request.authorization == "Bearer profiling-test-token-with-at-least-32-characters");
  CHECK(request.body.starts_with("{\"schema_version\":1,\"batch_id\":\""));
  CHECK(contains(request.body, "\"deployment_id\":\"00000000-0000-4000-8000-000000000001\""));
  CHECK(contains(request.body, "\"model_id\":\"test/model\",\"runtime_revision\":\"test\""));
  CHECK(contains(request.body, "\"event_type\":\"runtime.test\",\"properties\":{\"value\":1}}]}"));
}

DESMOND_TEST(profiling_retry_reuses_batch_id_and_body) {
  RecordingServer ingest;
  ingest.respond_in_sequence({500, 204});
  std::ostringstream log;
  desmond::ProfilingUploader uploader(config_for(ingest.port()), log);

  uploader.enqueue("runtime.test", "{\"value\":1}");

  CHECK(eventually([&] { return ingest.log().size() >= 2; }, 3s));
  uploader.stop();

  const auto requests = ingest.log().requests();
  REQUIRE(requests.size() == 2);
  CHECK(requests[0].body == requests[1].body);
  CHECK(contains(uploader.prometheus(), "desmond_profiling_failed_batches_total 1\n"));
  CHECK(contains(uploader.prometheus(), "desmond_profiling_uploaded_events_total 1\n"));
  CHECK(log.str() == "desmond: profiling upload failed cause=http_status=500\n"
                     "desmond: profiling upload recovered\n");
}

DESMOND_TEST(profiling_uploader_splits_the_queue_into_batches) {
  const RecordingServer ingest;
  auto config = config_for(ingest.port());
  config.batch_size = 2;
  config.flush_interval = 60s;
  std::ostringstream log;
  desmond::ProfilingUploader uploader(config, log);

  for (int event = 0; event < 5; ++event) {
    uploader.enqueue("runtime.test", "{}");
  }
  uploader.stop();

  std::size_t total = 0;
  for (const auto &request : ingest.log().requests()) {
    const auto count = event_count(request.body);
    CHECK(count >= 1 && count <= 2);
    total += count;
  }
  CHECK(ingest.log().size() == 3);
  CHECK(total == 5);
}

DESMOND_TEST(profiling_uploader_stop_delivers_queued_events) {
  const RecordingServer ingest;
  auto config = config_for(ingest.port());
  config.batch_size = 100;
  config.flush_interval = 60s;
  std::ostringstream log;
  desmond::ProfilingUploader uploader(config, log);
  for (int event = 0; event < 3; ++event) {
    uploader.enqueue("runtime.test", "{}");
  }

  uploader.stop();

  const auto requests = ingest.log().requests();
  REQUIRE(requests.size() == 1);
  CHECK(event_count(requests.front().body) == 3);
  CHECK(contains(uploader.prometheus(), "desmond_profiling_uploaded_events_total 3\n"));
  CHECK(contains(uploader.prometheus(), "desmond_profiling_dropped_events_total 0\n"));
}

DESMOND_TEST(profiling_uploader_drops_events_beyond_queue_capacity) {
  RecordingServer ingest;
  ingest.respond_with(500);
  auto config = config_for(ingest.port());
  config.queue_capacity = 2;
  config.retry_initial = 10s;
  config.retry_maximum = 10s;
  std::ostringstream log;
  desmond::ProfilingUploader uploader(config, log);
  uploader.enqueue("runtime.held", "{}");
  CHECK(eventually([&] {
    return contains(uploader.prometheus(), "desmond_profiling_failed_batches_total 1\n");
  }));

  uploader.enqueue("runtime.queued", "{}");
  uploader.enqueue("runtime.queued", "{}");
  uploader.enqueue("runtime.dropped", "{}");

  const auto metrics = uploader.prometheus();
  CHECK(contains(metrics, "desmond_profiling_queue_events 2\n"));
  CHECK(contains(metrics, "desmond_profiling_dropped_events_total 1\n"));
}

DESMOND_TEST(profiling_uploader_stop_against_a_failing_ingest_counts_unsent_events) {
  RecordingServer ingest;
  ingest.respond_with(500);
  auto config = config_for(ingest.port());
  config.retry_initial = 30s;
  config.retry_maximum = 30s;
  std::ostringstream log;
  desmond::ProfilingUploader uploader(config, log);
  for (int event = 0; event < 3; ++event) {
    uploader.enqueue("runtime.test", "{}");
  }
  CHECK(eventually([&] { return ingest.log().size() == 1; }));

  const auto started = std::chrono::steady_clock::now();
  uploader.stop();

  CHECK(std::chrono::steady_clock::now() - started < 1s);
  CHECK(contains(uploader.prometheus(), "desmond_profiling_dropped_events_total 3\n"));
  CHECK(contains(uploader.prometheus(), "desmond_profiling_queue_events 0\n"));
  CHECK(contains(log.str(), "desmond: profiling dropped 3 events\n"));
}

DESMOND_TEST(profiling_uploader_stop_is_bounded_by_the_flush_deadline) {
  const TestHttpServer slow_ingest([](const desmond::HttpRequest &) {
    std::this_thread::sleep_for(1500ms);
    return desmond::HttpResponse{204, "application/json", ""};
  });
  auto config = config_for(slow_ingest.port());
  config.batch_size = 100;
  config.flush_interval = 60s;
  std::ostringstream log;
  desmond::ProfilingUploader uploader(config, log);
  uploader.enqueue("runtime.test", "{}");

  const auto started = std::chrono::steady_clock::now();
  uploader.stop();
  const auto elapsed = std::chrono::steady_clock::now() - started;

  CHECK(elapsed >= 900ms && elapsed < 1500ms);
  CHECK(contains(uploader.prometheus(), "desmond_profiling_dropped_events_total 1\n"));
}

DESMOND_TEST(profiling_uploader_drops_events_enqueued_after_stop) {
  const RecordingServer ingest;
  std::ostringstream log;
  desmond::ProfilingUploader uploader(config_for(ingest.port()), log);
  uploader.stop();

  uploader.enqueue("runtime.late", "{}");

  CHECK(contains(uploader.prometheus(), "desmond_profiling_dropped_events_total 1\n"));
}

DESMOND_TEST(profiling_uploader_rejects_invalid_batch_and_retry_configuration) {
  auto zero_batch = config_for(1);
  zero_batch.batch_size = 0;
  auto batch_above_capacity = config_for(1);
  batch_above_capacity.batch_size = 3;
  batch_above_capacity.queue_capacity = 2;
  auto inverted_retry = config_for(1);
  inverted_retry.retry_maximum = 50ms;
  std::ostringstream log;

  CHECK(throws([&] { desmond::ProfilingUploader uploader(zero_batch, log); }));
  CHECK(throws([&] { desmond::ProfilingUploader uploader(batch_above_capacity, log); }));
  CHECK(throws([&] { desmond::ProfilingUploader uploader(inverted_retry, log); }));
}

} // namespace
