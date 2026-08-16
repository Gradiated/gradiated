from __future__ import annotations

import runpy


runpy.run_path("/work/bound_inputs/sparse_penalty_sitecustomize.py")

from sglang.srt.managers.scheduler_components.metrics_reporter import (
    SchedulerMetricsReporter,
)


_report_decode_stats = SchedulerMetricsReporter.report_decode_stats


def report_decode_stats_without_speculation(self, *args, **kwargs):
    if self.spec_num_forward_ct:
        return _report_decode_stats(self, *args, **kwargs)
    self.spec_num_forward_ct = 1
    self.spec_num_accept_tokens = 0
    try:
        return _report_decode_stats(self, *args, **kwargs)
    finally:
        self.spec_num_forward_ct = 0
        self.spec_num_accept_tokens = 0


SchedulerMetricsReporter.report_decode_stats = report_decode_stats_without_speculation

import high_load_bypass
