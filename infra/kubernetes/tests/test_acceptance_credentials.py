"""Offline checks for the disposable lab's credential and environment boundary."""

import io
import os
import secrets
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

RUNNER = Path(__file__).resolve().parents[1] / "run-acceptance.sh"


def load_runner():
    source = RUNNER.read_text().split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    module = types.ModuleType("acceptance_runner_test")
    exec(compile(source, str(RUNNER), "exec"), module.__dict__)
    return module


class AcceptanceCredentialTests(unittest.TestCase):
    def setUp(self):
        self.runner = load_runner()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.runner.CREDENTIAL_FILE = self.root / "password"
        self.runner.ROOT = self.root / "workspace"
        self.runner.WORK = self.root / "work"
        marker = self.runner.ROOT / "apps/web/playwright.cross-stack.config.ts"
        marker.parent.mkdir(parents=True)
        marker.touch()
        self.runner.WORK.mkdir()
        self.environment = patch.dict(os.environ, {"FEL_ACCEPTANCE_LOCAL": "1"}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def initialize(self):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            self.runner.initialize_credential()
        self.assertFalse(output.getvalue(), "initialization must not emit credential material")
        return self.runner.CREDENTIAL_FILE.read_text()

    def assert_refused(self, callback):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            with self.assertRaises(SystemExit) as error:
                callback()
        self.assertEqual(
            str(error.exception), "Refusing acceptance: dedicated local lab configuration required"
        )
        self.assertFalse(output.getvalue(), "refusal must not emit inherited or file values")

    def test_each_job_generates_private_material_without_overwriting(self):
        first = self.initialize()
        self.assertTrue(len(first) == 64 and all(c in "0123456789abcdef" for c in first))
        self.assertEqual(stat.S_IMODE(self.runner.CREDENTIAL_FILE.stat().st_mode), 0o640)
        self.assertEqual(self.runner.CREDENTIAL_FILE.stat().st_uid, os.geteuid())
        self.assert_refused(self.runner.initialize_credential)
        self.assertTrue(self.runner.CREDENTIAL_FILE.read_text() == first)
        self.runner.CREDENTIAL_FILE = self.root / "another-job-password"
        second = self.initialize()
        self.assertTrue(first != second, "independent Jobs must generate independent credentials")

    def test_environment_uses_only_generated_loopback_database_and_allowlist(self):
        expected = self.initialize()
        os.environ["UNRELATED_PROVIDER_KEY"] = secrets.token_hex(32)
        environment, password = self.runner.acceptance_environment()
        parsed = urlsplit(environment["FEL_DATABASE_URL"])
        self.assertTrue(password == expected and parsed.password == expected)
        self.assertEqual(
            (parsed.scheme, parsed.hostname, parsed.port, parsed.username),
            ("postgresql", "127.0.0.1", 5432, "fel"),
        )
        self.assertEqual(parsed.path, "/fel_extraction_acceptance")
        self.assertFalse(parsed.query or parsed.fragment)
        self.assertNotIn("UNRELATED_PROVIDER_KEY", environment)
        self.assertFalse(any(key.startswith("PG") for key in environment))

    def test_inherited_database_urls_are_rejected_even_when_empty_or_local(self):
        password = self.initialize()
        candidates = (
            "",
            f"postgresql://fel:{password}@127.0.0.1:5432/fel_extraction_acceptance",
            f"postgresql://fel:{password}@example.invalid:5432/fel_extraction_acceptance",
        )
        for candidate in candidates:
            with patch.dict(os.environ, {"FEL_DATABASE_URL": candidate}):
                self.assert_refused(self.runner.acceptance_environment)
                self.assert_refused(lambda: self.runner.main([]))

    def test_libpq_overrides_and_missing_lab_marker_are_rejected(self):
        self.initialize()
        for name in ("PGHOST", "PGHOSTADDR", "PGSERVICE", "PGPASSFILE", "PGOPTIONS"):
            with patch.dict(os.environ, {name: ""}):
                self.assert_refused(self.runner.acceptance_environment)
        with patch.dict(os.environ, {}, clear=True):
            self.assert_refused(self.runner.acceptance_environment)

    def test_shell_entrypoint_rejects_inherited_url_before_loading_database_driver(self):
        binaries = self.root / "bin"
        binaries.mkdir()
        (binaries / "python").symlink_to(sys.executable)
        injected = secrets.token_hex(32)
        result = subprocess.run(
            ["/bin/bash", str(RUNNER)],
            env={
                "PATH": f"{binaries}:/usr/bin:/bin",
                "FEL_ACCEPTANCE_LOCAL": "1",
                "FEL_DATABASE_URL": injected,
            },
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(injected in result.stdout or injected in result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            result.stderr.strip(), "Refusing acceptance: dedicated local lab configuration required"
        )

    def test_missing_malformed_or_permissive_file_is_rejected(self):
        self.assert_refused(self.runner.acceptance_environment)
        self.initialize()
        self.runner.CREDENTIAL_FILE.chmod(0o644)
        self.assert_refused(self.runner.acceptance_environment)
        self.runner.CREDENTIAL_FILE.chmod(0o640)
        for malformed in ("", secrets.token_hex(32) + "\n", secrets.token_hex(33), "!" * 64):
            self.runner.CREDENTIAL_FILE.write_text(malformed)
            self.assert_refused(self.runner.acceptance_environment)

    def test_symlink_file_is_rejected_for_initialization_and_consumption(self):
        self.initialize()
        original = self.runner.CREDENTIAL_FILE
        self.runner.CREDENTIAL_FILE = self.root / "linked-password"
        self.runner.CREDENTIAL_FILE.symlink_to(original)
        self.assert_refused(self.runner.initialize_credential)
        self.assert_refused(self.runner.acceptance_environment)

    def test_nonregular_file_is_rejected_without_blocking(self):
        os.mkfifo(self.runner.CREDENTIAL_FILE, 0o640)
        self.assert_refused(self.runner.acceptance_environment)

    def test_nonempty_work_directory_is_rejected(self):
        self.initialize()
        (self.runner.WORK / "prior-run").touch()
        self.assert_refused(self.runner.acceptance_environment)

    def test_output_masks_generated_material_and_every_url(self):
        password = self.initialize()
        line = (
            f"bare={password} database=postgresql://fel:{password}@127.0.0.1:5432/db "
            f"remote=https://example.invalid/?value={password} ordinary diagnostic\n"
        )
        safe = self.runner.redact_output(line, password)
        self.assertFalse(password in safe or "://" in safe)
        self.assertIn("ordinary diagnostic", safe)


if __name__ == "__main__":
    unittest.main()
