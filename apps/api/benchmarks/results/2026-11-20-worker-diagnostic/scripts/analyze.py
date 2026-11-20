"""DIAGNOSTIC analysis of sweep results. Nearest-rank p95 like the harness."""

import json
import math
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1] / "runs"


def nr(vals, q):
    v = sorted(vals)
    return v[max(0, math.ceil(q * len(v)) - 1)] if v else float("nan")


out = []
for label in sys.argv[1:]:
    d = R / label
    if not (d / "samples.jsonl").exists():
        continue
    rows = [json.loads(line) for line in (d / "samples.jsonl").read_text().splitlines()]
    meta = json.loads((d / "metadata.json").read_text()) if (d / "metadata.json").exists() else {}
    rev = [r for r in rows if r["operation"] == "review" and r["phase"] == "measured"]
    errs = sum(1 for r in rows if r["error"])
    lat = [(r["end_ns"] - r["start_ns"]) / 1e6 for r in rev]
    waves = sorted({r["wave"] for r in rev})
    per_wave = []
    for w in waves:
        wl = sorted((r["end_ns"] - r["start_ns"]) / 1e6 for r in rev if r["wave"] == w)
        per_wave.append([round(x) for x in wl])
    # pool checkouts during measured review windows
    pw, sql, hold, commit, nsql = [], [], [], [], []
    if (d / "pool.jsonl").exists() and rev:
        pool = [json.loads(line) for line in (d / "pool.jsonl").read_text().splitlines()]
        wins = []
        for w in waves:
            ws = [r for r in rev if r["wave"] == w]
            wins.append((min(r["start_ns"] for r in ws), max(r["end_ns"] for r in ws)))
        for p in pool:
            if "put" in p and any(s <= p["req"] and p["put"] <= e for s, e in wins):
                pw.append((p["got"] - p["req"]) / 1e6)
                sql.append(p["sql"] / 1e6)
                hold.append((p["put"] - p["got"]) / 1e6)
                commit.append(p["commit"] / 1e6)
                nsql.append(p["nsql"])
    big = [i for i, n in enumerate(nsql) if n >= 20]  # the review transaction itself
    rec = dict(
        label=label,
        clients=meta.get("clients"),
        pool_max=meta.get("db_pool_max"),
        failure=meta.get("failure"),
        errors=errs,
        waves=len(waves),
        requests=len(lat),
        p50=round(nr(lat, 0.5), 1),
        p95=round(nr(lat, 0.95), 1),
        max=round(max(lat), 1) if lat else None,
        wave_max=[max(w) for w in per_wave],
        checkouts=len(pw),
        review_tx=len(big),
        pool_wait_p50=round(nr([pw[i] for i in big], 0.5), 1) if big else None,
        pool_wait_p95=round(nr([pw[i] for i in big], 0.95), 1) if big else None,
        sql_p50=round(nr([sql[i] for i in big], 0.5), 1) if big else None,
        sql_p95=round(nr([sql[i] for i in big], 0.95), 1) if big else None,
        commit_p50=round(nr([commit[i] for i in big], 0.5), 1) if big else None,
        commit_p95=round(nr([commit[i] for i in big], 0.95), 1) if big else None,
        hold_p95=round(nr([hold[i] for i in big], 0.95), 1) if big else None,
        any_wait_p95=round(nr(pw, 0.95), 1) if pw else None,
        load=(meta.get("host_load_start"), meta.get("host_load_end")),
        per_wave_sorted_ms=per_wave,
    )
    out.append(rec)
    print(json.dumps({k: v for k, v in rec.items() if k != "per_wave_sorted_ms"}))
(R / "summary.json").write_text(json.dumps(out, indent=1))
