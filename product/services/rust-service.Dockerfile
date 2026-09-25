# Builds every Rust service. The build context is the service's own directory, and
# the target stage names the service: `--target gateway`, `--target proxy` or
# `--target collector`.
FROM rust:1.97-bookworm@sha256:0e2bcaef56d041a486784e54104a81aebe0da44bd03019bd70bc0401e42e4a97 AS chef

RUN cargo install cargo-chef --version 0.1.78 --locked

WORKDIR /app

FROM chef AS planner

COPY . .

RUN cargo chef prepare --recipe-path recipe.json

FROM chef AS build

COPY --from=planner /app/recipe.json recipe.json

RUN cargo chef cook --locked --release --recipe-path recipe.json

COPY . .

RUN cargo build --locked --release

# libc, CA certificates and a non-root user: no shell and no package manager.
FROM gcr.io/distroless/cc-debian12:nonroot@sha256:9dac0a79194e45a7da0158a9c6da57b217585af0786db3845d1f0ec1a0dd182f AS runtime

USER 65532:65532

FROM runtime AS database-client

# Amazon RDS roots its certificate chain in its own authority, which the system
# trust store does not hold, so a managed instance cannot be verified without it.
COPY rds-ca-bundle.pem /etc/gradiated/rds-ca-bundle.pem

FROM database-client AS gateway

COPY --from=build /app/target/release/gradiated-gateway /usr/local/bin/gradiated-gateway

ENTRYPOINT ["/usr/local/bin/gradiated-gateway"]

FROM database-client AS proxy

COPY --from=build /app/target/release/gradiated-proxy /usr/local/bin/gradiated-proxy

ENTRYPOINT ["/usr/local/bin/gradiated-proxy"]

FROM runtime AS collector

COPY --from=build /app/target/release/gradiated-collector /usr/local/bin/gradiated-collector

ENTRYPOINT ["/usr/local/bin/gradiated-collector"]
