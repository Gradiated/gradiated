use crate::config::ModelConfig;
use crate::kv::KvCache;
use anyhow::{bail, Context, Result};
use candle_core::{DType, Device, Tensor};
use candle_nn::ops::{rms_norm, silu, softmax_last_dim};
use candle_nn::rotary_emb::rope;
use candle_nn::{Linear, Module, VarBuilder};
use std::path::Path;

struct Layer {
    ln1: Tensor,
    qkv: Linear,
    o: Linear,
    ln2: Tensor,
    gate_up: Linear,
    down: Linear,
}

/// Llama-family transformer with an external slot KV cache.
///
/// Two entry points instead of one general forward: `prefill` (one sequence,
/// a chunk of T tokens) and `decode` (batch of sequences, one token each).
/// GQA is computed by folding the group dimension into the matmul batch, so
/// K/V are never tiled/repeated — zero extra memory traffic for grouping.
pub struct Model {
    pub cfg: ModelConfig,
    embed: Tensor,
    layers: Vec<Layer>,
    norm: Tensor,
    lm_head: Linear,
    cos: Tensor,
    sin: Tensor,
    pub dtype: DType,
    pub device: Device,
    eps: f32,
}

impl Model {
    pub fn load(dir: &Path, dtype: DType, dev: &Device, max_ctx: usize) -> Result<Self> {
        let cfg = ModelConfig::load(dir)?;
        let mut files: Vec<_> = std::fs::read_dir(dir)?
            .filter_map(|e| e.ok().map(|e| e.path()))
            .filter(|p| p.extension().is_some_and(|x| x == "safetensors"))
            .collect();
        files.sort();
        if files.is_empty() {
            bail!("no .safetensors in {}", dir.display());
        }
        let vb = unsafe { VarBuilder::from_mmaped_safetensors(&files, dtype, dev)? };
        Self::from_varbuilder(vb, cfg, dtype, dev, max_ctx)
    }

    pub fn from_varbuilder(
        vb: VarBuilder,
        cfg: ModelConfig,
        dtype: DType,
        dev: &Device,
        max_ctx: usize,
    ) -> Result<Self> {
        let (d, hd) = (cfg.hidden_size, cfg.head_dim());
        let (nh, nkv, ni) = (
            cfg.num_attention_heads,
            cfg.num_key_value_heads,
            cfg.intermediate_size,
        );
        let vm = vb.pp("model");
        let embed = vm.get((cfg.vocab_size, d), "embed_tokens.weight")?;
        let mut layers = Vec::with_capacity(cfg.num_hidden_layers);
        for i in 0..cfg.num_hidden_layers {
            let vl = vm.pp(format!("layers.{i}"));
            let va = vl.pp("self_attn");
            let q = va.get((nh * hd, d), "q_proj.weight")?;
            let k = va.get((nkv * hd, d), "k_proj.weight")?;
            let v = va.get((nkv * hd, d), "v_proj.weight")?;
            let qkv_w = Tensor::cat(&[&q, &k, &v], 0)?;
            let qkv_b = if cfg.attention_bias {
                Some(Tensor::cat(
                    &[
                        &va.get(nh * hd, "q_proj.bias")?,
                        &va.get(nkv * hd, "k_proj.bias")?,
                        &va.get(nkv * hd, "v_proj.bias")?,
                    ],
                    0,
                )?)
            } else {
                None
            };
            let vmlp = vl.pp("mlp");
            let gate = vmlp.get((ni, d), "gate_proj.weight")?;
            let up = vmlp.get((ni, d), "up_proj.weight")?;
            layers.push(Layer {
                ln1: vl.get(d, "input_layernorm.weight")?,
                qkv: Linear::new(qkv_w, qkv_b),
                o: Linear::new(va.get((d, nh * hd), "o_proj.weight")?, None),
                ln2: vl.get(d, "post_attention_layernorm.weight")?,
                gate_up: Linear::new(Tensor::cat(&[&gate, &up], 0)?, None),
                down: Linear::new(vmlp.get((d, ni), "down_proj.weight")?, None),
            });
        }
        let norm = vm.get(d, "norm.weight")?;
        let lm_head = if cfg.tie_word_embeddings {
            Linear::new(embed.clone(), None)
        } else {
            Linear::new(vb.get((cfg.vocab_size, d), "lm_head.weight")?, None)
        };
        let (cos, sin) = rope_tables(&cfg, max_ctx, dtype, dev)?;
        Ok(Self {
            eps: cfg.rms_norm_eps as f32,
            cfg,
            embed,
            layers,
            norm,
            lm_head,
            cos,
            sin,
            dtype,
            device: dev.clone(),
        })
    }

    /// Prefill a chunk of `tokens` for `slot` at positions [start, start+t).
    /// Returns logits [1, vocab] (f32) for the final position iff `want_logits`
    /// — computing the LM head for non-final prefill positions is pure waste.
    pub fn prefill(
        &self,
        kv: &KvCache,
        slot: usize,
        start: usize,
        tokens: &[u32],
        want_logits: bool,
    ) -> Result<Option<Tensor>> {
        let t = tokens.len();
        let l_ctx = start + t;
        let (nkv, g, hd) = (self.cfg.num_key_value_heads, self.cfg.group_size(), self.cfg.head_dim());
        let ids = Tensor::from_slice(tokens, t, &self.device)?;
        let mut x = self.embed.index_select(&ids, 0)?; // [t, d]

        // Causal mask for the merged (group, time) query dim: [1, 1, g*t, l_ctx].
        let mask = causal_mask(t, start, g, &self.device)?;
        // cos/sin for positions [start, start+t): broadcast over [1, kv, g, t, hd/2].
        let cos = self.cos.narrow(0, start, t)?;
        let sin = self.sin.narrow(0, start, t)?;

        for (li, layer) in self.layers.iter().enumerate() {
            let h = rms_norm(&x, &layer.ln1, self.eps)?;
            let qkv = layer.qkv.forward(&h)?;
            let q = qkv.narrow(1, 0, nkv * g * hd)?;
            let k = qkv.narrow(1, nkv * g * hd, nkv * hd)?;
            let v = qkv.narrow(1, nkv * (g + 1) * hd, nkv * hd)?;

            // q: [t, kv*g*hd] -> [1, kv*g, t, hd] (fused rope wants rank-4 contiguous)
            let q = q
                .reshape((t, nkv, g, hd))?
                .permute((1, 2, 0, 3))?
                .contiguous()?
                .reshape((1, nkv * g, t, hd))?;
            let q = rope(&q, &cos, &sin)?;
            // k,v: [t, kv*hd] -> [1, kv, t, hd]
            let k = k
                .reshape((t, nkv, hd))?
                .transpose(0, 1)?
                .contiguous()?
                .reshape((1, nkv, t, hd))?;
            let v = v
                .reshape((t, nkv, hd))?
                .transpose(0, 1)?
                .contiguous()?
                .reshape((1, nkv, t, hd))?;
            let k = rope(&k, &cos, &sin)?;
            kv.write_prefill(li, slot, start, &k, &v)?;

            let (kw, vw) = kv.slot_window(li, slot, l_ctx)?;
            // [1, kv, g*t, hd] @ [1, kv, hd, l] -> [1, kv, g*t, l]
            let qm = q.reshape((1, nkv, g * t, hd))?;
            let att = (qm.matmul(&kw.transpose(2, 3)?)? * (1.0 / (hd as f64).sqrt()))?;
            let att = att.to_dtype(DType::F32)?.broadcast_add(&mask)?;
            let att = softmax_last_dim(&att)?.to_dtype(self.dtype)?;
            let out = att.matmul(&vw)?; // [1, kv, g*t, hd]
            let out = out
                .reshape((nkv, g, t, hd))?
                .permute((2, 0, 1, 3))?
                .contiguous()?
                .reshape((t, nkv * g * hd))?;
            x = (x + layer.o.forward(&out)?)?;

            let h2 = rms_norm(&x, &layer.ln2, self.eps)?;
            let gu = layer.gate_up.forward(&h2)?;
            let gate = gu.narrow(1, 0, self.cfg.intermediate_size)?;
            let up = gu.narrow(1, self.cfg.intermediate_size, self.cfg.intermediate_size)?;
            x = (x + layer.down.forward(&(silu(&gate)? * up)?)?)?;
        }
        if !want_logits {
            return Ok(None);
        }
        let last = x.narrow(0, t - 1, 1)?;
        let last = rms_norm(&last, &self.norm, self.eps)?;
        Ok(Some(self.lm_head.forward(&last)?.to_dtype(DType::F32)?))
    }

    /// One decode step for slots 0..positions.len(); token[i] goes to slot i at
    /// positions[i]. Returns logits [b, vocab] (f32).
    pub fn decode(&self, kv: &KvCache, positions: &[usize], tokens: &[u32]) -> Result<Tensor> {
        let b = tokens.len();
        let (nkv, g, hd) = (self.cfg.num_key_value_heads, self.cfg.group_size(), self.cfg.head_dim());
        let l_ctx = positions.iter().max().unwrap() + 1;
        let ids = Tensor::from_slice(tokens, b, &self.device)?;
        let mut x = self.embed.index_select(&ids, 0)?; // [b, d]

        // [b, 1, 1, l_ctx] in model dtype: softmax_last_dim handles f16 with
        // f32 exp-sum accumulation on Metal, so no f32 round-trip is needed.
        let mask = length_mask(positions, l_ctx, &self.device)?.to_dtype(self.dtype)?;
        let pos_ids = Tensor::from_vec(
            positions.iter().map(|&p| p as u32).collect::<Vec<_>>(),
            b,
            &self.device,
        )?;
        // Rank-3 [b, 1, hd/2]: per-slot positions via the rope kernel's batched cos path.
        let cos = self.cos.index_select(&pos_ids, 0)?.reshape((b, 1, hd / 2))?;
        let sin = self.sin.index_select(&pos_ids, 0)?.reshape((b, 1, hd / 2))?;

        for (li, layer) in self.layers.iter().enumerate() {
            let h = rms_norm(&x, &layer.ln1, self.eps)?;
            let qkv = layer.qkv.forward(&h)?;
            let q = qkv
                .narrow(1, 0, nkv * g * hd)?
                .reshape((b, nkv * g, 1, hd))?
                .contiguous()?;
            let k = qkv
                .narrow(1, nkv * g * hd, nkv * hd)?
                .reshape((b, nkv, 1, hd))?
                .contiguous()?;
            let v = qkv
                .narrow(1, nkv * (g + 1) * hd, nkv * hd)?
                .reshape((b, nkv, hd))?;
            let q = rope(&q, &cos, &sin)?.reshape((b, nkv, g, hd))?;
            let k = rope(&k, &cos, &sin)?.reshape((b, nkv, hd))?;
            kv.write_decode(li, positions, &k, &v.contiguous()?)?;

            let (kw, vw) = kv.window(li, b, l_ctx)?;
            let att = (q.matmul(&kw.transpose(2, 3)?)? * (1.0 / (hd as f64).sqrt()))?; // [b, kv, g, l]
            let att = softmax_last_dim(&att.broadcast_add(&mask)?)?;
            let out = att.matmul(&vw)?.reshape((b, nkv * g * hd))?;
            x = (x + layer.o.forward(&out)?)?;

            let h2 = rms_norm(&x, &layer.ln2, self.eps)?;
            let gu = layer.gate_up.forward(&h2)?;
            let gate = gu.narrow(1, 0, self.cfg.intermediate_size)?;
            let up = gu.narrow(1, self.cfg.intermediate_size, self.cfg.intermediate_size)?;
            x = (x + layer.down.forward(&(silu(&gate)? * up)?)?)?;
        }
        let x = rms_norm(&x, &self.norm, self.eps)?;
        Ok(self.lm_head.forward(&x)?.to_dtype(DType::F32)?)
    }
}

fn rope_tables(cfg: &ModelConfig, max_ctx: usize, dtype: DType, dev: &Device) -> Result<(Tensor, Tensor)> {
    let hd = cfg.head_dim();
    let half = hd / 2;
    let theta = cfg.rope_theta as f32;
    let mut cos = Vec::with_capacity(max_ctx * half);
    let mut sin = Vec::with_capacity(max_ctx * half);
    for p in 0..max_ctx {
        for i in 0..half {
            let freq = (p as f32) / theta.powf(2.0 * i as f32 / hd as f32);
            cos.push(freq.cos());
            sin.push(freq.sin());
        }
    }
    Ok((
        Tensor::from_vec(cos, (max_ctx, half), dev)?.to_dtype(dtype)?,
        Tensor::from_vec(sin, (max_ctx, half), dev)?.to_dtype(dtype)?,
    ))
}

/// Causal mask for a prefill chunk with the group dim folded into rows:
/// [1, 1, g*t, start+t], row (j*t + ti) may attend to columns <= start+ti.
fn causal_mask(t: usize, start: usize, g: usize, dev: &Device) -> Result<Tensor> {
    let l = start + t;
    let mut m = vec![0f32; t * l];
    for ti in 0..t {
        for c in (start + ti + 1)..l {
            m[ti * l + c] = f32::NEG_INFINITY;
        }
    }
    let base = Tensor::from_vec(m, (t, l), dev)?;
    let tiled = Tensor::cat(&vec![&base; g], 0)?; // [g*t, l]
    Ok(tiled.reshape((1, 1, g * t, l))?)
}

/// Per-slot length mask for decode: [b, 1, 1, l], slot i attends to <= pos_i.
fn length_mask(positions: &[usize], l: usize, dev: &Device) -> Result<Tensor> {
    let b = positions.len();
    let mut m = vec![0f32; b * l];
    for (i, &p) in positions.iter().enumerate() {
        for c in (p + 1)..l {
            m[i * l + c] = f32::NEG_INFINITY;
        }
    }
    Ok(Tensor::from_vec(m, (b, 1, 1, l), dev)?)
}

/// Generate a random-weight model dir from a config.json — identical compute
/// cost to real weights, for benchmarking without downloads.
pub fn make_random_model(config_json: &Path, out_dir: &Path, dtype: DType) -> Result<()> {
    let raw = std::fs::read_to_string(config_json).context("reading config")?;
    let cfg: ModelConfig = serde_json::from_str(&raw)?;
    let dev = Device::Cpu;
    let (d, hd) = (cfg.hidden_size, cfg.head_dim());
    let (nh, nkv, ni, v) = (
        cfg.num_attention_heads,
        cfg.num_key_value_heads,
        cfg.intermediate_size,
        cfg.vocab_size,
    );
    let mut tensors = std::collections::HashMap::new();
    let mut add = |name: String, dims: Vec<usize>| -> Result<()> {
        let t = (Tensor::randn(0f32, 0.02f32, dims, &dev)?).to_dtype(dtype)?;
        tensors.insert(name, t);
        Ok(())
    };
    add("model.embed_tokens.weight".into(), vec![v, d])?;
    for i in 0..cfg.num_hidden_layers {
        let p = format!("model.layers.{i}");
        add(format!("{p}.self_attn.q_proj.weight"), vec![nh * hd, d])?;
        add(format!("{p}.self_attn.k_proj.weight"), vec![nkv * hd, d])?;
        add(format!("{p}.self_attn.v_proj.weight"), vec![nkv * hd, d])?;
        add(format!("{p}.self_attn.o_proj.weight"), vec![d, nh * hd])?;
        if cfg.attention_bias {
            add(format!("{p}.self_attn.q_proj.bias"), vec![nh * hd])?;
            add(format!("{p}.self_attn.k_proj.bias"), vec![nkv * hd])?;
            add(format!("{p}.self_attn.v_proj.bias"), vec![nkv * hd])?;
        }
        add(format!("{p}.mlp.gate_proj.weight"), vec![ni, d])?;
        add(format!("{p}.mlp.up_proj.weight"), vec![ni, d])?;
        add(format!("{p}.mlp.down_proj.weight"), vec![d, ni])?;
        add(format!("{p}.input_layernorm.weight"), vec![d])?;
        add(format!("{p}.post_attention_layernorm.weight"), vec![d])?;
    }
    add("model.norm.weight".into(), vec![d])?;
    if !cfg.tie_word_embeddings {
        add("lm_head.weight".into(), vec![v, d])?;
    }
    // LayerNorm weights should be ~1, not ~0.02.
    for (name, t) in tensors.iter_mut() {
        if name.contains("layernorm") || name.ends_with("norm.weight") {
            *t = Tensor::ones(t.dims(), dtype, &dev)?;
        }
    }
    std::fs::create_dir_all(out_dir)?;
    candle_core::safetensors::save(&tensors, out_dir.join("model.safetensors"))?;
    std::fs::copy(config_json, out_dir.join("config.json"))?;
    Ok(())
}
