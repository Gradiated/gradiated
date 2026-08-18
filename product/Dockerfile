FROM node:22.23.2-bookworm-slim

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/aws-rds-us-east-1-bundle.pem

ADD --chmod=0444 https://truststore.pki.rds.amazonaws.com/us-east-1/us-east-1-bundle.pem /etc/ssl/certs/aws-rds-us-east-1-bundle.pem

RUN corepack enable

WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json tsconfig.base.json ./
COPY packages ./packages
COPY services ./services

RUN pnpm install --frozen-lockfile
RUN pnpm turbo run build --filter=@gradiated/api...

USER node

CMD ["node", "services/api/dist/server.js"]
