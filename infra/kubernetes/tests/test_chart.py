"""Offline Helm rendering checks; install the pinned lab Helm CLI first."""

import shutil
import subprocess
import tempfile
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
            capture_output=True,
            text=True,
            timeout=30,
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
                pods = [
                    resource["spec"]["template"]["spec"]
                    for resource in resources
                    if resource["kind"] in ("Deployment", "Job")
                ]
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
                jobs = [
                    resource
                    for resource in self.render("--set", f"tests.hookMode={mode}")
                    if resource["kind"] == "Job"
                ]
                self.assertEqual(len(jobs), 2)
                for job in jobs:
                    self.assertIn(expected, job["metadata"]["annotations"])
                    self.assertNotIn(forbidden, job["metadata"]["annotations"])

    def test_fixture_only_omits_database_job_and_its_network_policy(self):
        resources = self.render("--set", "acceptance.enabled=false")
        self.assertEqual(
            sorted(resource["kind"] for resource in resources), ["Deployment", "Job", "Service"]
        )
        job = next(resource for resource in resources if resource["kind"] == "Job")
        self.assertEqual(job["metadata"]["name"], "pg-lab-web-smoke")

    def test_digest_replaces_tag_for_every_web_container(self):
        digest = "sha256:" + "a" * 64
        resources = self.render("--set-string", f"web.image.digest={digest}")
        for resource in resources:
            if resource["kind"] in ("Deployment", "Job"):
                for container in resource["spec"]["template"]["spec"]["containers"]:
                    if container["name"] in ("web", "web-smoke"):
                        self.assertEqual(container["image"], f"fel-web-fixture@{digest}")

    def test_unsupported_cluster_and_values_are_rejected(self):
        for arguments, diagnostic in (
            (["--kube-version", "1.32.0"], "kubeVersion"),
            (["--set", "web.env.FEL_DEPLOYMENT_MODE=public"], "'env' not allowed"),
            (["--set-string", "web.image.repository=invalid image"], "repository"),
            (["--set", "tests.hookMode=unknown"], "hookMode"),
        ):
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    [HELM, "template", "fel-test", str(CHART), *arguments],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(diagnostic, result.stderr)

    def test_environment_wrapper_passes_child_values_offline(self):
        import yaml

        with tempfile.TemporaryDirectory() as temporary:
            wrapper = Path(temporary)
            shutil.copytree(CHART, wrapper / "charts/fel")
            (wrapper / "Chart.yaml").write_text(
                "apiVersion: v2\nname: fel-wrapper\nversion: 0.1.0\n"
                "dependencies:\n  - name: fel\n    version: 0.1.0\n"
            )
            (wrapper / "values.yaml").write_text("fel:\n  tests:\n    hookMode: argocd\n")
            result = subprocess.run(
                [HELM, "template", "fel-test", str(wrapper), "--kube-version", "1.37.0"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            jobs = [doc for doc in yaml.safe_load_all(result.stdout) if doc["kind"] == "Job"]
            self.assertEqual(len(jobs), 2)
            for job in jobs:
                self.assertEqual(
                    job["metadata"]["annotations"]["argocd.argoproj.io/hook"], "PostSync"
                )
                self.assertNotIn("helm.sh/hook", job["metadata"]["annotations"])


if __name__ == "__main__":
    unittest.main()
