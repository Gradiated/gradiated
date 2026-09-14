FROM rust:1.97-bookworm@sha256:0e2bcaef56d041a486784e54104a81aebe0da44bd03019bd70bc0401e42e4a97 AS build
WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY src ./src
COPY examples ./examples
RUN cargo build --release --locked --bins --examples

FROM debian:bookworm-slim@sha256:88200866dfff7ea7f5cbcb6ec7c8a701889efe6fe859fe64d6990e4b07ea4171 AS runtime
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends openssh-server procps passwd \
    && rm -rf /var/lib/apt/lists/* /etc/ssh/ssh_host_* \
    && dpkg-query -W > /usr/local/share/package-versions.txt
COPY --from=build /build/target/release/ssh-relay /usr/local/bin/ssh-relay
COPY sshd_config /etc/ssh/nomad-tunnel.conf
EXPOSE 2222
ENTRYPOINT ["/usr/local/bin/ssh-relay"]

FROM runtime AS integration
COPY --from=build /build/target/release/examples/echo /usr/local/bin/test-echo

FROM runtime AS production
