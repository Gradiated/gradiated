//! $/token model. Hardware-hour cost (amortized capex + power) divided by
//! measured-or-simulated throughput. Objectives are pluggable: cost-per-token
//! now; a TPS/latency objective later reuses the same PerfReport.

use sartor_perf::PerfReport;
use sartor_spec::{CostSpec, HardwareSpec};
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct CostReport {
    pub hourly_usd: f64,
    pub capex_hourly_usd: f64,
    pub power_hourly_usd: f64,
    pub usd_per_mtok_output: f64,
    pub usd_per_mtok_total: f64,
    pub joules_per_token: f64,
}

pub fn cost(hw: &HardwareSpec, c: &CostSpec, perf: &PerfReport) -> CostReport {
    let capex = hw.unit_cost_usd * (1.0 + c.system_overhead_frac)
        / (c.amortization_months * 730.0 * c.utilization);
    // Power billed on average draw during the run, PUE-inflated.
    let avg_w = hw.tdp_w * (0.35 + 0.65 * perf.device_busy_frac);
    let power = avg_w * c.pue * c.power_usd_per_kwh / 1000.0;
    let hourly = capex + power;
    let out_tok_hr = perf.output_tok_per_s * 3600.0;
    let total_tok_hr = perf.total_tok_per_s * 3600.0;
    CostReport {
        hourly_usd: hourly,
        capex_hourly_usd: capex,
        power_hourly_usd: power,
        usd_per_mtok_output: hourly / out_tok_hr * 1e6,
        usd_per_mtok_total: hourly / total_tok_hr * 1e6,
        joules_per_token: perf.energy_j
            / (perf.output_tok_per_s * perf.wall_s).max(1.0),
    }
}
