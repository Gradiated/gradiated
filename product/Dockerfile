FROM node:22.23.2-bookworm-slim AS build

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
ENV CI=true

RUN corepack enable

WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json tsconfig.base.json ./
COPY packages ./packages
COPY services ./services

RUN pnpm install --frozen-lockfile
RUN pnpm turbo run build --filter=@gradiated/api... --filter=@gradiated/worker...
RUN pnpm install --prod --offline --frozen-lockfile

FROM node:22.23.2-bookworm-slim

ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/aws-rds-us-east-1-bundle.pem

ADD --chmod=0444 https://truststore.pki.rds.amazonaws.com/us-east-1/us-east-1-bundle.pem /etc/ssl/certs/aws-rds-us-east-1-bundle.pem

WORKDIR /app

COPY --from=build --chown=node:node /app /app

USER node

CMD ["node", "services/api/dist/server.js"]
