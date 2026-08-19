FROM node:22.23.2-bookworm-slim AS build

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
ENV CI=true

RUN corepack enable

WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json tsconfig.base.json ./
COPY packages/config/package.json ./packages/config/package.json
COPY packages/contracts/package.json ./packages/contracts/package.json
COPY packages/control/package.json ./packages/control/package.json
COPY packages/valkey/package.json ./packages/valkey/package.json
COPY services/api/package.json ./services/api/package.json
COPY services/console/package.json ./services/console/package.json
COPY services/gateway/package.json ./services/gateway/package.json
COPY services/worker/package.json ./services/worker/package.json

RUN pnpm install --frozen-lockfile

COPY packages ./packages
COPY services ./services

RUN mkdir -p packages/*/.turbo services/*/.turbo \
  && pnpm turbo run build --filter=@gradiated/api... --filter=@gradiated/worker...
RUN pnpm install --prod --offline --force --frozen-lockfile \
  --filter=@gradiated/api... \
  --filter=@gradiated/worker...

FROM node:22.23.2-bookworm-slim

ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/aws-rds-us-east-1-bundle.pem

ADD --chmod=0444 https://truststore.pki.rds.amazonaws.com/us-east-1/us-east-1-bundle.pem /etc/ssl/certs/aws-rds-us-east-1-bundle.pem

WORKDIR /app

COPY --from=build --chown=node:node /app /app

USER node

CMD ["node", "services/api/dist/server.js"]
