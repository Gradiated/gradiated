FROM rust:1.97-bookworm AS chef

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

FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /app/target/release/gradiated-proxy /usr/local/bin/gradiated-proxy

# Amazon RDS roots its certificate chain in its own authority, which the system
# trust store does not hold, so a managed instance cannot be verified without it.
COPY rds-ca-bundle.pem /etc/gradiated/rds-ca-bundle.pem

USER 65532:65532

ENTRYPOINT ["gradiated-proxy"]
