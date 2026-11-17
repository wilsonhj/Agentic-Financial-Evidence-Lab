"""Fault-inject registry lifecycle operations without using Docker or Kubernetes."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "local-registry.sh"
CONTAINER = "a" * 64
REPLACEMENT = "b" * 64
NAMESPACE = "11111111-1111-4111-8111-111111111111"
OTHER_NAMESPACE = "22222222-2222-4222-8222-222222222222"


class LocalRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = Path(self.temporary.name) / "state"
        self.registry = self.state / "registry"
        (self.registry / "tls").mkdir(parents=True)
        for name, value in (
            ("owner", "fel-test"),
            ("node-id", "owned-node"),
            ("kubeconfig", "test"),
            ("registry/container-id", CONTAINER),
            ("registry/namespace-uid", NAMESPACE),
            ("registry/tls/server.key", "nonsecret sentinel"),
            ("container", CONTAINER),
            ("namespace", NAMESPACE),
        ):
            (self.state / name).write_text(value)
        binaries = self.state / "bin"
        binaries.mkdir()
        cli = binaries / "fake-cli"
        cli.write_text(f"#!{sys.executable}\n" + r"""
import json, os, pathlib, sys
name, args = pathlib.Path(sys.argv[0]).name, sys.argv[1:]
state = pathlib.Path(os.environ["FEL_LAB_STATE"])
container, namespace = state / "container", state / "namespace"
with (state / "calls.jsonl").open("a") as stream:
    stream.write(json.dumps([name, *args]) + "\n")
if name == "docker":
    if args[0] == "inspect" and args[-1] == "fel-test-control-plane":
        print("owned-node")
    elif args[:2] == ["container", "ls"]:
        if os.environ.get("TEST_DOCKER_QUERY_ERROR"): sys.exit(7)
        if container.exists(): print(container.read_text())
    elif args[0] == "inspect":
        if os.environ.get("TEST_DOCKER_QUERY_ERROR"): sys.exit(7)
        if not container.exists(): sys.exit(1)
        print(container.read_text())
    elif args[0] == "rm":
        if os.environ.get("TEST_REPLACE_CONTAINER"):
            container.write_text("b" * 64)
        if args[-1] != "fel-test-registry" and (
            not container.exists() or container.read_text() != args[-1]
        ): sys.exit(1)
        container.unlink(missing_ok=True)
    elif args[0] == "run":
        (state / "started").touch()
        print("a" * 64)
elif "namespace" in args and "get" in args:
    if os.environ.get("TEST_NAMESPACE_QUERY_ERROR"): sys.exit(7)
    if namespace.exists(): print(namespace.read_text())
elif "delete" in args:
    if os.environ.get("TEST_NAMESPACE_DELETE_ERROR"): sys.exit(7)
    if os.environ.get("TEST_REPLACE_NAMESPACE"):
        namespace.write_text("22222222-2222-4222-8222-222222222222")
    if "--raw" in args:
        payload = json.load(sys.stdin)
        (state / "delete-options.json").write_text(json.dumps(payload))
        if not namespace.exists() or payload["preconditions"]["uid"] != namespace.read_text():
            sys.exit(9)
    namespace.unlink(missing_ok=True)
elif "wait" in args and namespace.exists():
    sys.exit(8)
""")
        cli.chmod(0o755)
        for name in ("docker", "kubectl"):
            (binaries / name).symlink_to(cli)
        self.environment = dict(
            os.environ,
            PATH=f"{binaries}:{os.environ['PATH']}",
            FEL_LAB_STATE=str(self.state),
            FEL_LAB_CLUSTER="fel-test",
        )

    def run_registry(self, action="delete", **environment):
        return subprocess.run(
            ["bash", str(SCRIPT), action],
            env=dict(self.environment, **environment),
            capture_output=True,
            text=True,
            timeout=10,
        )

    def calls(self):
        return [json.loads(line) for line in (self.state / "calls.jsonl").read_text().splitlines()]

    def assert_key_retained(self):
        self.assertTrue((self.registry / "tls/server.key").exists())

    def test_namespace_delete_failure_can_resume_after_container_removal(self):
        first = self.run_registry(TEST_NAMESPACE_DELETE_ERROR="1")
        self.assertNotEqual(first.returncode, 0)
        self.assertFalse((self.state / "container").exists())
        self.assert_key_retained()
        second = self.run_registry()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertFalse((self.state / "namespace").exists())
        self.assertFalse((self.registry / "tls/server.key").exists())

    def test_already_absent_owned_resources_complete_cleanup(self):
        (self.state / "container").unlink()
        (self.state / "namespace").unlink()
        result = self.run_registry()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.registry / "tls/server.key").exists())

    def test_failed_namespace_creation_can_clean_recorded_container_and_key(self):
        (self.registry / "namespace-uid").write_text("")
        (self.state / "namespace").unlink()
        result = self.run_registry()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.state / "container").exists())
        self.assertFalse((self.registry / "tls/server.key").exists())

    def test_unknown_namespace_is_preserved_after_lost_create_response(self):
        (self.registry / "namespace-uid").unlink()
        result = self.run_registry()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse((self.state / "container").exists())
        self.assertFalse((self.registry / "tls/server.key").exists())
        self.assertEqual((self.state / "namespace").read_text(), NAMESPACE)
        self.assertTrue((self.registry / "container-id").exists())
        self.assertIn("namespace has no recorded UID", result.stderr)
        self.assertFalse(any("delete" in call for call in self.calls()))

    def test_partial_create_query_error_preserves_state_for_retry(self):
        (self.registry / "namespace-uid").write_text("")
        result = self.run_registry(TEST_NAMESPACE_QUERY_ERROR="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.state / "container").read_text(), CONTAINER)
        self.assert_key_retained()

    def test_query_errors_never_mean_absence_or_permit_mutation(self):
        for variable in ("TEST_DOCKER_QUERY_ERROR", "TEST_NAMESPACE_QUERY_ERROR"):
            with self.subTest(variable=variable):
                result = self.run_registry(**{variable: "1"})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((self.state / "container").read_text(), CONTAINER)
                self.assertEqual((self.state / "namespace").read_text(), NAMESPACE)
                self.assert_key_retained()

    def test_wrong_ownership_refuses_before_any_deletion(self):
        for path, replacement in (("container", REPLACEMENT), ("namespace", OTHER_NAMESPACE)):
            with self.subTest(path=path):
                (self.state / path).write_text(replacement)
                result = self.run_registry()
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue((self.state / "container").exists())
                self.assertTrue((self.state / "namespace").exists())
                self.assert_key_retained()
                (self.state / path).write_text(CONTAINER if path == "container" else NAMESPACE)

    def test_container_replacement_during_delete_is_preserved(self):
        result = self.run_registry(TEST_REPLACE_CONTAINER="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.state / "container").read_text(), REPLACEMENT)
        self.assertTrue((self.state / "namespace").exists())
        self.assert_key_retained()

    def test_namespace_replacement_during_delete_is_preserved(self):
        result = self.run_registry(TEST_REPLACE_NAMESPACE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.state / "namespace").read_text(), OTHER_NAMESPACE)
        self.assert_key_retained()

    def test_deletions_use_recorded_container_id_and_namespace_precondition(self):
        result = self.run_registry()
        self.assertEqual(result.returncode, 0, result.stderr)
        removal = next(call for call in self.calls() if call[:2] == ["docker", "rm"])
        self.assertEqual(removal[-1], CONTAINER)
        options = json.loads((self.state / "delete-options.json").read_text())
        self.assertEqual(options["preconditions"], {"uid": NAMESPACE})
        for call in self.calls():
            if call[0] == "kubectl":
                self.assertIn(str(self.state / "kubeconfig"), call)
                self.assertIn("kind-fel-test", call)

    def test_create_preflight_query_failure_does_not_start_registry(self):
        for path in sorted(self.registry.rglob("*"), reverse=True):
            path.rmdir() if path.is_dir() else path.unlink()
        self.registry.rmdir()
        (self.state / "container").unlink()
        (self.state / "namespace").unlink()
        result = self.run_registry("create", TEST_NAMESPACE_QUERY_ERROR="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.state / "started").exists())
        self.assertFalse(self.registry.exists())


if __name__ == "__main__":
    unittest.main()
