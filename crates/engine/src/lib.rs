pub mod config;
pub mod detok;
pub mod engine;
pub mod kv;
pub mod model;
pub mod probe;
pub mod sample;
pub mod sched;

use anyhow::{bail, Result};
use candle_core::{DType, Device};

pub fn parse_device(s: &str) -> Result<Device> {
    match s {
        "cpu" => Ok(Device::Cpu),
        "metal" => Ok(Device::new_metal(0)?),
        _ => bail!("unknown device {s} (cpu|metal)"),
    }
}

pub fn parse_dtype(s: &str) -> Result<DType> {
    match s {
        "f16" => Ok(DType::F16),
        "bf16" => Ok(DType::BF16),
        "f32" => Ok(DType::F32),
        _ => bail!("unknown dtype {s} (f16|bf16|f32)"),
    }
}
