# Build from the repository root; the adjacent ignore file is an allowlist.
# This manifest-list digest supports both linux/amd64 and linux/arm64.
FROM node:24.20.0-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS build
WORKDIR /workspace
ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_OPTIONS=--max-old-space-size=3072 \
    FEL_DEPLOYMENT_MODE=fixture \
    FEL_EVIDENCE_SOURCE=fixture
RUN npm install --global pnpm@10.33.0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json .node-version ./
COPY apps/web/package.json ./apps/web/package.json
COPY packages/contracts/package.json ./packages/contracts/package.json
RUN test "$(node --version)" = "v$(cat .node-version)" \
    && pnpm install --frozen-lockfile
COPY apps/web ./apps/web
COPY packages/contracts ./packages/contracts
RUN pnpm --filter @fel/web build

FROM node:24.20.0-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    FEL_DEPLOYMENT_MODE=fixture \
    FEL_EVIDENCE_SOURCE=fixture
COPY --from=build --chown=node:node /workspace /workspace
COPY LICENSE NOTICE /workspace/
WORKDIR /workspace/apps/web
USER node
ARG SOURCE_SHA=unknown
LABEL org.opencontainers.image.revision=$SOURCE_SHA
EXPOSE 3000
# A fixture image never inherits a shared bearer token from its environment.
ENTRYPOINT ["sh", "-c", "unset FEL_API_BEARER_TOKEN; exec node node_modules/next/dist/bin/next start --hostname 0.0.0.0 --port 3000"]
