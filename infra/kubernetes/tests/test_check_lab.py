"""The CI entrypoint must fail for missing tools, failures and skipped checks."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-lab.sh"


class LabGateTests(unittest.TestCase):
    def run_gate(self, fixture, helm=True):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "infra/kubernetes"
            tests = scripts / "tests"
            tests.mkdir(parents=True)
            shutil.copy2(SCRIPT, scripts / SCRIPT.name)
            if fixture:
                (tests / "test_fixture.py").write_text(fixture)
            binaries = root / "bin"
            binaries.mkdir()
            for name in ("bash", "dirname", "git", "tar"):
                (binaries / name).symlink_to(shutil.which(name))
            if helm:
                (binaries / "helm").write_text("#!/bin/sh\nexit 0\n")
                (binaries / "helm").chmod(0o755)
            return subprocess.run(
                ["/bin/bash", str(scripts / SCRIPT.name)],
                env=dict(os.environ, PATH=str(binaries), FEL_LAB_PYTHON=sys.executable),
                capture_output=True,
                text=True,
                timeout=10,
            )

    def test_missing_helm_is_an_error_instead_of_skipped_success(self):
        result = self.run_gate("", helm=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Missing required tool: helm", result.stderr)

    def test_test_failure_propagates_to_shell(self):
        result = self.run_gate(
            "import unittest\nclass Check(unittest.TestCase):\n"
            "    def test_failure(self): self.fail('intentional gate failure')\n"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("intentional gate failure", result.stderr)

    def test_skipped_tests_are_rejected(self):
        result = self.run_gate(
            "import unittest\nclass Check(unittest.TestCase):\n"
            "    @unittest.skip('intentional missing prerequisite')\n"
            "    def test_skip(self): pass\n"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("zero skips", result.stderr)

    def test_empty_collection_is_rejected(self):
        result = self.run_gate("")
        self.assertEqual(result.returncode, 1)
        self.assertIn("collected tests", result.stderr)


if __name__ == "__main__":
    unittest.main()
