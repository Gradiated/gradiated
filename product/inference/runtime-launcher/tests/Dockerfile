FROM ubuntu:24.04@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254 AS toolchain
COPY --from=alpine:3.22@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
RUN sed -i 's|http://|https://|g' /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    cmake make g++ ca-certificates curl python3 jq clang-format shellcheck shfmt libarchive-tools libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*
FROM toolchain AS tests
ENV GRADIATED_TEST_CONTAINER=1
WORKDIR /src
COPY runtime-launcher/ .
COPY gpu/fetch-runtime.sh /opt/gradiated/bin/fetch-runtime
COPY gpu/download-runtime.py /tests/download-runtime.py
COPY gpu/download_runtime_test.py /tests/test_download_runtime.py
RUN mkdir -p /etc/gradiated && printf 'test-base-v1\n' > /etc/gradiated/base-id
RUN cmake -S . -B /build -DBUILD_TESTING=ON && cmake --build /build --parallel 2
RUN clang-format --dry-run --Werror *.cpp *.h tests/*.cpp
RUN shfmt -d -i 2 -ci tests/*.sh tests/fixtures/*.sh
RUN shellcheck -x -P tests tests/*.sh tests/fixtures/*.sh
RUN ctest --test-dir /build --output-on-failure
RUN python3 -m unittest discover -s /tests -p test_download_runtime.py

RUN shellcheck /opt/gradiated/bin/fetch-runtime
