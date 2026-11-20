"""DIAGNOSTIC ONLY: start uvicorn after wrapping psycopg_pool / psycopg timing.

Records, per pool checkout: wait for getconn, hold time, summed cursor execute
time, and transaction-exit (commit) time. Uses time.perf_counter_ns (CLOCK_MONOTONIC,
comparable with the client process). Writes JSONL to $SWEEP_POOL_LOG at exit.
Does not change any application setting or behavior beyond timing overhead.
"""

import atexit
import json
import os
import sys
import threading
import time

import psycopg
import psycopg_pool

LOG = os.environ["SWEEP_POOL_LOG"]
_records: list = []
_lock = threading.Lock()
_tl = threading.local()

_orig_getconn = psycopg_pool.ConnectionPool.getconn
_orig_putconn = psycopg_pool.ConnectionPool.putconn
_orig_exec = psycopg.Cursor.execute
_orig_execmany = psycopg.Cursor.executemany
_orig_tx_exit = psycopg.Transaction.__exit__


def getconn(self, timeout=None):
    t0 = time.perf_counter_ns()
    conn = _orig_getconn(self, timeout)
    t1 = time.perf_counter_ns()
    conn._sweep = {
        "req": t0,
        "got": t1,
        "sql": 0,
        "nsql": 0,
        "commit": 0,
        "size": self.get_stats().get("pool_size"),
    }
    return conn


def putconn(self, conn):
    s = getattr(conn, "_sweep", None)
    if s is not None:
        s["put"] = time.perf_counter_ns()
        with _lock:
            _records.append(s)
        conn._sweep = None
    return _orig_putconn(self, conn)


def _acc(conn, dt):
    s = getattr(conn, "_sweep", None)
    if s is not None:
        s["sql"] += dt
        s["nsql"] += 1


def execute(self, *a, **k):
    t0 = time.perf_counter_ns()
    try:
        return _orig_exec(self, *a, **k)
    finally:
        _acc(self.connection, time.perf_counter_ns() - t0)


def executemany(self, *a, **k):
    t0 = time.perf_counter_ns()
    try:
        return _orig_execmany(self, *a, **k)
    finally:
        _acc(self.connection, time.perf_counter_ns() - t0)


def tx_exit(self, *a):
    t0 = time.perf_counter_ns()
    try:
        return _orig_tx_exit(self, *a)
    finally:
        s = getattr(self.connection, "_sweep", None)
        if s is not None:
            s["commit"] += time.perf_counter_ns() - t0


psycopg_pool.ConnectionPool.getconn = getconn
psycopg_pool.ConnectionPool.putconn = putconn
psycopg.Cursor.execute = execute
psycopg.Cursor.executemany = executemany
psycopg.Transaction.__exit__ = tx_exit


def _flush():
    with _lock, open(LOG, "w") as f:
        for r in _records:
            f.write(json.dumps(r) + "\n")


atexit.register(_flush)


def _on_term(signum, frame):
    # uvicorn restores this handler after graceful shutdown and re-raises SIGTERM.
    _flush()
    os._exit(0)


if __name__ == "__main__":
    import signal

    signal.signal(signal.SIGTERM, _on_term)
    import uvicorn.main

    sys.argv = ["uvicorn", *sys.argv[1:]]
    try:
        uvicorn.main.main()
    finally:
        _flush()
