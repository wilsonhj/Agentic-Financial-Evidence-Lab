"""DIAGNOSTIC: aggregate sampler output inside measured review windows."""

import collections
import json
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1] / "runs"
for label in sys.argv[1:]:
    rows = [json.loads(line) for line in (R / label / "samples.jsonl").read_text().splitlines()]
    rev = [r for r in rows if r["operation"] == "review" and r["phase"] == "measured"]
    wins = []
    for w in sorted({r["wave"] for r in rev}):
        ws = [r for r in rev if r["wave"] == w]
        wins.append((min(r["start_ns"] for r in ws), max(r["end_ns"] for r in ws)))
    acts = [json.loads(line) for line in (R / label / "activity.jsonl").read_text().splitlines()]
    inw = [a for a in acts if any(s <= a["at_ns"] <= e for s, e in wins)]
    ev = collections.Counter()
    mx = collections.Counter()
    for a in inw:
        per = collections.Counter()
        for st, t, e, n in a["activity"]:
            k = f"{t}:{e}" if st == "active" else st
            ev[k] += n
            per[k] += n
        for k, v in per.items():
            mx[k] = max(mx[k], v)
    n = len(inw) or 1
    api = [a["api_cpu_cores"] for a in inw if a["api_cpu_cores"] is not None]
    print(
        json.dumps(
            dict(
                label=label,
                samples=len(inw),
                host_busy_mean=round(sum(a["host_busy"] for a in inw) / n, 2),
                api_cpu_cores_mean=round(sum(api) / max(1, len(api)), 2),
                mean_backends_by_state=dict(
                    sorted(((k, round(v / n, 2)) for k, v in ev.items()), key=lambda x: -x[1])[:8]
                ),
                max_simultaneous={k: mx[k] for k, _ in ev.most_common(8)},
            )
        )
    )
