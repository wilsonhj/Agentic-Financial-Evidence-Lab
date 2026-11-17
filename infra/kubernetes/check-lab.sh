#!/usr/bin/env bash
# Offline CI/local gate. Never pass by skipping unavailable Helm or YAML checks.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$root"
python=${FEL_LAB_PYTHON:-python3}
for tool in helm git tar "$python"; do
  command -v "$tool" >/dev/null || { echo "Missing required tool: $tool" >&2; exit 2; }
done
"$python" -c 'import yaml' || {
  echo 'Install the PyYAML version from requirements-dev.lock in the selected Python environment.' >&2
  exit 2
}
for script in infra/kubernetes/*.sh; do bash -n "$script"; done
helm lint infra/helm/fel --strict
PYTHONDONTWRITEBYTECODE=1 "$python" - <<'PY'
import sys
import unittest

suite = unittest.defaultTestLoader.discover("infra/kubernetes/tests")
result = unittest.TextTestRunner(verbosity=2).run(suite)
if result.skipped or result.testsRun == 0:
    print("Lab gate requires collected tests and zero skips.", file=sys.stderr)
    raise SystemExit(1)
raise SystemExit(0 if result.wasSuccessful() else 1)
PY
