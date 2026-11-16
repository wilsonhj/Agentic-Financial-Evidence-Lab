#!/usr/bin/env bash
# Container-only runner for the unchanged extraction HTTP acceptance test.
# The Helm test creates its own PostgreSQL sidecar and emptyDir volumes.
set -euo pipefail
exec python - "$@" <<'PY'
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time
from urllib.parse import urlsplit

CREDENTIAL_FILE = Path("/run/fel-acceptance/password")
ROOT = Path("/workspace")
WORK = Path("/work")
DATABASE = "fel_extraction_acceptance"


def refuse():
    # Do not include inherited URLs, credentials or file contents in errors.
    raise SystemExit("Refusing acceptance: dedicated local lab configuration required")


def require_local_environment():
    if (
        os.environ.get("FEL_ACCEPTANCE_LOCAL") != "1"
        or "FEL_DATABASE_URL" in os.environ
        or any(key.startswith("PG") for key in os.environ)
    ):
        refuse()


def initialize_credential():
    require_local_environment()
    try:
        # The first init container owns this fresh memory-backed volume. Never
        # reuse or follow an existing path, including after a partial init.
        descriptor = os.open(CREDENTIAL_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        with os.fdopen(descriptor, "w") as output:
            os.fchmod(output.fileno(), 0o640)
            output.write(secrets.token_hex(32))
    except OSError:
        refuse()


def read_credential():
    try:
        descriptor = os.open(CREDENTIAL_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "r") as source:
            metadata = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_gid != os.getegid()
                or stat.S_IMODE(metadata.st_mode) != 0o640
                or metadata.st_nlink != 1
            ):
                refuse()
            password = source.read(65)
    except (OSError, UnicodeError):
        refuse()
    if re.fullmatch(r"[0-9a-f]{64}", password) is None:
        refuse()
    return password


def acceptance_environment():
    require_local_environment()
    password = read_credential()
    if not (ROOT / "apps/web/playwright.cross-stack.config.ts").is_file():
        refuse()
    if not WORK.is_dir() or any(WORK.iterdir()):
        refuse()

    # No inherited application credential, proxy configuration, alternate DSN
    # or libpq override reaches the synthetic test subprocesses. The only DB
    # target is composed here, after validating the per-Job credential file.
    environment = {
        key: os.environ[key]
        for key in ("PATH", "HOME", "LANG", "PLAYWRIGHT_BROWSERS_PATH")
        if key in os.environ
    }
    dsn = f"postgresql://fel:{password}@127.0.0.1:5432/{DATABASE}"
    parsed = urlsplit(dsn)
    if (
        parsed.scheme != "postgresql"
        or parsed.hostname != "127.0.0.1"
        or parsed.port != 5432
        or parsed.username != "fel"
        or parsed.password != password
        or parsed.path != f"/{DATABASE}"
        or parsed.query
        or parsed.fragment
    ):
        refuse()
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
        "FEL_STORAGE_DIR": str(WORK / "storage"),
        "CROSS_STACK_MANIFEST": str(WORK / "manifest.json"),
        "FEL_ACCEPTANCE_PYTHON": sys.executable,
        "PYTHONPATH": ":".join(str(ROOT / path) for path in (
            ".", "apps/api", "workers/src", "packages/providers", "packages/ontology",
            "packages/retrieval", "packages/retrieval-evals",
        )),
    })
    return environment, password


def redact_output(line, password):
    # Hide every URL as well as standalone generated material on failure paths.
    line = re.sub(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s]+", "[URL redacted]", line)
    return line.replace(password, "[credential redacted]")


def main(arguments):
    if arguments == ["--initialize-db-credential"]:
        initialize_credential()
        return 0
    if arguments:
        refuse()
    environment, password = acceptance_environment()
    dsn = environment["FEL_DATABASE_URL"]
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
            if identity != (DATABASE, "fel", "127.0.0.1"):
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
                                    "--output", str(WORK / "test-results")]),
        )
        for stage, command in steps:
            print(f"Acceptance stage: {stage}", flush=True)
            with subprocess.Popen(command, cwd=ROOT, env=environment, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True) as process:
                for line in process.stdout:
                    print(redact_output(line, password), end="", flush=True)
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
        (WORK / "result.json").write_text(summary + "\n")
        print(f"Acceptance result: {summary}", flush=True)
        print(f"Acceptance artifacts: {WORK} (ephemeral; JSON summary and stage output "
              "also in container logs)", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
PY
