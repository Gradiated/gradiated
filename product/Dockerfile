FROM node:22.23.2-bookworm-slim AS build

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
ENV CI=true

RUN corepack enable

WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json tsconfig.base.json ./
COPY packages/analytics/package.json ./packages/analytics/package.json
COPY packages/config/package.json ./packages/config/package.json
COPY packages/contracts/package.json ./packages/contracts/package.json
COPY packages/control/package.json ./packages/control/package.json
COPY packages/credentials/package.json ./packages/credentials/package.json
COPY packages/temporal/package.json ./packages/temporal/package.json
COPY packages/valkey/package.json ./packages/valkey/package.json
COPY services/api/package.json ./services/api/package.json
COPY services/console/package.json ./services/console/package.json
COPY services/gateway/package.json ./services/gateway/package.json
COPY services/worker/package.json ./services/worker/package.json
COPY services/temporal-worker/package.json ./services/temporal-worker/package.json
COPY services/ops-mcp/package.json ./services/ops-mcp/package.json

RUN pnpm install --frozen-lockfile

COPY packages ./packages
COPY services ./services
COPY inference/gpu/ ./inference/gpu/
COPY inference/images/gpu-base/ ./inference/images/gpu-base/
COPY inference/tailscale/ ./inference/tailscale/

RUN mkdir -p packages/*/.turbo services/*/.turbo \
  && pnpm turbo run build --filter=@gradiated/api... --filter=@gradiated/worker... --filter=@gradiated/temporal-worker... --filter=@gradiated/ops-mcp...
# Reinstall only the runtime closure: an in-place --prod install keeps every
# build and test tool in the pnpm virtual store. better-auth still resolves
# drizzle-kit and vitest as optional peers, which bring esbuild's Go binaries;
# nothing at runtime imports esbuild, so remove it.
RUN rm -rf node_modules packages/*/node_modules services/*/node_modules \
  && pnpm install --prod --offline --frozen-lockfile \
  --filter=@gradiated/api... \
  --filter=@gradiated/worker... --filter=@gradiated/temporal-worker... --filter=@gradiated/ops-mcp... \
  && rm -rf node_modules/.pnpm/esbuild@* node_modules/.pnpm/@esbuild+*

FROM node:22.23.2-bookworm-slim

# Take Debian security updates published after the base image was built. The
# services start with node only, so drop the base image's package managers.
RUN apt-get update && apt-get upgrade -y \
  && apt-get install -y --no-install-recommends ca-certificates \
  && rm -rf /var/lib/apt/lists/* \
    /usr/local/lib/node_modules /opt/yarn-v* \
    /usr/local/bin/corepack /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/yarn /usr/local/bin/yarnpkg

ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/aws-rds-us-east-1-bundle.pem

RUN mkdir -p /etc/ssl/certs \
  && chmod 0755 /etc/ssl /etc/ssl/certs

ADD --chmod=0444 https://truststore.pki.rds.amazonaws.com/us-east-1/us-east-1-bundle.pem /etc/ssl/certs/aws-rds-us-east-1-bundle.pem

RUN chmod 0755 /etc/ssl /etc/ssl/certs \
  && chmod 0444 /etc/ssl/certs/aws-rds-us-east-1-bundle.pem

WORKDIR /app

COPY --from=build --chown=node:node /app /app

USER node

CMD ["node", "services/api/dist/server.js"]
