# API image for the Vercel container runtime (ADR-0035).
#
# Build from the repository root:
#   docker build -f infra/docker/api.Dockerfile -t fel-api .
#
# The base image is pinned by digest. Python stays on 3.11 to match
# .python-version; every third-party package comes from the hash-locked
# requirements.lock, and the first-party wheels are built from this checkout by
# scripts/runtime/install.sh, the same installer the CI job verifies.
FROM python:3.11-slim-bookworm@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/fel

COPY requirements.lock ./
COPY scripts/runtime/ scripts/runtime/
COPY packages/providers/ packages/providers/
COPY packages/ontology/ packages/ontology/
COPY packages/retrieval/ packages/retrieval/
COPY workers/ workers/
COPY apps/api/ apps/api/

# Install, verify, then drop the sources: the app runs from the installed
# wheels, so nothing under /srv/fel is needed at runtime.
RUN bash scripts/runtime/install.sh python \
    && cd / && rm -rf /srv/fel \
    && useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin fel

USER 10001
WORKDIR /

# A non-root process cannot bind port 80, the container runtime's default, so
# the image listens on PORT. Set PORT=8080 in the Vercel project's environment
# variables so the platform routes to the same port. FORWARDED_ALLOW_IPS
# defaults to '*' for Vercel's dynamic edge proxy; non-Vercel deployments
# behind a fixed proxy should restrict it to their proxy IP/CIDR.
ENV PORT=8080 \
    FORWARDED_ALLOW_IPS="*"
EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT}\" --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS}\" --no-server-header"]
