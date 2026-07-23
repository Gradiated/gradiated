from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import pathlib
import platform
import traceback


MODULES = {
    "cuda_graph_runner": "sglang.srt.model_executor.cuda_graph_runner",
    "model_runner": "sglang.srt.model_executor.model_runner",
    "tp_worker": "sglang.srt.managers.tp_worker",
    "scheduler": "sglang.srt.managers.scheduler",
    "schedule_batch": "sglang.srt.managers.schedule_batch",
    "batch_result_processor": "sglang.srt.managers.scheduler_components.batch_result_processor",
    "sampler": "sglang.srt.layers.sampler",
    "sampling_batch_info": "sglang.srt.sampling.sampling_batch_info",
    "penalizer_orchestrator": "sglang.srt.sampling.penaltylib.orchestrator",
}

CPP_SOURCE = """
#include <torch/extension.h>
int run_conditional_loop_cuda(torch::Tensor counter);
"""

CUDA_SOURCE = r"""
#include <torch/extension.h>
#include <cuda_runtime.h>

static void check_cuda(cudaError_t error, const char* operation) {
  TORCH_CHECK(error == cudaSuccess, operation, ": ", cudaGetErrorString(error));
}

__global__ void loop_body(int* counter, cudaGraphConditionalHandle handle) {
  int value = atomicAdd(counter, 1) + 1;
  cudaGraphSetConditional(handle, value < 4 ? 1 : 0);
}

int run_conditional_loop_cuda(torch::Tensor counter) {
  TORCH_CHECK(counter.is_cuda(), "counter must be CUDA");
  TORCH_CHECK(counter.scalar_type() == torch::kInt32, "counter must be int32");
  TORCH_CHECK(counter.numel() == 1 && counter.is_contiguous(), "counter must be contiguous scalar");

  cudaGraph_t graph;
  cudaGraphExec_t graph_exec;
  cudaGraphNode_t node;
  check_cuda(cudaGraphCreate(&graph, 0), "cudaGraphCreate");

  cudaGraphConditionalHandle handle;
  check_cuda(
      cudaGraphConditionalHandleCreate(
          &handle, graph, 1, cudaGraphCondAssignDefault),
      "cudaGraphConditionalHandleCreate");

  cudaGraphNodeParams conditional = {cudaGraphNodeTypeConditional};
  conditional.conditional.handle = handle;
  conditional.conditional.type = cudaGraphCondTypeWhile;
  conditional.conditional.size = 1;
  check_cuda(
      cudaGraphAddNode(&node, graph, nullptr, nullptr, 0, &conditional),
      "cudaGraphAddNode(conditional)");

  cudaGraph_t body_graph = conditional.conditional.phGraph_out[0];
  int* counter_ptr = counter.data_ptr<int>();
  void* args[] = {&counter_ptr, &handle};
  cudaGraphNodeParams kernel = {cudaGraphNodeTypeKernel};
  kernel.kernel.func = reinterpret_cast<void*>(loop_body);
  kernel.kernel.gridDim = dim3(1, 1, 1);
  kernel.kernel.blockDim = dim3(1, 1, 1);
  kernel.kernel.sharedMemBytes = 0;
  kernel.kernel.kernelParams = args;
  kernel.kernel.extra = nullptr;
  cudaGraphNode_t body_node;
  check_cuda(
      cudaGraphAddNode(&body_node, body_graph, nullptr, nullptr, 0, &kernel),
      "cudaGraphAddNode(body)");

  check_cuda(
      cudaGraphInstantiate(&graph_exec, graph, nullptr, nullptr, 0),
      "cudaGraphInstantiate");
  check_cuda(cudaGraphLaunch(graph_exec, nullptr), "cudaGraphLaunch");
  check_cuda(cudaDeviceSynchronize(), "cudaDeviceSynchronize");
  check_cuda(cudaGraphExecDestroy(graph_exec), "cudaGraphExecDestroy");
  check_cuda(cudaGraphDestroy(graph), "cudaGraphDestroy");
  return 4;
}
"""


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def live_sources() -> dict[str, dict[str, object]]:
    rows = {}
    for label, module_name in MODULES.items():
        module = importlib.import_module(module_name)
        path = pathlib.Path(inspect.getsourcefile(module) or module.__file__).resolve()
        rows[label] = {
            "module": module_name,
            "path": str(path),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
    return rows


def source_contract() -> dict[str, object]:
    graph_runner = inspect.getsource(
        importlib.import_module(MODULES["cuda_graph_runner"]).CudaGraphRunner
    )
    tp_worker = inspect.getsource(
        importlib.import_module(MODULES["tp_worker"]).TpModelWorker
    )
    scheduler = inspect.getsource(
        importlib.import_module(MODULES["scheduler"]).Scheduler
    )
    result_processor = inspect.getsource(
        importlib.import_module(
            MODULES["batch_result_processor"]
        ).SchedulerBatchResultProcessor
    )
    schedule_batch = inspect.getsource(
        importlib.import_module(MODULES["schedule_batch"]).ScheduleBatch
    )

    checks = {
        "graph_capture_calls_model_forward": "logits_output_or_pp_proxy_tensors = forward("
        in graph_runner,
        "graph_capture_contains_sampler": "model_runner.sample(" in graph_runner,
        "worker_samples_after_forward": "batch_result.next_token_ids = self.model_runner.sample("
        in tp_worker,
        "scheduler_processes_each_batch_on_host": "self.process_batch_result(batch, result)"
        in scheduler,
        "scheduler_prepares_next_decode_on_host": "batch.prepare_for_decode()" in scheduler,
        "result_tokens_cross_to_host_list": "next_token_ids = next_token_ids.tolist()"
        in result_processor,
        "finish_state_is_python_request_state": "req.update_finish_state(new_accepted_len)"
        in result_processor,
        "output_ids_are_python_request_state": "req.output_ids.append(next_token_id)"
        in result_processor,
        "next_kv_slot_allocated_outside_graph": "self.out_cache_loc = alloc_for_decode(self, token_per_req=1)"
        in schedule_batch,
    }
    return {
        "checks": checks,
        "full_body_already_graph_capturable": bool(
            checks["graph_capture_calls_model_forward"]
            and checks["graph_capture_contains_sampler"]
            and not checks["result_tokens_cross_to_host_list"]
            and not checks["next_kv_slot_allocated_outside_graph"]
        ),
    }


def conditional_smoke(torch) -> dict[str, object]:
    from torch.utils.cpp_extension import load_inline

    counter = torch.zeros(1, dtype=torch.int32, device="cuda")
    extension = load_inline(
        name="gemma4_fixed4_conditional_graph",
        cpp_sources=CPP_SOURCE,
        cuda_sources=CUDA_SOURCE,
        functions=["run_conditional_loop_cuda"],
        extra_cuda_cflags=["-O2"],
        with_cuda=True,
        verbose=False,
    )
    extension.run_conditional_loop_cuda(counter)
    value = int(counter.item())
    return {
        "pass": value == 4,
        "counter": value,
        "scientific_invocation_began": True,
        "meaning": "CUDA conditional WHILE executes four device-selected iterations; this does not establish SGLang full-body composability.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    result: dict[str, object] = {
        "schema_version": 1,
        "status": "terminal",
        "candidate": "fixed_repeat_four_device_conditional_full_decode_graph",
        "scientific_invocation_began": False,
    }
    try:
        import torch

        result["runtime"] = {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "torch_cuda": torch.version.cuda,
            "device": torch.cuda.get_device_name(0),
            "capability": list(torch.cuda.get_device_capability(0)),
            "compiled_cuda_version": int(torch._C._cuda_getCompiledVersion()),
        }
        result["live_sources"] = live_sources()
        result["source_contract"] = source_contract()
        graph_api = sorted(
            name
            for name in dir(torch.cuda.CUDAGraph)
            if "graph" in name.lower() or "raw" in name.lower() or "capture" in name.lower()
        )
        result["torch_graph_api"] = {
            "attributes": graph_api,
            "raw_graph_handle_exposed": any("raw" in name.lower() for name in graph_api),
        }
        result["conditional_node_smoke"] = conditional_smoke(torch)
        result["scientific_invocation_began"] = True

        source_ready = result["source_contract"]["full_body_already_graph_capturable"]
        raw_handle = result["torch_graph_api"]["raw_graph_handle_exposed"]
        conditional_ready = result["conditional_node_smoke"]["pass"]
        result["full_body_support"] = {
            "pass": bool(source_ready and raw_handle and conditional_ready),
            "source_body_ready": source_ready,
            "captured_graph_composition_handle_ready": raw_handle,
            "cuda_conditional_node_ready": conditional_ready,
        }
        if result["full_body_support"]["pass"]:
            result["classification"] = "full_body_candidate_runtime_support_present"
        else:
            result["classification"] = "full_body_device_continuation_not_composable_in_pinned_stack"
        result["pass"] = result["full_body_support"]["pass"]
    except Exception as exc:
        result.update(
            {
                "classification": "runtime_discriminator_failure",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "pass": False,
            }
        )

    temporary = args.output.with_suffix(args.output.suffix + ".part")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("classification") != "runtime_discriminator_failure" else 1


if __name__ == "__main__":
    raise SystemExit(main())
