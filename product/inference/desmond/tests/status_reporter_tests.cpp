#include "desmond/status_reporter.h"

#include "test_support.h"

#include <chrono>
#include <sstream>

namespace {

using namespace std::chrono_literals;
using desmond::testing::contains;
using desmond::testing::eventually;
using desmond::testing::RecordingServer;
using desmond::testing::throws;
using desmond::DeploymentStatus;

desmond::StatusReporterConfig config_for(const RecordingServer &ingest) {
  return {
      .url = desmond::testing::local_url(ingest.port(), "/v1/deployment-status"),
      .token = "status-token",
      .deployment_id = "00000000-0000-4000-8000-000000000001",
      .runtime_revision = "test-release",
      .interval = 1s,
  };
}

DESMOND_TEST(status_reporter_uploads_snapshot_with_bearer_token) {
  RecordingServer ingest;
  std::ostringstream log;
  desmond::StatusReporter reporter(config_for(ingest), log);

  reporter.update(DeploymentStatus::accepting);

  REQUIRE(eventually([&] { return ingest.log().size() >= 1; }));
  CHECK(eventually([&] { return reporter.recently_uploaded(); }));

  const auto request = ingest.log().requests().front();
  CHECK(request.method == "POST" && request.path == "/v1/deployment-status");
  CHECK(request.authorization == "Bearer status-token");
  CHECK(request.body ==
        "{\"schema_version\":1,\"deployment_id\":\"00000000-0000-4000-8000-000000000001\","
        "\"runtime_revision\":\"test-release\",\"healthy\":true,\"accepting_requests\":true,"
        "\"reason_code\":null}");
  CHECK(contains(reporter.prometheus(), "desmond_status_uploaded_total 1\n"));
}

DESMOND_TEST(status_reporter_accepts_any_2xx_reply) {
  RecordingServer ingest;
  ingest.respond_with(200);
  std::ostringstream log;
  desmond::StatusReporter reporter(config_for(ingest), log);

  reporter.update(DeploymentStatus::accepting);

  CHECK(eventually([&] { return reporter.recently_uploaded(); }));
  CHECK(contains(reporter.prometheus(), "desmond_status_failures_total 0\n"));
}

DESMOND_TEST(status_reporter_counts_rejected_uploads_as_failures) {
  RecordingServer ingest;
  ingest.respond_with(503);
  std::ostringstream log;
  desmond::StatusReporter reporter(config_for(ingest), log);

  reporter.update(DeploymentStatus::runtime_unavailable);

  CHECK(eventually(
      [&] { return contains(reporter.prometheus(), "desmond_status_failures_total 1\n"); }));
  CHECK(!reporter.recently_uploaded());
  const auto requests = ingest.log().requests();
  REQUIRE(!requests.empty());
  CHECK(contains(requests.front().body, "\"reason_code\":\"runtime_unavailable\""));
}

DESMOND_TEST(status_reporter_logs_the_failure_cause_once_and_then_the_recovery) {
  RecordingServer ingest;
  ingest.respond_in_sequence({503, 503, 204});
  std::ostringstream log;
  desmond::StatusReporter reporter(config_for(ingest), log);

  reporter.update(DeploymentStatus::accepting);

  CHECK(eventually([&] { return reporter.recently_uploaded(); }, 5s));
  reporter.stop();
  CHECK(log.str() == "desmond: status upload failed cause=http_status=503\n"
                     "desmond: status upload recovered\n");
}

DESMOND_TEST(status_reporter_uploads_the_latest_snapshot_on_stop) {
  RecordingServer ingest;
  auto config = config_for(ingest);
  config.interval = 60s;
  std::ostringstream log;
  desmond::StatusReporter reporter(config, log);
  reporter.update(DeploymentStatus::accepting);
  CHECK(eventually([&] { return ingest.log().size() == 1; }));

  reporter.update(DeploymentStatus::draining);
  reporter.stop();

  const auto requests = ingest.log().requests();
  REQUIRE(requests.size() == 2);
  CHECK(contains(requests.back().body, "\"healthy\":false,\"accepting_requests\":false"));
  CHECK(contains(requests.back().body, "\"reason_code\":\"draining\""));
}

DESMOND_TEST(status_reporter_delivers_an_update_followed_at_once_by_stop) {
  RecordingServer ingest;
  std::ostringstream log;
  desmond::StatusReporter reporter(config_for(ingest), log);

  reporter.update(DeploymentStatus::draining);
  reporter.stop();

  const auto requests = ingest.log().requests();
  REQUIRE(requests.size() == 1);
  CHECK(contains(requests.front().body, "\"reason_code\":\"draining\""));
}

DESMOND_TEST(status_reporter_does_not_resend_a_delivered_snapshot_on_stop) {
  RecordingServer ingest;
  auto config = config_for(ingest);
  config.interval = 60s;
  std::ostringstream log;
  desmond::StatusReporter reporter(config, log);
  reporter.update(DeploymentStatus::accepting);
  CHECK(eventually([&] { return ingest.log().size() == 1; }));

  reporter.stop();

  CHECK(ingest.log().size() == 1);
}

DESMOND_TEST(status_reporter_without_a_snapshot_uploads_nothing) {
  RecordingServer ingest;
  std::ostringstream log;
  desmond::StatusReporter reporter(config_for(ingest), log);

  reporter.stop();

  CHECK(ingest.log().size() == 0);
  CHECK(!reporter.recently_uploaded());
}

DESMOND_TEST(status_reporter_rejects_non_positive_interval) {
  RecordingServer ingest;
  auto config = config_for(ingest);
  config.interval = 0s;
  std::ostringstream log;

  CHECK(throws([&] { desmond::StatusReporter reporter(config, log); }));
}

} // namespace
