# API image for the Vercel container runtime (ADR-0035).
#
# Build from the repository root:
#   docker build -f infra/docker/api.Dockerfile -t fel-api .
#
# The base image is pinned by digest. Python stays on 3.11 to match
# .python-version; every third-party package comes from the hash-locked
# requirements.lock, and the first-party wheels are built from this checkout by
# scripts/runtime/install.sh, the same installer the CI job verifies.
FROM python:3.11-slim-bookworm@sha256:ef56ae98435cc40d8a27020b0b32a9941515acd5840f0fba34858bb34dd362d1

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
# wheels, so nothing under /srv/fel is needed at runtime. The base image's
# setuptools 79 vendors jaraco.context 5.3.0 and wheel 0.45.1, and its pip is
# 24.0. Replace those two distributions from the hash-locked file after the
# app install; --no-deps keeps the fixed copies that are already inside the
# wheels and does not fetch an unpinned dependency.
RUN bash scripts/runtime/install.sh python \
    && python -m pip install --require-hashes --no-deps -r scripts/runtime/image-tools.lock \
    && cd / && rm -rf /srv/fel \
    && useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin fel

USER 10001
WORKDIR /

# A non-root process cannot bind port 80, the container runtime's default, so
# the image listens on PORT. Set PORT=8080 in the Vercel project's environment
# variables so the platform routes to the same port.
# --proxy-headers stays so a deployment can set FORWARDED_ALLOW_IPS. Uvicorn
# otherwise trusts only 127.0.0.1, which is the safe default.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT}\" --proxy-headers --no-server-header"]
