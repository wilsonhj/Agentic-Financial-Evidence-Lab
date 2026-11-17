"""Printed chart commands must never silently select the default cluster."""

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

NOTES = Path(__file__).resolve().parents[2] / "helm/fel/templates/NOTES.txt"


class NotesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        executable = self.root / "fake-cli"
        executable.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "with open(os.environ['TEST_CALLS'], 'a') as output:\n"
            "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        )
        executable.chmod(0o755)
        for name in ("helm", "kubectl"):
            (self.root / name).symlink_to(executable)
        self.calls = self.root / "calls.jsonl"
        self.environment = {
            "PATH": f"{self.root}:/usr/bin:/bin",
            "TEST_CALLS": str(self.calls),
        }
        # Replace only Helm names/control tags; exercise the printed shell
        # commands themselves, including their parameter-expansion guards.
        text = NOTES.read_text()
        text = text.replace('{{ include "fel.fullname" . }}', "fel-test")
        text = text.replace("{{ .Release.Namespace }}", "fel-test")
        text = text.replace("{{ .Release.Name }}", "fel-test")
        text = re.sub(r"{{.*?}}", "", text)
        self.commands = [
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith(("kubectl ", "helm "))
        ]
        self.assertEqual(len(self.commands), 4)

    def test_missing_either_explicit_target_fails_before_calling_a_cli(self):
        for missing in ("FEL_KUBECONFIG", "FEL_KUBE_CONTEXT"):
            environment = dict(
                self.environment,
                FEL_KUBECONFIG="/tmp/explicit kubeconfig",
                FEL_KUBE_CONTEXT="kind-explicit",
            )
            del environment[missing]
            for command in self.commands:
                with self.subTest(missing=missing, command=command):
                    result = subprocess.run(
                        ["/bin/bash", "-c", command], env=environment, capture_output=True
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(self.calls.exists())

    def test_every_command_passes_both_explicit_target_arguments(self):
        environment = dict(
            self.environment,
            FEL_KUBECONFIG="/tmp/explicit kubeconfig",
            FEL_KUBE_CONTEXT="kind-explicit",
        )
        for command in self.commands:
            subprocess.run(["/bin/bash", "-c", command], env=environment, check=True)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(len(calls), len(self.commands))
        for command, arguments in zip(self.commands, calls, strict=True):
            context_flag = "--kube-context" if command.startswith("helm ") else "--context"
            self.assertEqual(
                arguments[arguments.index("--kubeconfig") + 1], "/tmp/explicit kubeconfig"
            )
            self.assertEqual(arguments[arguments.index(context_flag) + 1], "kind-explicit")


if __name__ == "__main__":
    unittest.main()
