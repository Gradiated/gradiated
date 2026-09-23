#include "desmond/control_api.h"

#include "test_support.h"

#include <optional>
#include <string>

namespace {

using desmond::testing::contains;

const desmond::RuntimeIdentity identity{
    .release = "release-1",
    .model = std::string("model \"q\" \x01"),
    .model_revision = "rev",
};

using desmond::ChildState;
using desmond::RuntimeState;

struct Fixture {
  desmond::Mode mode{desmond::Mode::supervise};
  RuntimeState runtime{RuntimeState::ready};
  std::optional<desmond::SupervisedChild> supervised_child{
      {.pid = 42, .state = ChildState::running}};
  bool reporter_fresh{true};
  std::string control_token{"control-token"};
  std::optional<std::string> upstream{"runtime_metric 1\n"};

  desmond::HttpResponse get(const std::string &path, const std::string &authorization = "") const {
    return request("GET", path, authorization);
  }

  desmond::HttpResponse request(const std::string &method, const std::string &path,
                                const std::string &authorization = "") const {
    return desmond::handle_control_request(
        {.method = method, .path = path, .authorization = authorization, .body = ""},
        {
            .mode = mode,
            .runtime = runtime,
            .supervised_child = supervised_child,
            .reporter_fresh = reporter_fresh,
            .identity = identity,
            .control_token = control_token,
            .desmond_metrics = [] { return std::string("desmond_metric 1\n"); },
            .runtime_metrics = [this] { return upstream; },
        });
  }
};

DESMOND_TEST(liveness_is_always_ok) {
  Fixture fixture;
  fixture.runtime = RuntimeState::draining;

  CHECK(fixture.get("/health/live").status == 200);
}

DESMOND_TEST(readiness_follows_runtime_health_and_draining) {
  Fixture ready;
  Fixture not_ready;
  not_ready.runtime = RuntimeState::unready;
  Fixture draining;
  draining.runtime = RuntimeState::draining;

  for (const char *path : {"/health/ready", "/health"}) {
    CHECK(ready.get(path).status == 200);
    CHECK(not_ready.get(path).status == 503);
    CHECK(draining.get(path).status == 503);
  }
}

DESMOND_TEST(observe_mode_is_ready_only_with_a_fresh_status_upload) {
  Fixture fresh;
  fresh.mode = desmond::Mode::observe;
  fresh.supervised_child.reset();
  Fixture stale = fresh;
  stale.reporter_fresh = false;
  Fixture supervised_stale;
  supervised_stale.reporter_fresh = false;

  CHECK(fresh.get("/health/ready").status == 200);
  CHECK(stale.get("/health/ready").status == 503);
  CHECK(supervised_stale.get("/health/ready").status == 200);
}

DESMOND_TEST(metrics_append_the_runtime_block_only_when_present) {
  Fixture with_runtime;
  Fixture without_runtime;
  without_runtime.upstream.reset();

  const auto both = with_runtime.get("/metrics");
  const auto desmond_only = without_runtime.get("/metrics");

  CHECK(both.status == 200 && both.content_type.starts_with("text/plain; version=0.0.4"));
  CHECK(both.body == "desmond_metric 1\n\n# runtime metrics\nruntime_metric 1\n");
  CHECK(desmond_only.body == "desmond_metric 1\n");
}

DESMOND_TEST(status_requires_the_exact_bearer_token) {
  const Fixture fixture;

  CHECK(fixture.get("/v1/desmond/status").status == 401);
  CHECK(fixture.get("/v1/desmond/status", "Bearer control-tokex").status == 401);
  CHECK(fixture.get("/v1/desmond/status", "Bearer control-token-longer").status == 401);
  CHECK(fixture.get("/v1/desmond/status", "control-token").status == 401);
  CHECK(fixture.get("/v1/desmond/status", "Bearer control-token").status == 200);
}

DESMOND_TEST(status_is_open_without_a_control_token) {
  Fixture fixture;
  fixture.control_token.clear();

  CHECK(fixture.get("/v1/desmond/status").status == 200);
}

DESMOND_TEST(status_body_is_escaped_json) {
  const Fixture fixture;

  const auto response = fixture.get("/v1/desmond/status", "Bearer control-token");

  CHECK(response.content_type == "application/json");
  CHECK(response.body ==
        "{\"child_running\":true,\"runtime_ready\":true,\"draining\":false,\"pid\":42,"
        "\"starts\":1,\"unexpected_exits\":0,\"release\":\"release-1\","
        "\"model\":\"model \\\"q\\\" \\u0001\",\"model_revision\":\"rev\"}\n");
}

DESMOND_TEST(status_leaves_out_pid_without_a_child) {
  Fixture fixture;
  fixture.supervised_child.reset();

  const auto body = fixture.get("/v1/desmond/status", "Bearer control-token").body;

  CHECK(contains(body, "\"child_running\":false"));
  CHECK(contains(body, "\"starts\":0,\"unexpected_exits\":0"));
  CHECK(!contains(body, "\"pid\""));
}

DESMOND_TEST(status_reports_an_unexpected_runtime_exit) {
  Fixture fixture;
  fixture.runtime = RuntimeState::draining;
  fixture.supervised_child = {{.pid = 42, .state = ChildState::exited_unexpectedly}};

  const auto body = fixture.get("/v1/desmond/status", "Bearer control-token").body;

  CHECK(contains(body, "\"child_running\":false,\"runtime_ready\":false,\"draining\":true,"
                       "\"starts\":1,\"unexpected_exits\":1"));
  CHECK(!contains(body, "\"pid\""));
}

DESMOND_TEST(non_get_methods_are_405_and_unknown_paths_404) {
  const Fixture fixture;

  CHECK(fixture.request("POST", "/health").status == 405);
  CHECK(fixture.request("DELETE", "/v1/desmond/status").status == 405);
  CHECK(fixture.get("/unknown").status == 404);
}

} // namespace
