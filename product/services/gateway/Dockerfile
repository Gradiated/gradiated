FROM rust:1.97-bookworm AS build

WORKDIR /app

COPY Cargo.toml Cargo.lock ./
COPY src ./src

RUN cargo build --locked --release

FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /app/target/release/gradiated-gateway /usr/local/bin/gradiated-gateway

USER 65532:65532

ENTRYPOINT ["gradiated-gateway"]
