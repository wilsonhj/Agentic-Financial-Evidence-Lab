"""Pins and runtime hardening that the image scan showed were missing."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
NODE_IMAGE = (
    "node:24.22.3-bookworm-slim"
    "@sha256:873f586f3794f52281bd039bf02c048a0be08fde619338f9941bad1eb6b34530"
)
PYTHON_IMAGE = (
    "python:3.11-slim-bookworm"
    "@sha256:ef56ae98435cc40d8a27020b0b32a9941515acd5840f0fba34858bb34dd362d1"
)
NPM_TREE = "/usr/local/lib/node_modules/npm"


class RuntimeHardeningTests(unittest.TestCase):
    def test_node_pin_matches_the_patched_manifest_list(self):
        self.assertEqual((ROOT / ".node-version").read_text().strip(), "24.22.3")
        self.assertEqual((ROOT / ".nvmrc").read_text().strip(), "24.22.3")
        for relative in (
            "infra/kubernetes/images/web-fixture.Dockerfile",
            "infra/kubernetes/images/acceptance.Dockerfile",
        ):
            text = (ROOT / relative).read_text()
            self.assertIn(NODE_IMAGE, text)
            self.assertNotIn("24.20.0-bookworm-slim", text)

    def test_shipped_node_images_do_not_keep_the_npm_cli_tree(self):
        web = (ROOT / "infra/kubernetes/images/web-fixture.Dockerfile").read_text()
        runtime = web.split("FROM ")[2]
        self.assertIn(f"rm -rf {NPM_TREE}", runtime)
        acceptance = (ROOT / "infra/kubernetes/images/acceptance.Dockerfile").read_text()
        removal = f"rm -rf {NPM_TREE}"
        self.assertIn(removal, acceptance)
        self.assertLess(acceptance.index("pnpm install"), acceptance.index(removal))
        self.assertLess(acceptance.index(removal), acceptance.index("USER node"))

    def test_api_image_replaces_vulnerable_base_packaging_tools(self):
        dockerfile = (ROOT / "infra/docker/api.Dockerfile").read_text()
        self.assertIn(PYTHON_IMAGE, dockerfile)
        self.assertNotIn("forwarded-allow-ips", dockerfile)
        self.assertIn("--proxy-headers", dockerfile)
        self.assertIn(
            "python -m pip install --require-hashes --no-deps -r scripts/runtime/image-tools.lock",
            dockerfile,
        )
        lock = (ROOT / "scripts/runtime/image-tools.lock").read_text()
        self.assertIn("setuptools==84.1.0", lock)
        self.assertIn("pip==26.2.1", lock)

    def test_fixture_web_root_filesystem_is_read_only(self):
        text = (ROOT / "infra/helm/fel/templates/web.yaml").read_text()
        container = text.split("- name: web", 1)[1].split("startupProbe:", 1)[0]
        self.assertIn("readOnlyRootFilesystem: true", container)
        self.assertIn("mountPath: /tmp", text)
        self.assertIn("mountPath: /workspace/apps/web/.next/cache", text)


if __name__ == "__main__":
    unittest.main()
