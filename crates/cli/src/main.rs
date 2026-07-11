use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use sartor_spec::StackConfig;
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "sartor", about = "full-stack inference co-design environment")]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Simulate one stack config -> perf + cost JSON.
    Run {
        #[arg(long)]
        config: PathBuf,
        /// Append JSONL result here.
        #[arg(long)]
        out: Option<PathBuf>,
    },
    /// Sweep dotted config keys: --set serving.max_batch=1,8,32,64
    /// (multiple --set flags form a cartesian product).
    Sweep {
        #[arg(long)]
        config: PathBuf,
        #[arg(long = "set")]
        sets: Vec<String>,
        #[arg(long)]
        out: Option<PathBuf>,
    },
    /// Run anchor configs and compare simulated vs measured throughput.
    Calibrate {
        /// JSONL: {"config": "path.toml", "measured_output_tok_per_s": 977.0, "note": "..."}
        #[arg(long)]
        anchors: PathBuf,
    },
}

fn run_one(cfg: &StackConfig) -> Result<serde_json::Value> {
    let perf = sartor_perf::simulate(cfg);
    let cost = sartor_cost::cost(&cfg.hardware, &cfg.cost, &perf);
    Ok(serde_json::json!({
        "model": cfg.model.name,
        "hardware": cfg.hardware.name,
        "kernel": cfg.kernel.name,
        "serving": cfg.serving.name,
        "workload": cfg.workload.name,
        "perf": perf,
        "cost": cost,
    }))
}

fn emit(v: &serde_json::Value, out: &Option<PathBuf>) -> Result<()> {
    let line = serde_json::to_string(v)?;
    println!("{line}");
    if let Some(p) = out {
        if let Some(dir) = p.parent() {
            std::fs::create_dir_all(dir)?;
        }
        use std::io::Write;
        let mut f = std::fs::OpenOptions::new().create(true).append(true).open(p)?;
        writeln!(f, "{line}")?;
    }
    Ok(())
}

/// Set a dotted key in a toml value tree.
fn set_key(v: &mut toml::Value, dotted: &str, raw: &str) -> Result<()> {
    let mut cur = v;
    let parts: Vec<&str> = dotted.split('.').collect();
    for p in &parts[..parts.len() - 1] {
        cur = cur
            .get_mut(p)
            .with_context(|| format!("no key {p} in config"))?;
    }
    let leaf = parts.last().unwrap();
    let existing = cur.get(leaf);
    let new: toml::Value = match existing {
        Some(toml::Value::Integer(_)) => toml::Value::Integer(raw.parse()?),
        Some(toml::Value::Float(_)) => toml::Value::Float(raw.parse()?),
        Some(toml::Value::Boolean(_)) => toml::Value::Boolean(raw.parse()?),
        _ => toml::Value::String(raw.into()),
    };
    cur.as_table_mut()
        .with_context(|| format!("{dotted} parent not a table"))?
        .insert(leaf.to_string(), new);
    Ok(())
}

fn main() -> Result<()> {
    match Cli::parse().cmd {
        Cmd::Run { config, out } => {
            let cfg = StackConfig::from_toml(&std::fs::read_to_string(&config)?)?;
            emit(&run_one(&cfg)?, &out)?;
        }
        Cmd::Sweep { config, sets, out } => {
            let base: toml::Value = std::fs::read_to_string(&config)?.parse()?;
            let axes: Vec<(String, Vec<String>)> = sets
                .iter()
                .map(|s| {
                    let (k, vs) = s.split_once('=').context("--set needs key=v1,v2")?;
                    Ok((k.to_string(), vs.split(',').map(String::from).collect()))
                })
                .collect::<Result<_>>()?;
            let mut combos: Vec<Vec<(String, String)>> = vec![vec![]];
            for (k, vs) in &axes {
                combos = combos
                    .into_iter()
                    .flat_map(|c| {
                        vs.iter().map(move |v| {
                            let mut c2 = c.clone();
                            c2.push((k.clone(), v.clone()));
                            c2
                        }).collect::<Vec<_>>()
                    })
                    .collect();
            }
            anyhow::ensure!(combos.len() <= 10_000, "sweep too large: {}", combos.len());
            for combo in combos {
                let mut v = base.clone();
                for (k, val) in &combo {
                    set_key(&mut v, k, val)?;
                }
                let cfg: StackConfig = v.try_into()?;
                let mut res = run_one(&cfg)?;
                res["sweep"] = serde_json::json!(combo
                    .iter()
                    .map(|(k, val)| format!("{k}={val}"))
                    .collect::<Vec<_>>());
                emit(&res, &out)?;
            }
        }
        Cmd::Calibrate { anchors } => {
            let raw = std::fs::read_to_string(&anchors)?;
            let mut worst: f64 = 0.0;
            for line in raw.lines().filter(|l| !l.trim().is_empty() && !l.trim_start().starts_with('#')) {
                let a: serde_json::Value = serde_json::from_str(line)?;
                let cfg_path = a["config"].as_str().context("anchor needs config")?;
                let measured = a["measured_output_tok_per_s"]
                    .as_f64()
                    .context("anchor needs measured_output_tok_per_s")?;
                let base = anchors.parent().unwrap_or(std::path::Path::new("."));
                let cfg =
                    StackConfig::from_toml(&std::fs::read_to_string(base.join(cfg_path))?)?;
                let perf = sartor_perf::simulate(&cfg);
                let err = (perf.output_tok_per_s - measured) / measured * 100.0;
                worst = worst.max(err.abs());
                println!(
                    "{:<40} sim {:>9.1} vs measured {:>9.1} tok/s  err {:>+6.1}%  {}",
                    cfg_path,
                    perf.output_tok_per_s,
                    measured,
                    err,
                    a["note"].as_str().unwrap_or("")
                );
            }
            println!("worst |err|: {worst:.1}%");
        }
    }
    Ok(())
}
