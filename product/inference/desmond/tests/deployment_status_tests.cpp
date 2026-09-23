#include "desmond/deployment_status.h"

#include "test_support.h"

#include <optional>
#include <string>
#include <string_view>

namespace {

using desmond::DeploymentStatus;
using desmond::Mode;
using desmond::RuntimeState;

constexpr std::string_view calm = "vllm:kv_cache_usage_perc 0.10\n";
constexpr std::string_view pressured = "vllm:kv_cache_usage_perc 0.95\n";

DESMOND_TEST(assessment_orders_reasons_in_both_modes) {
  struct Case {
    RuntimeState runtime;
    Mode mode;
    std::optional<std::string_view> metrics;
    DeploymentStatus expected;
  };
  const Case cases[] = {
      {RuntimeState::unready, Mode::supervise, pressured, DeploymentStatus::runtime_unavailable},
      {RuntimeState::unready, Mode::observe, std::nullopt, DeploymentStatus::runtime_unavailable},
      {RuntimeState::draining, Mode::supervise, pressured, DeploymentStatus::draining},
      {RuntimeState::draining, Mode::observe, std::nullopt, DeploymentStatus::draining},
      {RuntimeState::ready, Mode::observe, std::nullopt, DeploymentStatus::metrics_unavailable},
      {RuntimeState::ready, Mode::supervise, std::nullopt, DeploymentStatus::accepting},
      {RuntimeState::ready, Mode::observe, pressured, DeploymentStatus::kv_pressure},
      {RuntimeState::ready, Mode::supervise, pressured, DeploymentStatus::kv_pressure},
      {RuntimeState::ready, Mode::observe, calm, DeploymentStatus::accepting},
      {RuntimeState::ready, Mode::supervise, calm, DeploymentStatus::accepting},
  };

  for (const auto &test : cases) {
    CHECK(desmond::assess_deployment(test.runtime, test.mode, test.metrics, 0.90) ==
          test.expected);
  }
}

DESMOND_TEST(each_status_has_one_wire_meaning) {
  struct Case {
    DeploymentStatus status;
    bool healthy;
    bool accepting;
    std::optional<std::string_view> reason;
  };
  const Case cases[] = {
      {DeploymentStatus::accepting, true, true, std::nullopt},
      {DeploymentStatus::runtime_unavailable, false, false, "runtime_unavailable"},
      {DeploymentStatus::draining, false, false, "draining"},
      {DeploymentStatus::metrics_unavailable, true, false, "metrics_unavailable"},
      {DeploymentStatus::kv_pressure, true, false, "kv_pressure"},
  };

  for (const auto &test : cases) {
    CHECK(desmond::is_healthy(test.status) == test.healthy);
    CHECK(desmond::accepts_requests(test.status) == test.accepting);
    CHECK(desmond::reason_code(test.status) == test.reason);
  }
}

DESMOND_TEST(kv_usage_at_or_above_the_limit_is_pressure) {
  CHECK(desmond::kv_pressure_exceeded("vllm:kv_cache_usage_perc 0.95\n", 0.90));
  CHECK(desmond::kv_pressure_exceeded("vllm:kv_cache_usage_perc 0.9", 0.90));
  CHECK(!desmond::kv_pressure_exceeded("vllm:kv_cache_usage_perc 0.89\n", 0.90));
}

DESMOND_TEST(kv_pressure_reads_the_value_before_an_exposition_timestamp) {
  CHECK(desmond::kv_pressure_exceeded("vllm:kv_cache_usage_perc 0.95 1700000000000\n", 0.90));
  CHECK(!desmond::kv_pressure_exceeded("vllm:kv_cache_usage_perc 0.10 1700000000000\n", 0.90));
}

DESMOND_TEST(kv_pressure_reads_labelled_samples) {
  CHECK(desmond::kv_pressure_exceeded(
      "vllm:kv_cache_usage_perc{engine=\"0\",model=\"a } b\"} 0.99 1700000000000\n", 0.90));
  CHECK(!desmond::kv_pressure_exceeded("vllm:kv_cache_usage_perc{engine=\"0\"} 0.10\n", 0.90));
}

DESMOND_TEST(kv_pressure_accepts_every_vllm_cache_metric_name) {
  for (const auto *name : {"vllm:kv_cache_usage_perc", "vllm_kv_cache_usage_perc",
                           "vllm:gpu_cache_usage_perc", "vllm_gpu_cache_usage_perc"}) {
    CHECK(desmond::kv_pressure_exceeded(std::string(name) + " 0.99\n", 0.90));
  }
}

DESMOND_TEST(kv_pressure_ignores_comments_other_metrics_and_unusable_values) {
  CHECK(!desmond::kv_pressure_exceeded("# vllm:kv_cache_usage_perc 0.99\n"
                                       "vllm:kv_cache_usage_perc_total 0.99\n"
                                       "vllm:kv_cache_usage_perc not-a-number\n"
                                       "vllm:kv_cache_usage_perc NaN\n"
                                       "vllm:kv_cache_usage_perc 0.99x\n"
                                       "vllm:kv_cache_usage_perc{unterminated=\"0.99\n"
                                       "vllm:kv_cache_usage_perc\n"
                                       "\n",
                                       0.90));
}

DESMOND_TEST(kv_pressure_ignores_batch_counters) {
  CHECK(!desmond::kv_pressure_exceeded("vllm:kv_cache_usage_perc 0.10\n"
                                       "vllm:num_requests_waiting 50\n"
                                       "vllm:num_requests_running 999\n",
                                       0.90));
}

} // namespace
