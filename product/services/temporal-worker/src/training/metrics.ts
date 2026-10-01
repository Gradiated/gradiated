import { Gauge, type Registry } from "prom-client";
import type { TrainingMetric } from "@gradiated/control";

import { RUN_STAGE_ORDER, TERMINAL_RUN_STAGES } from "@gradiated/contracts";
const stages = [...RUN_STAGE_ORDER, "cancelling"];
const outcomes = TERMINAL_RUN_STAGES;

export class TrainingMetrics {
  private readonly gauges: Record<TrainingMetric["kind"], Gauge<"stage">>;
  private readonly available: Gauge;
  private readonly observed: Gauge;
  private nextRefresh = 0;
  private pending: Promise<void> | undefined;

  constructor(
    registry: Registry,
    private readonly read: () => Promise<TrainingMetric[]>,
  ) {
    const gauge = (name: string, help: string) =>
      new Gauge({
        name: `gradiated_training_${name}`,
        help,
        labelNames: ["stage"],
        registers: [registry],
      });
    this.gauges = {
      active: gauge(
        "active_runs",
        "Current runs by stage, shared database snapshot; use max across worker replicas.",
      ),
      oldest: gauge(
        "oldest_stage_seconds",
        "Age of the oldest active run in each stage.",
      ),
      completed: gauge(
        "completed_runs_24h",
        "Runs completed in the last 24 hours by terminal stage; a rolling gauge, not a counter.",
      ),
      duration: gauge(
        "stage_duration_p95_seconds_24h",
        "P95 duration of stage visits completed in the last 24 hours, including capacity waits.",
      ),
    };
    this.available = new Gauge({
      name: "gradiated_training_metrics_available",
      help: "One when the last training database observation succeeded.",
      registers: [registry],
    });
    this.observed = new Gauge({
      name: "gradiated_training_metrics_timestamp_seconds",
      help: "Time of the last successful training database observation.",
      registers: [registry],
    });
  }

  async collect(): Promise<void> {
    if (this.pending) return this.pending;
    if (Date.now() < this.nextRefresh) return;

    this.pending = this.refresh();
    try {
      await this.pending;
    } finally {
      this.pending = undefined;
      this.nextRefresh = Date.now() + 30_000;
    }
  }

  private async refresh(): Promise<void> {
    try {
      const rows = await this.read();
      for (const gauge of Object.values(this.gauges)) gauge.reset();
      for (const stage of stages) {
        this.gauges.active.set({ stage }, 0);
        this.gauges.oldest.set({ stage }, 0);
      }
      for (const stage of outcomes) this.gauges.completed.set({ stage }, 0);
      for (const row of rows) {
        if (![...stages, ...outcomes].includes(row.stage)) continue;
        this.gauges[row.kind].set({ stage: row.stage }, row.value);
      }
      this.available.set(1);
      this.observed.set(Date.now() / 1000);
    } catch {
      for (const gauge of Object.values(this.gauges)) gauge.reset();
      this.available.set(0);
    }
  }
}
