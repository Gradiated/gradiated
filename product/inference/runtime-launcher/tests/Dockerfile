FROM ubuntu:24.04@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254
COPY --from=alpine:3.22@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
RUN sed -i 's|http://|https://|g' /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    cmake make g++ ca-certificates openssl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=hashicorp/nomad@sha256:b964829b94c5493f3b543bb409b60c335a9ca03f21d9fac8b4cdd2af18b331c9 /bin/nomad /usr/local/bin/nomad
WORKDIR /src
COPY . .
RUN cmake -S . -B /build && cmake --build /build --parallel 2
RUN timeout --kill-after=5s 60s bash tests/test.sh /build/runtime-launch
RUN timeout --kill-after=5s 60s bash tests/nomad-artifact.sh
