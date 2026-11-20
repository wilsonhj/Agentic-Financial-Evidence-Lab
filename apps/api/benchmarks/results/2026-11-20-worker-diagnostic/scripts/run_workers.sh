#!/usr/bin/env bash
# DIAGNOSTIC: client latency at N API worker processes, unchanged harness waves.
# Run from the repository root. The caller supplies FEL_DATABASE_URL for a
# disposable database whose name starts with fel_load, and SWEEP_OUT, an empty
# directory for the results. No value is stored in this file.
set -euo pipefail
: "${FEL_DATABASE_URL:?set FEL_DATABASE_URL}"
: "${SWEEP_OUT:?set SWEEP_OUT}"
HERE="$(cd "$(dirname "$0")" && pwd)"
export FEL_AUTH_MODE=mock FEL_ALLOW_MOCK_LLM=1 FEL_WORKER_DB_ROLE=fel_worker
export FEL_DEPLOYMENT_MODE=synthetic-http FEL_SYNTHETIC_HTTP_TARGET=sweep-diagnostic
export FEL_STORAGE_DIR="${FEL_STORAGE_DIR:-$SWEEP_OUT/storage}"
export PYTHONPATH="apps/api:evals:workers/src:packages/providers:packages/ontology:packages/retrieval:packages/retrieval-evals:$HERE"
for spec in w1_c25:1:25 w2_c25:2:25 w4_c25:4:25 w4_c10:4:10 w2_c25b:2:25 w1_c25b:1:25; do
  IFS=: read -r label workers clients <<< "$spec"
  echo "== $label workers=$workers clients=$clients load=$(cut -d' ' -f1-3 /proc/loadavg)"
  python "$HERE/sweep_workers.py" --output "$SWEEP_OUT/$label" \
    --clients "$clients" --workers "$workers" --waves 4
done
