ARG SGLANG_IMAGE=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6

FROM ${SGLANG_IMAGE} AS native-build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY . .
RUN cmake -S . -B /build \
      -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_TESTING=OFF \
      -DGRADIATED_ENGINE_ENABLE_CUDA=ON \
    && cmake --build /build -j"$(nproc)" --target desmondd gradiated-engine-runtime \
    && cmake --install /build --prefix /opt/gradiated

FROM ${SGLANG_IMAGE}

COPY --from=native-build /opt/gradiated/bin/desmondd /usr/local/bin/desmondd
COPY --from=native-build /opt/gradiated/bin/gradiated-engine-runtime /usr/local/bin/gradiated-engine-runtime

ENV DESMOND_CONTROL_HOST=0.0.0.0 \
    DESMOND_CONTROL_PORT=9090 \
    DESMOND_RUNTIME_HOST=127.0.0.1 \
    DESMOND_RUNTIME_PORT=30000 \
    DESMOND_RUNTIME_HEALTH_PATH=/health \
    DESMOND_RUNTIME_API_KEY_MODE=environment \
    DESMOND_RELEASE=native-gemma4-h200-v1 \
    DESMOND_MODEL=google/gemma-4-31B-it \
    DESMOND_MODEL_REVISION=b9ea41a2887d8607f594846523f94c6cc75ac8a4 \
    GRADIATED_RUNTIME_HOST=0.0.0.0 \
    GRADIATED_RUNTIME_PORT=30000

EXPOSE 30000 9090
ENTRYPOINT ["/usr/local/bin/desmondd", "--"]
CMD ["/usr/local/bin/gradiated-engine-runtime", "/root/.cache/huggingface/hub/models--google--gemma-4-31B-it/snapshots/b9ea41a2887d8607f594846523f94c6cc75ac8a4"]
