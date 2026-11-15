# Build from the repository root. No architecture-specific browser image is used:
# the repository's Playwright CLI installs its matching native Chromium binary.
FROM node:24.20.0-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e
ENV DEBIAN_FRONTEND=noninteractive \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_OPTIONS=--max-old-space-size=3072 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    PATH=/opt/venv/bin:$PATH
WORKDIR /workspace
RUN apt-get update \
    && apt-get install --yes --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && npm install --global pnpm@10.33.0
COPY requirements-dev.lock .python-version ./
RUN python -c 'import sys; assert sys.version_info[:2] == (3, 11)' \
    # Debian's bundled pip predates the lockfile's package metadata. Bootstrap
    # the pip version and hashes from that same lock before resolving extras.
    && python -c 'from pathlib import Path; text = Path("requirements-dev.lock").read_text(); Path("/tmp/pip.lock").write_text("pip==" + text.split("\npip==", 1)[1].split("\n    #", 1)[0] + "\n")' \
    && python -m pip install --no-cache-dir --require-hashes --no-deps -r /tmp/pip.lock \
    && pip install --no-cache-dir --require-hashes -r requirements-dev.lock
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json .node-version ./
COPY apps/web/package.json ./apps/web/package.json
COPY packages/contracts/package.json ./packages/contracts/package.json
RUN test "$(node --version)" = "v$(cat .node-version)" \
    && pnpm install --frozen-lockfile \
    && pnpm --filter @fel/web exec playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*
COPY --chown=node:node apps/web ./apps/web
COPY --chown=node:node apps/api ./apps/api
COPY --chown=node:node packages/contracts ./packages/contracts
COPY --chown=node:node packages/providers ./packages/providers
COPY --chown=node:node packages/ontology ./packages/ontology
COPY --chown=node:node packages/retrieval ./packages/retrieval
COPY --chown=node:node packages/retrieval-evals ./packages/retrieval-evals
COPY --chown=node:node workers ./workers
COPY --chown=node:node evals ./evals
COPY --chown=node:node scripts/db/migrate.py ./scripts/db/migrate.py
COPY --chown=node:node db/migrations ./db/migrations
COPY --chown=node:node infra/kubernetes/run-acceptance.sh ./infra/kubernetes/run-acceptance.sh
# Next creates .next and may update its generated next-env.d.ts during the test.
RUN mkdir -p /work \
    && chown -R node:node /workspace/apps/web /work \
    && chmod -R a+rX /opt/playwright
USER node
ARG SOURCE_SHA=unknown
LABEL org.opencontainers.image.revision=$SOURCE_SHA
ENTRYPOINT ["bash", "/workspace/infra/kubernetes/run-acceptance.sh"]
