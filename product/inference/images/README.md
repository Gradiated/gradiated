# Model serving images

Each model has its own image and launch script. Build from that model directory.
Each image runs one vLLM replica. Nomad owns restart and health policy.
The images contain no Runpod bootstrap, SSH server, proxy credentials, or supervisor.

The current configurations require NVIDIA B300 GPUs. Other GPU models and
other tensor-parallel sizes need separate qualification.

| Image               | Replica | Runtime source              | Status                                       |
| ------------------- | ------- | --------------------------- | -------------------------------------------- |
| deepseek-v4-1-flash | TP4     | Image digest from PR #46    | Packaging added; image and GPU tests pending |
| glm-5-3-flash       | TP2     | Exact existing vLLM package | Base image digest and build required         |

## Build

Build DeepSeek from its directory with Docker, targeting linux/amd64.
GLM requires a RUNTIME_IMAGE build argument with a repository and SHA-256 digest.
The captured GLM source is commit `933876c388fb129ad82590660e6506614559cb86`
with local changes in `glm-5-3-flash/runtime.patch`. Its recorded packages are
vLLM `0.1.dev19910+g933876c38.d20260826`, PyTorch `2.13.0`, Transformers
`5.16.1`, Triton `3.7.1`, and FlashInfer `0.6.17`.
First package or locate that runtime and verify its CUDA dependencies.
Do not substitute a newer vLLM image to make the build pass. The Dockerfile checks
its package version. That check alone does not qualify the runtime.

Push qualified images and record the resulting image digests before deployment.
Use those digests in Nomad jobs or provider pod configuration.

## Runtime contract

- Assign two GPUs for GLM or four for DeepSeek. Launchers preserve the GPU mask.
- Mount the verified GLM snapshot and set GLM_MODEL_PATH. Its expected revision is
  84c6a6aa9497188e15a635ba793b0f95a79b1033. Deployment must verify the local files.
- DeepSeek loads its fixed artifact and tokenizer revision. Mount HF_HOME for cache.
- Set RUNTIME_PORT for each replica. It defaults to 8000.
- RUNTIME_HOST defaults to loopback for the current authenticated proxy.
  Set it to 0.0.0.0 only inside a network with restricted ingress.
- GLM retains the optional VLLM_MOE_BACKEND setting.
- DeepSeek retains SPECULATIVE_DECODING=1. Set 0 for the baseline.
- Inject credentials at deployment time. Do not bake them into images.
- Send SIGTERM to the entrypoint. It uses exec, so vLLM receives the signal.

## Runpod and Nomad

Runpod starts a provider pod from an image. This is separate from Nomad's task
driver. Do not assume a Nomad client inside that pod can start Docker containers.

Qualify the driver on the actual pod. If it uses raw_exec, the provider pod must
contain the pinned model runtime, while Nomad starts this launch script.
A model image alone does not supply the Nomad agent or GPU isolation. Client
bootstrap, device assignment, proxy, and reporter are the next integration step.

Keep the current infra/environments/prod/runpod files as the manual rollback path
until the Nomad migration passes. Keep their qualification evidence.

## Checks

Run: bash product/inference/images/tests/test_launch.sh

These checks verify launch arguments and environment handling without a GPU.
They do not establish image build success or serving correctness.
