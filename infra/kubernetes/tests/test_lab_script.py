"""Exercise lab reruns and failure reporting without a Docker engine or cluster."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "lab.sh"


class LabScriptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.state.mkdir()
        for name, value in (
            ("owner", "fel-test"),
            ("node-id", "owned-node"),
            ("kubeconfig", "test"),
        ):
            (self.state / name).write_text(value)
        binaries = self.root / "bin"
        binaries.mkdir()
        cli = binaries / "fake-cli"
        cli.write_text(f"#!{sys.executable}\n" + """
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
state = pathlib.Path(os.environ["FEL_LAB_STATE"])
with (state / "calls.jsonl").open("a") as calls:
    calls.write(json.dumps([name, *args]) + "\\n")
if name == "docker":
    print("owned-node")
elif name == "helm":
    (state / "fel-lab-web-smoke").write_text("current smoke")
    status = int(os.environ.get("TEST_HELM_STATUS", "1"))
    if status == 0:
        (state / "fel-lab-acceptance").write_text("current acceptance passed")
    print("current Helm test")
    sys.exit(status)
elif "delete" in args:
    if os.environ.get("TEST_DELETE_STATUS"):
        sys.exit(int(os.environ["TEST_DELETE_STATUS"]))
    for job in ("fel-lab-web-smoke", "fel-lab-acceptance"):
        (state / job).unlink(missing_ok=True)
elif "logs" in args:
    job = next(arg.removeprefix("job/") for arg in args if arg.startswith("job/"))
    path = state / job
    if not path.exists():
        print("Job does not exist", file=sys.stderr)
        sys.exit(1)
    print(path.read_text())
elif "get" in args:
    print("current workload metadata")
    sys.exit(int(os.environ.get("TEST_COLLECTION_STATUS", "0")))
elif name == "date":
    print("20261116T120000Z")
""")
        cli.chmod(0o755)
        for name in ("docker", "helm", "kubectl", "date"):
            (binaries / name).symlink_to(cli)
        self.environment = dict(
            os.environ,
            PATH=f"{binaries}:{os.environ['PATH']}",
            FEL_LAB_STATE=str(self.state),
            FEL_LAB_CLUSTER="fel-test",
        )

    def run_script(self, action="test", **environment):
        return subprocess.run(
            ["bash", str(SCRIPT), action],
            env=dict(self.environment, **environment),
            capture_output=True,
            text=True,
            timeout=10,
        )

    def calls(self):
        return [json.loads(line) for line in (self.state / "calls.jsonl").read_text().splitlines()]

    def test_failed_smoke_never_archives_previous_acceptance_success(self):
        (self.state / "fel-lab-acceptance").write_text("previous acceptance passed")
        result = self.run_script()
        self.assertEqual(result.returncode, 1, result.stderr)
        evidence = list((self.state / "evidence").glob("acceptance-acceptance-*.log"))
        self.assertEqual(len(evidence), 1)
        self.assertNotIn("previous acceptance passed", evidence[0].read_text())
        calls = self.calls()
        deletion = next(i for i, call in enumerate(calls) if "delete" in call)
        execution = next(i for i, call in enumerate(calls) if call[0] == "helm")
        self.assertLess(deletion, execution)
        self.assertIn("fel-lab-web-smoke", calls[deletion])
        self.assertIn("fel-lab-acceptance", calls[deletion])
        for call in calls:
            if call[0] in ("helm", "kubectl"):
                self.assertIn(str(self.state / "kubeconfig"), call)
                self.assertIn("kind-fel-test", call)

    def test_cleanup_failure_stops_before_launching_tests(self):
        result = self.run_script(TEST_DELETE_STATUS="7")
        self.assertEqual(result.returncode, 7)
        self.assertFalse(any(call[0] == "helm" for call in self.calls()))

    def test_collection_failure_preserves_failed_or_passed_helm_status(self):
        for status in ("0", "9"):
            with self.subTest(helm_status=status):
                result = self.run_script(TEST_HELM_STATUS=status, TEST_COLLECTION_STATUS="4")
                self.assertEqual(result.returncode, int(status), result.stderr)
                self.assertIn("Could not collect", result.stderr)

    def test_unknown_action_fails_and_help_succeeds(self):
        self.assertEqual(self.run_script("tset").returncode, 2)
        self.assertEqual(self.run_script("help").returncode, 0)

    def test_same_second_attempts_keep_separate_evidence(self):
        for _ in range(2):
            self.assertEqual(self.run_script().returncode, 1)
        logs = list((self.state / "evidence").glob("helm-test-20261116T120000Z-*.log"))
        self.assertEqual(len(logs), 2)


if __name__ == "__main__":
    unittest.main()
