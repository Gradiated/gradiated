ARG SGLANG_IMAGE=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6

FROM ubuntu:24.04 AS desmond-build
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --yes --no-install-recommends cmake ninja-build g++ ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY . /src
RUN cmake -S /src -B /build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_TESTING=OFF \
      -DCMAKE_EXE_LINKER_FLAGS="-static-libstdc++ -static-libgcc" \
    && cmake --build /build --target desmondd \
    && cmake --install /build --prefix /opt/desmond

FROM ${SGLANG_IMAGE}
COPY --from=desmond-build /opt/desmond/bin/desmondd /usr/local/bin/desmondd

ENV DESMOND_CONTROL_HOST=0.0.0.0 \
    DESMOND_CONTROL_PORT=9090 \
    DESMOND_RUNTIME_HOST=127.0.0.1 \
    DESMOND_RUNTIME_PORT=30000 \
    DESMOND_RUNTIME_HEALTH_PATH=/health \
    DESMOND_MODEL=google/gemma-4-31B-it \
    DESMOND_MODEL_REVISION=b9ea41a2887d8607f594846523f94c6cc75ac8a4 \
    DESMOND_RELEASE=sglang-v0.5.13-gemma4-h200-v1 \
    DESMOND_PROFILING_PORT=80 \
    DESMOND_PROFILING_PATH=/v1/profiling-events \
    HF_HOME=/var/lib/gradiated/huggingface \
    TRANSFORMERS_CACHE=/var/lib/gradiated/huggingface

EXPOSE 30000 9090
ENTRYPOINT ["/usr/local/bin/desmondd", "--"]
CMD ["python3", "-m", "sglang.launch_server", "--model-path", "google/gemma-4-31B-it", "--tokenizer-path", "google/gemma-4-31B-it", "--revision", "b9ea41a2887d8607f594846523f94c6cc75ac8a4", "--served-model-name", "google/gemma-4-31B-it", "--dtype", "bfloat16", "--tp-size", "1", "--context-length", "8192", "--max-running-requests", "16", "--mem-fraction-static", "0.85", "--enable-metrics", "--tool-call-parser", "gemma4", "--log-level", "warning", "--host", "0.0.0.0", "--port", "30000"]
