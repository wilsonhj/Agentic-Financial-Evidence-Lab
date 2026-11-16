"""Offline Helm rendering checks; install the pinned lab Helm CLI first."""

import shutil
import subprocess
import unittest
from pathlib import Path

HELM = shutil.which("helm")
CHART = Path(__file__).resolve().parents[2] / "helm/fel"


@unittest.skipUnless(HELM, "Helm is optional; install with bootstrap-tools.sh to check renders")
class ChartTests(unittest.TestCase):
    def render(self, *arguments):
        import yaml

        result = subprocess.run(
            [HELM, "template", "pg-lab", str(CHART), "--kube-version", "1.37.0", *arguments],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return list(yaml.safe_load_all(result.stdout))

    def test_service_links_cannot_inject_pg_overrides_into_test_containers(self):
        # A valid pg-prefixed release creates PG_LAB_WEB_* service variables
        # unless service links are disabled, causing both credential init and
        # acceptance to refuse execution as an inherited libpq override.
        for mode in ("helm", "argocd"):
            with self.subTest(mode=mode):
                resources = self.render("--set", f"tests.hookMode={mode}")
                pods = [resource["spec"]["template"]["spec"] for resource in resources
                        if resource["kind"] in ("Deployment", "Job")]
                self.assertEqual(len(pods), 3)
                for pod in pods:
                    self.assertIs(pod["enableServiceLinks"], False)
                    self.assertIs(pod["automountServiceAccountToken"], False)

    def test_hook_controller_modes_remain_exclusive(self):
        for mode, expected, forbidden in (
            ("helm", "helm.sh/hook", "argocd.argoproj.io/hook"),
            ("argocd", "argocd.argoproj.io/hook", "helm.sh/hook"),
        ):
            with self.subTest(mode=mode):
                jobs = [resource for resource in self.render("--set", f"tests.hookMode={mode}")
                        if resource["kind"] == "Job"]
                self.assertEqual(len(jobs), 2)
                for job in jobs:
                    self.assertIn(expected, job["metadata"]["annotations"])
                    self.assertNotIn(forbidden, job["metadata"]["annotations"])


if __name__ == "__main__":
    unittest.main()
