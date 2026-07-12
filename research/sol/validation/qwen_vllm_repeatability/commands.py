from __future__ import annotations

from pathlib import Path

from .schema import CampaignSpec


def build_server_command(spec: CampaignSpec) -> tuple[str, ...]:
    engine = spec.engine
    command = (
        str(engine.python),
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        str(engine.model_path),
        "--served-model-name",
        engine.served_model_name,
        "--host",
        engine.host,
        "--port",
        str(engine.port),
        "--seed",
        str(spec.workload.dataset_seed),
        "--max-model-len",
        "512",
        "--max-num-seqs",
        "8",
        "--enforce-eager",
        "--disable-log-stats",
        "--no-enable-log-requests",
        "--disable-uvicorn-access-log",
    )
    return command + spec.engine.server_arguments


def build_benchmark_command(
    spec: CampaignSpec,
    concurrency: int,
    prompts_path: Path,
    output_path: Path,
    request_id_prefix: str,
) -> tuple[str, ...]:
    workload = spec.workload
    return (
        str(spec.engine.python),
        "-m",
        "vllm.entrypoints.cli.main",
        "bench",
        "serve",
        "--backend",
        "openai",
        "--base-url",
        f"http://{spec.engine.host}:{spec.engine.port}",
        "--endpoint",
        "/v1/completions",
        "--model",
        spec.engine.served_model_name,
        "--tokenizer",
        str(spec.engine.model_path),
        "--dataset-name",
        "custom",
        "--dataset-path",
        str(prompts_path),
        "--disable-shuffle",
        "--skip-chat-template",
        "--num-prompts",
        str(workload.num_prompts),
        "--output-len",
        str(workload.output_tokens),
        "--request-rate",
        workload.request_rate,
        "--max-concurrency",
        str(concurrency),
        "--seed",
        str(workload.dataset_seed),
        "--extra-body",
        '{"seed":0,"temperature":0}',
        "--ignore-eos",
        "--request-id-prefix",
        request_id_prefix,
        "--metric-percentiles",
        "50,95,99",
        "--disable-tqdm",
        "--save-result",
        "--save-detailed",
        "--result-dir",
        str(output_path.parent),
        "--result-filename",
        output_path.name,
    )
