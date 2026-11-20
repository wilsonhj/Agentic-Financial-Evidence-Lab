"""DIAGNOSTIC sampler: every 100 ms record pg_stat_activity wait events (own DB only),
host CPU busy fraction from /proc/stat, and the API python process CPU (by cmdline match)."""

import json
import os
import sys
import time

import psycopg

out = open(sys.argv[1], "w")
dsn = os.environ["FEL_DATABASE_URL"]


def cpu():
    f = open("/proc/stat").readline().split()[1:]
    v = list(map(int, f))
    return sum(v), v[3] + v[4]


def api_ticks():
    t = 0
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            if b"instrumented_uvicorn" in open(f"/proc/{pid}/cmdline", "rb").read():
                s = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()
                t += int(s[11]) + int(s[12])
        except OSError:
            pass
    return t


with psycopg.connect(dsn, autocommit=True) as c:
    pt, pi = cpu()
    pa = api_ticks()
    pw = time.monotonic()
    while True:
        time.sleep(0.1)
        rows = c.execute(
            "SELECT state, coalesce(wait_event_type,'CPU'), coalesce(wait_event,'-'), count(*) "
            "FROM pg_stat_activity WHERE datname=current_database() "
            "AND pid<>pg_backend_pid() AND state<>'idle' GROUP BY 1,2,3"
        ).fetchall()
        t, i = cpu()
        a = api_ticks()
        now = time.monotonic()
        out.write(
            json.dumps(
                dict(
                    at_ns=time.perf_counter_ns(),
                    host_busy=round(1 - (i - pi) / max(1, t - pt), 3),
                    api_cpu_cores=round((a - pa) / 100 / (now - pw), 2) if a >= pa else None,
                    activity=[list(r) for r in rows],
                )
            )
            + "\n"
        )
        out.flush()
        pt, pi, pa, pw = t, i, a, now
