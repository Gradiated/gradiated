#include <cuda_bf16.h>
#include <cuda_runtime.h>
#include <math.h>
#include <torch/extension.h>

// One CTA is request x KV head.  Every q-head in its GQA group walks precisely
// the supplied key order and maintains its own FP32 online-softmax recurrence.
extern "C" __global__ void m384_grouped_attention_sm90a(
    const __nv_bfloat16* q, const __nv_bfloat16* cache_k, const __nv_bfloat16* cache_v,
    const int* page_indices, const int* request_ids, const int* key_rows,
    __nv_bfloat16* out, int rows, int q_heads, int kv_heads, int head_dim, int max_keys) {
  int row=blockIdx.x, kvh=blockIdx.y, lane=threadIdx.x;
  if(row>=rows||lane>=head_dim||request_ids[row]<0) return;
  int group=q_heads/kv_heads;
  for(int g=0;g<group;g++) {
    int qh=kvh*group+g; float m=-INFINITY, l=0.f, acc=0.f; float scale=rsqrtf((float)head_dim);
    const __nv_bfloat16* qr=q+((long)row*q_heads+qh)*head_dim;
    for(int j=0;j<max_keys;j++) { int kr=key_rows[(long)row*max_keys+j]; if(kr<0) break;
      int pg=page_indices[kr]; const __nv_bfloat16* kk=cache_k+((long)pg*kv_heads+kvh)*head_dim;
      float dot=0.f; for(int d=0;d<head_dim;d++) dot+=__bfloat162float(qr[d])*__bfloat162float(kk[d]);
      float score=dot*scale, nm=fmaxf(m,score), a=expf(m-nm), b=expf(score-nm);
      const __nv_bfloat16* vv=cache_v+((long)pg*kv_heads+kvh)*head_dim;
      acc=acc*a+b*__bfloat162float(vv[lane]); l=l*a+b; m=nm;
    }
    out[((long)row*q_heads+qh)*head_dim+lane]=__float2bfloat16_rn(acc/l);
  }
}

torch::Tensor launch(torch::Tensor q, torch::Tensor ck, torch::Tensor cv, torch::Tensor pages, torch::Tensor requests, torch::Tensor keys) {
  auto out=torch::empty_like(q); int rows=q.size(0), hq=q.size(1), d=q.size(2), hkv=ck.size(1);
  m384_grouped_attention_sm90a<<<dim3(rows,hkv),d>>>(reinterpret_cast<const __nv_bfloat16*>(q.data_ptr()),reinterpret_cast<const __nv_bfloat16*>(ck.data_ptr()),reinterpret_cast<const __nv_bfloat16*>(cv.data_ptr()),pages.data_ptr<int>(),requests.data_ptr<int>(),keys.data_ptr<int>(),reinterpret_cast<__nv_bfloat16*>(out.data_ptr()),rows,hq,hkv,d,keys.size(1));
  TORCH_CHECK(cudaGetLastError() == cudaSuccess, "m384_grouped_attention_sm90a launch failed"); return out;
}
PYBIND11_MODULE(TORCH_EXTENSION_NAME,m){m.def("launch",&launch);}
