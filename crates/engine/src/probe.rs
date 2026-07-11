//! Op-level microbenchmarks on real engine shapes. Fingerprints where step
//! time goes on a given device — the raw data for the simulator's
//! per-hardware efficiency curves.
use crate::kv::KvCache;
use crate::model::Model;
use anyhow::Result;
use candle_core::{DType, Device, Tensor};
use std::time::Instant;

fn time_op<F: FnMut() -> Result<()>>(name: &str, dev: &Device, iters: usize, mut f: F) -> Result<f64> {
    // warmup
    for _ in 0..3 {
        f()?;
    }
    dev.synchronize()?;
    let t0 = Instant::now();
    for _ in 0..iters {
        f()?;
    }
    dev.synchronize()?;
    let us = t0.elapsed().as_secs_f64() * 1e6 / iters as f64;
    println!("{name:<44} {us:>10.1} us");
    Ok(us)
}

pub fn run_probe(model_dir: &std::path::Path, dev: &Device, dtype: DType, b: usize) -> Result<()> {
    let max_ctx = 2048;
    let m = Model::load(model_dir, dtype, dev, max_ctx)?;
    let cfg = &m.cfg;
    let (nkv, hd, d) = (cfg.num_key_value_heads, cfg.head_dim(), cfg.hidden_size);
    let l = 512usize; // attention window length to probe
    let kv = KvCache::new(cfg.num_hidden_layers, 64, max_ctx, nkv, hd, dtype, dev)?;
    println!(
        "probe: model={} layers={} b={} dev={:?} dtype={:?}",
        model_dir.display(),
        cfg.num_hidden_layers,
        b,
        dev.location(),
        dtype
    );

    // 0. dispatch floor: one trivial elementwise op
    let x1 = Tensor::zeros((b, d), dtype, dev)?;
    time_op("dispatch floor (1 add)", dev, 50, || {
        let _ = (&x1 + 1.0)?;
        Ok(())
    })?;

    // 1. fused qkv GEMM [b, d] @ [d, (nq+2kv)*hd]
    let w = Tensor::zeros(((cfg.num_attention_heads + 2 * nkv) * hd, d), dtype, dev)?;
    time_op("qkv GEMM", dev, 50, || {
        let _ = x1.matmul(&w.t()?)?;
        Ok(())
    })?;

    // 2. mlp GEMMs [b, d] @ [d, 2i] + [b, i] @ [i, d]
    let wgu = Tensor::zeros((2 * cfg.intermediate_size, d), dtype, dev)?;
    let wd = Tensor::zeros((d, cfg.intermediate_size), dtype, dev)?;
    let xi = Tensor::zeros((b, cfg.intermediate_size), dtype, dev)?;
    time_op("mlp gate_up GEMM", dev, 50, || {
        let _ = x1.matmul(&wgu.t()?)?;
        Ok(())
    })?;
    time_op("mlp down GEMM", dev, 50, || {
        let _ = xi.matmul(&wd.t()?)?;
        Ok(())
    })?;

    // 3. KV decode write (scatter_set) for one layer
    let kk = Tensor::zeros((b, nkv, hd), dtype, dev)?;
    let positions: Vec<usize> = (0..b).map(|i| 100 + i).collect();
    time_op("kv write_decode (1 layer)", dev, 50, || {
        kv.write_decode(0, &positions, &kk, &kk)?;
        Ok(())
    })?;

    // 4. decode attention for one layer at window l
    let g = cfg.group_size();
    let q = Tensor::zeros((b, nkv, g, hd), dtype, dev)?;
    let (kw, vw) = kv.window(0, b, l)?;
    time_op("attn qk^T (strided window)", dev, 50, || {
        let _ = q.matmul(&kw.transpose(2, 3)?)?;
        Ok(())
    })?;
    let att = Tensor::zeros((b, nkv, g, l), DType::F32, dev)?;
    time_op("softmax f32", dev, 50, || {
        let _ = candle_nn::ops::softmax_last_dim(&att)?;
        Ok(())
    })?;
    let attd = att.to_dtype(dtype)?;
    time_op("attn @V (strided window)", dev, 50, || {
        let _ = attd.matmul(&vw)?;
        Ok(())
    })?;

    // 5. lm_head [b, d] @ [d, vocab]
    let wv = Tensor::zeros((cfg.vocab_size, d), dtype, dev)?;
    time_op("lm_head GEMM", dev, 20, || {
        let _ = x1.matmul(&wv.t()?)?;
        Ok(())
    })?;

    // 6. logits -> host copy
    let logits = Tensor::zeros((b, cfg.vocab_size), DType::F32, dev)?;
    time_op("logits to host", dev, 20, || {
        let _ = logits.flatten_all()?.to_vec1::<f32>()?;
        Ok(())
    })?;

    // 7. rms_norm
    let alpha = Tensor::ones(d, dtype, dev)?;
    time_op("rms_norm", dev, 50, || {
        let _ = candle_nn::ops::rms_norm(&x1, &alpha, 1e-5)?;
        Ok(())
    })?;

    // 8. full decode step, end to end
    let toks: Vec<u32> = vec![1; b];
    time_op("FULL decode step (all layers)", dev, 10, || {
        let _ = m.decode(&kv, &positions, &toks)?;
        Ok(())
    })?;

    // 9. prefill chunk 512, end to end
    let ptoks: Vec<u32> = vec![1; 512];
    time_op("FULL prefill chunk 512", dev, 5, || {
        let _ = m.prefill(&kv, 63, 0, &ptoks, false)?;
        Ok(())
    })?;
    Ok(())
}
