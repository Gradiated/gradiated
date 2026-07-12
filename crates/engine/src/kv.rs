use anyhow::Result;
use candle_core::{DType, Device, Tensor};
use std::sync::Mutex;

/// Slot-based preallocated KV cache.
///
/// Layout per layer: [max_slots, kv_heads, max_ctx, head_dim], contiguous.
/// Active sequences occupy slots [0, n_active) — the scheduler keeps slots
/// compacted (swap-remove on completion), so per-step tensors never need a
/// gather: attention reads are narrow() views, which are free.
///
/// This is a deliberate bet against paged KV: paging exists to fight
/// fragmentation and enable prefix sharing, but needs fused gather kernels to
/// be cheap. With a framework backend, slot-contiguous + explicit context
/// budget wins. See docs/DESIGN.md.
pub struct KvCache {
    /// (k, v) per layer.
    layers: Vec<(Tensor, Tensor)>,
    pub max_slots: usize,
    pub max_ctx: usize,
    kv_heads: usize,
    head_dim: usize,
    /// Decode scatter rows are identical for every layer within a step:
    /// cache the uploaded index tensor keyed by the positions that built it.
    decode_idx: Mutex<Option<(Vec<usize>, Tensor)>>,
}

impl KvCache {
    pub fn new(
        n_layers: usize,
        max_slots: usize,
        max_ctx: usize,
        kv_heads: usize,
        head_dim: usize,
        dtype: DType,
        dev: &Device,
    ) -> Result<Self> {
        let mut layers = Vec::with_capacity(n_layers);
        for _ in 0..n_layers {
            let k = Tensor::zeros((max_slots, kv_heads, max_ctx, head_dim), dtype, dev)?;
            let v = Tensor::zeros((max_slots, kv_heads, max_ctx, head_dim), dtype, dev)?;
            layers.push((k, v));
        }
        Ok(Self {
            layers,
            max_slots,
            max_ctx,
            kv_heads,
            head_dim,
            decode_idx: Mutex::new(None),
        })
    }

    /// Write a prefill chunk for one slot: k/v are [1, kv_heads, t, head_dim],
    /// written at positions [start, start+t). One in-place slice_set per tensor.
    pub fn write_prefill(&self, layer: usize, slot: usize, start: usize, k: &Tensor, v: &Tensor) -> Result<()> {
        let (kc, vc) = &self.layers[layer];
        kc.narrow(0, slot, 1)?.slice_set(k, 2, start)?;
        vc.narrow(0, slot, 1)?.slice_set(v, 2, start)?;
        Ok(())
    }

    /// Batched decode write: new k/v are [b, kv_heads, head_dim] for slots
    /// 0..b, written at per-slot positions. Single scatter_set per tensor:
    /// the cache is viewed as [(slot, kv_head, pos) rows, head_dim] and rows
    /// are addressed as (slot*kv_heads + h)*max_ctx + pos.
    pub fn write_decode(&self, layer: usize, positions: &[usize], k: &Tensor, v: &Tensor) -> Result<()> {
        let b = positions.len();
        let (kc, vc) = &self.layers[layer];
        let idx = self.decode_index(positions, kc.device())?;
        let flat_dims = (self.max_slots * self.kv_heads * self.max_ctx, self.head_dim);
        let src_k = k.reshape((b * self.kv_heads, self.head_dim))?;
        let src_v = v.reshape((b * self.kv_heads, self.head_dim))?;
        kc.reshape(flat_dims)?.scatter_set(&idx, &src_k, 0)?;
        vc.reshape(flat_dims)?.scatter_set(&idx, &src_v, 0)?;
        Ok(())
    }

    /// Build (or reuse) the scatter row-index tensor for a decode step. All
    /// layers of one step share identical positions, so the CPU build + upload
    /// happens once per step instead of once per layer.
    fn decode_index(&self, positions: &[usize], dev: &Device) -> Result<Tensor> {
        let mut cache = self.decode_idx.lock().unwrap();
        if let Some((pos, idx)) = cache.as_ref() {
            if pos == positions {
                return Ok(idx.clone());
            }
        }
        let b = positions.len();
        let mut rows = Vec::with_capacity(b * self.kv_heads);
        for (slot, &pos) in positions.iter().enumerate() {
            for h in 0..self.kv_heads {
                rows.push(((slot * self.kv_heads + h) * self.max_ctx + pos) as u32);
            }
        }
        let idx = Tensor::from_vec(rows, (b * self.kv_heads, 1), dev)?
            .broadcast_as((b * self.kv_heads, self.head_dim))?
            .contiguous()?;
        *cache = Some((positions.to_vec(), idx.clone()));
        Ok(idx)
    }

    /// Views over the first `b` slots, positions [0, upto): [b, kv_heads, upto, head_dim].
    /// Pure views — no copy.
    pub fn window(&self, layer: usize, b: usize, upto: usize) -> Result<(Tensor, Tensor)> {
        let (kc, vc) = &self.layers[layer];
        Ok((
            kc.narrow(0, 0, b)?.narrow(2, 0, upto)?,
            vc.narrow(0, 0, b)?.narrow(2, 0, upto)?,
        ))
    }

    /// Single-slot view, positions [0, upto): [1, kv_heads, upto, head_dim].
    pub fn slot_window(&self, layer: usize, slot: usize, upto: usize) -> Result<(Tensor, Tensor)> {
        let (kc, vc) = &self.layers[layer];
        Ok((
            kc.narrow(0, slot, 1)?.narrow(2, 0, upto)?,
            vc.narrow(0, slot, 1)?.narrow(2, 0, upto)?,
        ))
    }

    /// Move slot `from`'s first `len` positions into slot `to` (swap-remove on
    /// sequence completion). One copy per layer per k/v, amortized once per
    /// finished request.
    pub fn move_slot(&self, from: usize, to: usize, len: usize) -> Result<()> {
        if from == to || len == 0 {
            return Ok(());
        }
        for (kc, vc) in &self.layers {
            let ksrc = kc.narrow(0, from, 1)?.narrow(2, 0, len)?.contiguous()?;
            let vsrc = vc.narrow(0, from, 1)?.narrow(2, 0, len)?.contiguous()?;
            kc.narrow(0, to, 1)?.slice_set(&ksrc, 2, 0)?;
            vc.narrow(0, to, 1)?.slice_set(&vsrc, 2, 0)?;
        }
        Ok(())
    }
}
