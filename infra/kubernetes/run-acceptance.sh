#!/usr/bin/env bash
# Container-only runner for the unchanged extraction HTTP acceptance test.
# The Helm test creates its own PostgreSQL sidecar and emptyDir volumes.
set -euo pipefail
exec python - <<'PY'
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit


def refuse():
    # Never echo configuration values, connection strings or credentials.
    raise SystemExit("Refusing acceptance: dedicated local lab configuration required")


dsn = os.environ.get("FEL_DATABASE_URL", "")
try:
    parsed = urlsplit(dsn)
    database = parsed.path.removeprefix("/")
    if (
        os.environ.get("FEL_ACCEPTANCE_LOCAL") != "1"
        or parsed.scheme != "postgresql"
        or parsed.hostname != "127.0.0.1"
        or parsed.port != 5432
        or parsed.username != "fel"
        or parsed.password != "fel-local-only"
        or parsed.query
        or parsed.fragment
        or re.fullmatch(r"fel_extraction_acceptance(?:_[a-z0-9_]+)?", database) is None
        or dsn != f"postgresql://fel:fel-local-only@127.0.0.1:5432/{database}"
        or any(key.startswith("PG") for key in os.environ)
    ):
        refuse()
except ValueError:
    refuse()

root = Path("/workspace")
work = Path("/work")
if not (root / "apps/web/playwright.cross-stack.config.ts").is_file():
    refuse()
if not work.is_dir() or any(work.iterdir()):
    refuse()

# Retain only runtime essentials. Real provider keys, bearer tokens, alternate
# DSNs and libpq overrides cannot leak into the synthetic test subprocesses.
environment = {
    key: os.environ[key]
    for key in ("PATH", "HOME", "LANG", "PLAYWRIGHT_BROWSERS_PATH")
    if key in os.environ
}
environment.update({
    "CI": "1",
    "NEXT_TELEMETRY_DISABLED": "1",
    "NODE_OPTIONS": "--max-old-space-size=3072",
    "FEL_DATABASE_URL": dsn,
    "FEL_DEPLOYMENT_MODE": "synthetic-http",
    "FEL_SYNTHETIC_HTTP_TARGET": "extraction-ci",
    "FEL_AUTH_MODE": "mock",
    "FEL_ALLOW_MOCK_LLM": "1",
    "FEL_WORKER_DB_ROLE": "fel_worker",
    "FEL_STORAGE_DIR": str(work / "storage"),
    "CROSS_STACK_MANIFEST": str(work / "manifest.json"),
    "FEL_ACCEPTANCE_PYTHON": sys.executable,
    "PYTHONPATH": ":".join(str(root / path) for path in (
        ".", "apps/api", "workers/src", "packages/providers", "packages/ontology",
        "packages/retrieval", "packages/retrieval-evals",
    )),
})
os.environ.clear()
os.environ.update(environment)

import psycopg

stage = "database-readiness"
result = {"status": "failed", "stage": stage}
exit_code = 1
try:
    # No database creation, deletion or reset. Require an empty, already-created
    # database in the dedicated sidecar before applying the committed ledger.
    for attempt in range(60):
        try:
            connection = psycopg.connect(dsn, connect_timeout=2)
            break
        except psycopg.OperationalError:
            if attempt == 59:
                raise RuntimeError("local database readiness timed out") from None
            time.sleep(1)
    with connection:
        identity = connection.execute(
            "SELECT current_database(), current_user, host(inet_server_addr())"
        ).fetchone()
        if identity != (database, "fel", "127.0.0.1"):
            raise RuntimeError("local database identity mismatch")
        if connection.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public')"
        ).fetchone()[0]:
            raise RuntimeError("local acceptance database must start empty")

    steps = (
        ("migrate", [sys.executable, "scripts/db/migrate.py"]),
        ("migration-check", [sys.executable, "scripts/db/migrate.py", "--check"]),
        ("seed", [sys.executable, "-m", "evals.harness.extraction_cross_stack", "seed",
                  "--manifest", environment["CROSS_STACK_MANIFEST"]]),
        ("browser-api-worker", ["pnpm", "--filter", "@fel/web", "exec", "playwright", "test",
                                "--config", "playwright.cross-stack.config.ts",
                                "--output", str(work / "test-results")]),
    )
    for stage, command in steps:
        print(f"Acceptance stage: {stage}", flush=True)
        with subprocess.Popen(command, cwd=root, env=environment, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True) as process:
            for line in process.stdout:
                # Defense in depth for failures in dependencies. Only mock
                # configuration reaches these processes, and URLs stay private.
                line = re.sub(r"postgres(?:ql)?://[^\s]+", "[database URL redacted]", line)
                print(line.replace("fel-local-only", "[redacted]"), end="", flush=True)
            code = process.wait()
        if code:
            raise RuntimeError(f"stage exited with code {code}")
    result = {"status": "passed", "stage": stage}
    exit_code = 0
except Exception:
    # Detailed, redacted child output appears above; connection exceptions can
    # contain libpq connection material, so they are deliberately not printed.
    print(f"Acceptance failed at stage: {stage}", file=sys.stderr, flush=True)
    result = {"status": "failed", "stage": stage}
finally:
    summary = json.dumps(result, sort_keys=True)
    (work / "result.json").write_text(summary + "\n")
    print(f"Acceptance result: {summary}", flush=True)
    print(f"Acceptance artifacts: {work} (ephemeral; JSON summary and stage output "
          "also in container logs)", flush=True)
raise SystemExit(exit_code)
PY
