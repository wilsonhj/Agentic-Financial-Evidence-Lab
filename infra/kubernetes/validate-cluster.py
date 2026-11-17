#!/usr/bin/env python3
"""Exercise an already deployed, owned FEL lab; record evidence, never a load claim."""

import argparse
import ipaddress
import json
import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc  # noqa: UP017 -- The host-only CLI also supports macOS Python 3.9.
PROBE = """const http = require('node:http');
const timer = setTimeout(() => {
  console.log(JSON.stringify({outcome:'timeout'})); process.exit(3);
}, 2500);
const request = http.get(process.argv[1], response => {
  response.resume(); response.on('end', () => {
    clearTimeout(timer);
    console.log(JSON.stringify({outcome:'response', status:response.statusCode}));
    process.exit(response.statusCode === 200 ? 0 : 2);
  });
});
request.on('error', error => {
  clearTimeout(timer);
  console.log(JSON.stringify({outcome:'error', code:error.code})); process.exit(4);
});"""


class Validation:
    def __init__(self, state, cluster, interval):
        self.state, self.cluster, self.interval = state, cluster, interval
        self.nonce = uuid.uuid4().hex[:10]
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.output = state / "evidence" / f"validation-{stamp}-{self.nonce}"
        self.kube = [
            "kubectl",
            "--kubeconfig",
            str(state / "kubeconfig"),
            "--context",
            f"kind-{cluster}",
            "--request-timeout=15s",
            "-n",
            "fel-lab",
        ]
        self.lab = ["bash", str(ROOT / "infra/kubernetes/lab.sh")]
        self.environment = dict(os.environ, FEL_LAB_STATE=str(state), FEL_LAB_CLUSTER=cluster)
        self.result = {
            "status": "failed",
            "cluster": cluster,
            "started_at": stamp,
            "host": {"platform": platform.platform(), "architecture": platform.machine()},
            "stages": [],
            "commands": [],
            "samples": 0,
            "successful_samples": 0,
        }
        self.stop = threading.Event()
        self.sampler = None

    def run(self, label, arguments, *, check=True, timeout=45, payload=None):
        started = time.monotonic()
        number = len(self.result["commands"]) + 1
        log = self.output / f"{number:03d}-{label}.log"
        entry = {"name": label, "argv": arguments, "log": log.name}
        self.result["commands"].append(entry)
        print(f"Validation step: {label}", flush=True)
        try:
            process = subprocess.Popen(
                arguments,
                env=self.environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            try:
                stdout, stderr = process.communicate(payload, timeout=timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                raise
            log.write_text(stdout + stderr)
            entry.update(exit_code=process.returncode, seconds=round(time.monotonic() - started, 3))
            if check and process.returncode:
                raise RuntimeError(f"{label} failed (exit {process.returncode}); see {log.name}")
            return subprocess.CompletedProcess(arguments, process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            entry.update(exit_code=None, seconds=round(time.monotonic() - started, 3))
            log.write_text(f"Command exceeded {timeout} seconds.\n")
            raise RuntimeError(f"{label} exceeded its deadline") from None

    def jobs(self, stage):
        identities = {}
        self.result.setdefault("pod_uids", {})[stage] = self.run(
            f"{stage}-pod-uids",
            self.kube
            + [
                "get",
                "pods",
                "-l",
                "app.kubernetes.io/instance=fel-lab",
                "-o",
                'jsonpath={range .items[*]}{.metadata.name}{" "}{.metadata.uid}{"\\n"}{end}',
            ],
        ).stdout
        for name in ("web-smoke", "acceptance"):
            value = self.run(
                f"{stage}-{name}-uid",
                self.kube + ["get", "job", f"fel-lab-{name}", "-o", "jsonpath={.metadata.uid}"],
            ).stdout.strip()
            if not value:
                raise RuntimeError(f"{stage}: {name} has no Job UID")
            identities[name] = value
        return identities

    def sample(self):
        peaks = {
            "node_working_set_bytes": 0,
            "node_cpu_nanocores": 0,
            "docker_cpu_percent": 0,
            "pod_working_set_bytes": {},
        }
        with (self.output / "samples.jsonl").open("w") as stream:
            while not self.stop.is_set():
                sample = {"time": datetime.now(UTC).isoformat()}
                try:
                    raw = subprocess.run(
                        self.kube
                        + [
                            "get",
                            "--raw",
                            f"/api/v1/nodes/{self.cluster}-control-plane/proxy/stats/summary",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=8,
                        env=self.environment,
                    )
                    raw.check_returncode()
                    stats = json.loads(raw.stdout)
                    memory = stats["node"].get("memory", {}).get("workingSetBytes") or 0
                    cpu = stats["node"].get("cpu", {}).get("usageNanoCores") or 0
                    sample.update(node_memory_bytes=memory, node_cpu_nanocores=cpu)
                    sample["pod_memory_bytes"] = {
                        pod["podRef"]["name"]: pod.get("memory", {}).get("workingSetBytes") or 0
                        for pod in stats.get("pods", [])
                        if pod["podRef"]["namespace"] == "fel-lab"
                    }
                    peaks["node_working_set_bytes"] = max(peaks["node_working_set_bytes"], memory)
                    peaks["node_cpu_nanocores"] = max(peaks["node_cpu_nanocores"], cpu)
                    for name, value in sample["pod_memory_bytes"].items():
                        prior = peaks["pod_working_set_bytes"].get(name, 0)
                        peaks["pod_working_set_bytes"][name] = max(prior, value)
                    docker = subprocess.run(
                        [
                            "docker",
                            "stats",
                            "--no-stream",
                            "--format",
                            "{{.CPUPerc}}",
                            f"{self.cluster}-control-plane",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=8,
                    )
                    docker.check_returncode()
                    sample["docker_cpu_percent"] = float(docker.stdout.strip().rstrip("%"))
                    peaks["docker_cpu_percent"] = max(
                        peaks["docker_cpu_percent"], sample["docker_cpu_percent"]
                    )
                    self.result["successful_samples"] += 1
                except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
                    sample["collection_error"] = type(error).__name__
                stream.write(json.dumps(sample, sort_keys=True) + "\n")
                stream.flush()
                self.result["samples"] += 1
                self.stop.wait(self.interval)
        self.result["sampled_peaks"] = peaks

    def network(self):
        image = self.run(
            "probe-image",
            self.kube
            + [
                "get",
                "deployment",
                "fel-lab-web",
                "-o",
                "jsonpath={.spec.template.spec.containers[0].image}",
            ],
        ).stdout.strip()
        names = {role: f"fel-probe-{role}-{self.nonce}" for role in ("control", "isolated")}
        try:
            for role, name in names.items():
                component = "acceptance" if role == "isolated" else "validation"
                labels = {
                    "fel-validation-id": self.nonce,
                    "app.kubernetes.io/instance": "fel-lab",
                    "app.kubernetes.io/component": component,
                }
                server = "require('node:http').createServer((q,r)=>r.end('ok'))"
                pod = {
                    "apiVersion": "v1",
                    "kind": "Pod",
                    "metadata": {"name": name, "labels": labels},
                    "spec": {
                        "restartPolicy": "Never",
                        "activeDeadlineSeconds": 300,
                        "automountServiceAccountToken": False,
                        "enableServiceLinks": False,
                        "securityContext": {
                            "runAsNonRoot": True,
                            "runAsUser": 1000,
                            "runAsGroup": 1000,
                            "seccompProfile": {"type": "RuntimeDefault"},
                        },
                        "containers": [
                            {
                                "name": "probe",
                                "image": image,
                                "imagePullPolicy": "IfNotPresent",
                                "command": ["node", "-e", server + ".listen(8080,'0.0.0.0')"],
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "readOnlyRootFilesystem": True,
                                    "capabilities": {"drop": ["ALL"]},
                                },
                                "readinessProbe": {
                                    "exec": {
                                        "command": ["node", "-e", PROBE, "http://127.0.0.1:8080"]
                                    },
                                    "timeoutSeconds": 5,
                                    "periodSeconds": 3,
                                },
                                "resources": {
                                    "requests": {"cpu": "10m", "memory": "32Mi"},
                                    "limits": {"cpu": "100m", "memory": "128Mi"},
                                },
                            }
                        ],
                    },
                }
                self.run(
                    f"create-{role}", self.kube + ["create", "-f", "-"], payload=json.dumps(pod)
                )
            self.run(
                "probe-ready",
                self.kube
                + [
                    "wait",
                    "--for=condition=Ready",
                    "pod",
                    *names.values(),
                    "--timeout=90s",
                    "--request-timeout=100s",
                ],
                timeout=110,
            )
            addresses = {
                role: str(
                    ipaddress.ip_address(
                        self.run(
                            f"{role}-ip",
                            self.kube + ["get", "pod", name, "-o", "jsonpath={.status.podIP}"],
                        ).stdout.strip()
                    )
                )
                for role, name in names.items()
            }
            addresses = {role: f"[{ip}]" if ":" in ip else ip for role, ip in addresses.items()}
            outcomes = {}
            for label, role, url, denied in (
                ("control-service", "control", "http://fel-lab-web:3000/api/health", False),
                ("control-listener", "control", f"http://{addresses['control']}:8080", False),
                ("isolated-loopback", "isolated", "http://127.0.0.1:8080", False),
                ("isolated-egress", "isolated", f"http://{addresses['control']}:8080", True),
                ("isolated-ingress", "control", f"http://{addresses['isolated']}:8080", True),
            ):
                for attempt in range(10 if denied else 1):
                    probe = self.run(
                        f"{label}-{attempt}",
                        self.kube + ["exec", names[role], "--", "node", "-e", PROBE, url],
                        check=False,
                        timeout=20,
                    )
                    outcome = json.loads(probe.stdout)
                    expected = (
                        (probe.returncode == 3 and outcome.get("outcome") == "timeout")
                        if denied
                        else (probe.returncode == 0 and outcome.get("status") == 200)
                    )
                    if expected:
                        outcomes[label] = outcome
                        break
                    if outcome.get("outcome") != "response" or not denied:
                        raise RuntimeError(f"{label} failed without the expected network outcome")
                    time.sleep(1)
                else:
                    raise RuntimeError(f"{label}: traffic remained allowed")
            self.result["network_policy"] = outcomes
        finally:
            self.run(
                "delete-probes",
                self.kube
                + [
                    "delete",
                    "pods",
                    "-l",
                    f"fel-validation-id={self.nonce}",
                    "--ignore-not-found=true",
                    "--wait=true",
                    "--timeout=60s",
                    "--request-timeout=70s",
                ],
                timeout=80,
            )

    def execute(self):
        self.output.mkdir(parents=True)
        print(f"Validation evidence: {self.output}", flush=True)
        started = time.monotonic()
        try:
            # First cluster operation checks ownership. Failure still gets a summary.
            self.run("ownership", self.lab + ["status"])
            self.result["validator_source_sha"] = self.run(
                "source", ["git", "-C", str(ROOT), "rev-parse", "HEAD"]
            ).stdout.strip()
            self.result["fixture_image_ids"] = self.run(
                "fixture-image-ids",
                self.kube
                + [
                    "get",
                    "pods",
                    "-l",
                    "app.kubernetes.io/component=fixture-web",
                    "-o",
                    "jsonpath={.items[*].status.containerStatuses[*].imageID}",
                ],
            ).stdout.strip()
            self.result["docker"] = json.loads(
                self.run(
                    "docker-info",
                    [
                        "docker",
                        "info",
                        "--format",
                        '{"cpus":{{.NCPU}},"memory_bytes":{{.MemTotal}},"version":"{{.ServerVersion}}"}',
                    ],
                ).stdout
            )
            self.result["node_limits"] = json.loads(
                self.run(
                    "node-limits",
                    [
                        "docker",
                        "inspect",
                        "--format",
                        '{"nano_cpus":{{.HostConfig.NanoCpus}},"memory_bytes":{{.HostConfig.Memory}}}',
                        f"{self.cluster}-control-plane",
                    ],
                ).stdout
            )
            if self.interval:
                self.sampler = threading.Thread(target=self.sample, daemon=True)
                self.sampler.start()
            self.run("baseline", self.lab + ["test"], timeout=1100)
            baseline = self.jobs("baseline")
            self.result["stages"].append({"name": "baseline", "status": "passed", "jobs": baseline})
            try:
                self.run(
                    "scale-down", self.kube + ["scale", "deployment/fel-lab-web", "--replicas=0"]
                )
                for _ in range(45):
                    pods = self.run(
                        "wait-web-down",
                        self.kube
                        + [
                            "get",
                            "pods",
                            "-l",
                            "app.kubernetes.io/instance=fel-lab,app.kubernetes.io/component=fixture-web",
                            "-o",
                            "name",
                        ],
                    )
                    if not pods.stdout.strip():
                        break
                    time.sleep(2)
                else:
                    raise RuntimeError("Fixture Pods did not terminate")
                failed = self.run(
                    "expected-smoke-failure", self.lab + ["test"], check=False, timeout=1100
                )
                if failed.returncode == 0:
                    raise RuntimeError("Smoke passed with its Deployment scaled to zero")
                condition = self.run(
                    "smoke-failure-condition",
                    self.kube
                    + [
                        "get",
                        "job",
                        "fel-lab-web-smoke",
                        "-o",
                        'jsonpath={.status.conditions[?(@.type=="Failed")].status}',
                    ],
                )
                if condition.stdout.strip() != "True":
                    raise RuntimeError("Failure did not come from a failed smoke Job")
                absent = self.run(
                    "acceptance-must-be-absent",
                    self.kube
                    + ["get", "job", "fel-lab-acceptance", "--ignore-not-found=true", "-o", "json"],
                )
                if absent.stdout.strip():
                    raise RuntimeError("Skipped acceptance retained a stale Job")
                self.result["stages"].append(
                    {
                        "name": "failure",
                        "status": "passed",
                        "helm_exit": failed.returncode,
                        "acceptance_job_absent": True,
                    }
                )
            finally:
                self.run(
                    "restore-replicas",
                    self.kube + ["scale", "deployment/fel-lab-web", "--replicas=1"],
                )
                self.run(
                    "restore-ready",
                    self.kube
                    + [
                        "rollout",
                        "status",
                        "deployment/fel-lab-web",
                        "--timeout=120s",
                        "--request-timeout=130s",
                    ],
                    timeout=140,
                )
            self.run("recovery", self.lab + ["test"], timeout=1100)
            recovery = self.jobs("recovery")
            if any(recovery[name] == baseline[name] for name in baseline):
                raise RuntimeError("Recovery reused a baseline Job")
            self.result["stages"].append({"name": "recovery", "status": "passed", "jobs": recovery})
            self.network()
            self.result["status"] = "passed"
        except (
            OSError,
            ValueError,
            RuntimeError,
            subprocess.SubprocessError,
            KeyboardInterrupt,
        ) as error:
            self.result["error"] = str(error) or type(error).__name__
        finally:
            self.stop.set()
            if self.sampler:
                self.sampler.join(timeout=20)
            self.result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            self.result["measurement_scope"] = (
                "Sampled local validation; excludes image builds; not a capacity or load test."
            )
            (self.output / "summary.json").write_text(
                json.dumps(self.result, indent=2, sort_keys=True) + "\n"
            )
            print(f"Validation {self.result['status']}: {self.output / 'summary.json'}", flush=True)
        return 0 if self.result["status"] == "passed" else 1


def main():
    signal.signal(signal.SIGTERM, lambda *_: signal.raise_signal(signal.SIGINT))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample-seconds", type=float, default=2, help="Sampling interval; 0 disables measurement"
    )
    arguments = parser.parse_args()
    state = os.environ.get("FEL_LAB_STATE", "")
    cluster = os.environ.get("FEL_LAB_CLUSTER", "fel-helm-lab")
    if not state or not Path(state).is_absolute() or not re.fullmatch(r"fel-[a-z0-9-]+", cluster):
        parser.error("Set an absolute FEL_LAB_STATE and a FEL_LAB_CLUSTER starting fel-.")
    if not 0 <= arguments.sample_seconds <= 60:
        parser.error("--sample-seconds must be between 0 and 60")
    return Validation(Path(state), cluster, arguments.sample_seconds).execute()


if __name__ == "__main__":
    sys.exit(main())
