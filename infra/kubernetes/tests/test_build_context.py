"""Exercise the build entrypoint without a Docker engine or network."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


class BuildContextTests(unittest.TestCase):
    def test_ignored_files_never_reach_docker_and_context_is_removed(self):
        script = Path(__file__).resolve().parents[1] / "lab.sh"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            scripts = repo / "infra/kubernetes"
            scripts.mkdir(parents=True)
            shutil.copy2(script, scripts / "lab.sh")
            (repo / ".gitignore").write_text("*.log\n.env*\n")
            (repo / "package.json").write_text("{}\n")
            for args in (("init", "-q"), ("add", "."),
                         ("-c", "user.name=Lab Test", "-c", "user.email=lab@example.invalid",
                          "commit", "-qm", "fixture")):
                subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
            (repo / "debug.log").write_text("synthetic-build-context-sentinel\n")
            (repo / ".env.local").write_text("SYNTHETIC_SENTINEL=not-a-credential\n")
            binaries = root / "bin"
            binaries.mkdir()
            docker = binaries / "docker"
            docker.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
context = pathlib.Path(sys.argv[-1])
assert context != pathlib.Path(os.environ["TEST_REPOSITORY"])
assert (context / "package.json").is_file()
assert not (context / "debug.log").exists()
assert not (context / ".env.local").exists()
assert not (context / ".git").exists()
assert "SOURCE_SHA=" in " ".join(sys.argv)
with open(os.environ["TEST_CALLS"], "a") as stream:
    stream.write(json.dumps(str(context)) + "\\n")
''')
            docker.chmod(0o755)
            calls = root / "calls.jsonl"
            env = dict(os.environ, PATH=f"{binaries}:{os.environ['PATH']}",
                       TEST_REPOSITORY=str(repo), TEST_CALLS=str(calls))
            subprocess.run(["bash", str(scripts / "lab.sh"), "build"],
                           check=True, env=env, capture_output=True, text=True)
            import json
            contexts = [Path(json.loads(line)) for line in calls.read_text().splitlines()]
            self.assertEqual(len(contexts), 2)
            self.assertEqual(contexts[0], contexts[1])
            self.assertFalse(contexts[0].exists())


if __name__ == "__main__":
    unittest.main()
