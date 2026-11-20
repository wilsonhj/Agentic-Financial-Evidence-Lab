"""DIAGNOSTIC concurrency sweep driver (not acceptance).

Reuses benchmarks.extraction_load.wave/measure and the fixture unchanged; only the
per-wave client count differs from the harness (which hard-codes 25). Mirrors the
harness's main(): same env guards, synthetic target, owned single Uvicorn process
bound via --fd, 1-user preflight, 25-user warmup, then N measured waves at --clients.
The server is started through instrumented_uvicorn.py to log pool wait / SQL time.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psycopg

from app.config import settings
from benchmarks.extraction_load import wave
from benchmarks.synthetic_target import prepare_synthetic_target

HERE = Path(__file__).resolve().parent

p = argparse.ArgumentParser()
p.add_argument("--output", type=Path, required=True)
p.add_argument("--clients", type=int, required=True)
p.add_argument("--waves", type=int, default=4)
p.add_argument("--port", type=int, default=8231)
p.add_argument("--warmup", type=int, default=25)
p.add_argument("--workers", type=int, default=1)
a = p.parse_args()
assert a.waves >= 4
database = os.environ["FEL_DATABASE_URL"]
assert psycopg.conninfo.conninfo_to_dict(database)["dbname"].startswith("fel_load")
assert os.environ["FEL_AUTH_MODE"] == "mock" and os.environ["FEL_WORKER_DB_ROLE"] == "fel_worker"
a.output.mkdir(parents=True, exist_ok=False)
storage = Path(os.environ["FEL_STORAGE_DIR"])
prepare_synthetic_target(
    database, storage, os.environ.get("FEL_SYNTHETIC_HTTP_TARGET", ""), "fel_load"
)
with psycopg.connect(database) as conn:
    assert (
        conn.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
        == 0
    )
    pg = {
        k: conn.execute("SELECT current_setting(%s)", (k,)).fetchone()[0]
        for k in (
            "server_version",
            "fsync",
            "synchronous_commit",
            "shared_buffers",
            "max_connections",
            "wal_sync_method",
        )
    }
cfg = settings()
meta = dict(
    diagnostic=True,
    clients=a.clients,
    waves=a.waves,
    warmup_clients=a.warmup,
    host_load_start=os.getloadavg(),
    cpu_count=os.cpu_count(),
    api_processes=a.workers,
    db_pool_min=cfg.db_pool_min,
    db_pool_max=cfg.db_pool_max,
    postgres=pg,
    started=time.time(),
)
rows: list = []
failure = None
pool_log = a.output / "pool.jsonl"
env = dict(os.environ, SWEEP_POOL_LOG=str(pool_log))
base = f"http://127.0.0.1:{a.port}"
with socket.socket() as listener, (a.output / "server.log").open("w") as log:
    listener.bind(("127.0.0.1", a.port))
    listener.listen(128)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--workers",
            str(a.workers),
            "--fd",
            str(listener.fileno()),
            "--no-access-log",
        ],
        pass_fds=(listener.fileno(),),
        stdout=log,
        stderr=log,
        env=env,
    )
    try:
        with httpx.Client(timeout=1) as c:
            for _ in range(100):
                if proc.poll() is not None:
                    raise RuntimeError("API exited")
                try:
                    if c.get(base + "/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("API not healthy")
        out = a.output / "samples.jsonl"
        wave(database, storage, base, 1, "preflight", 0, out, rows)
        wave(database, storage, base, a.warmup, "warmup", 0, out, rows)
        for i in range(a.waves):
            wave(database, storage, base, a.clients, "measured", i, out, rows)
    except Exception as exc:
        failure = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
meta.update(host_load_end=os.getloadavg(), finished=time.time(), failure=failure)
(a.output / "metadata.json").write_text(json.dumps(meta, indent=2))
print(json.dumps(meta))
sys.exit(1 if failure else 0)
