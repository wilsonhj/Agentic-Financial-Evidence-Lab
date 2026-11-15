# FEL local chart

This chart runs one offline fixture Web Deployment and a ClusterIP Service.
`helm test` runs an independent, disposable PostgreSQL/API/worker/Web/browser
stack using the existing extraction cross-stack acceptance. Its real database,
queue, API, review, correction history and SSE paths use synthetic source data
and a deterministic model. The test does not exercise a backend behind the
fixture Deployment or establish public/hosted readiness.

Use the [local lab guide](../../../docs/research/2026-11-15-kubernetes-helm-lab.md) for image builds,
cluster setup and commands. The `local-dev` image tags are local build names,
not published images; reproducible runs should override both tags with the
reviewed Git SHA or set `image.digest`. A digest takes precedence over a tag.
With the default `pullPolicy: Never`, load images into the cluster first.

Kubernetes >= 1.33 is required. PostgreSQL is a [native sidecar](https://kubernetes.io/docs/concepts/workloads/pods/sidecar-containers/):
it starts before the runner and stops when the runner exits, allowing the Job to complete.
All acceptance connections use loopback inside the Pod, preserving the existing
synthetic deployment guards. PostgreSQL listens only on `127.0.0.1` and has no
Service. The fixed `fel-local-only` password belongs only to this disposable DB;
the `extraction-ci` target matches the existing CI acceptance configuration.
An ingress/egress deny policy selects the test Pod; its enforcement depends on
the cluster CNI, and kind's default kindnet does not enforce NetworkPolicy.

All data uses `emptyDir`. Pod deletion discards the database, canonical evidence,
marker and manifest together. No PVC, live provider, public ingress or arbitrary
application environment override is supported. Unknown values fail schema
validation. `acceptance.enabled=false` omits the cross-stack test.

The first test checks the installed fixture Service's health and extraction UI.
The second test runs the isolated full stack. `tests.hookMode=helm` (default)
uses `helm test`; `tests.hookMode=argocd` instead renders controller-owned
PostSync Jobs at waves -10 and 0 ([Argo CD hooks](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-waves/)).
Use a full Argo CD sync for that mode, never
`helm test` or selective sync (which skips hooks). Do not manage one release
with both Helm and Argo CD. Only one controller's hook annotations are emitted.

The test Job has no retry and a 15-minute deadline. Helm retains it until the
next test (`before-hook-creation`) or explicit cleanup. Capture logs before
rerunning; [hook resources](https://helm.sh/docs/topics/charts_hooks/) are not managed by `helm uninstall`. Test-result files
inside the terminated runner cannot be retrieved using `kubectl cp`; use the
runner's log artifacts or collect files while it is running. The Web health
probe checks process startup, not API, provider or database readiness.

Run `helm test RELEASE -n NAMESPACE --timeout 16m` without `--logs`.
Helm 3.22.1's [log reader](https://github.com/helm/helm/blob/v3.22.1/pkg/action/release_testing.go#L119)
looks for a Pod with the hook's name, whereas Jobs create Pods with suffixes;
`--logs` therefore reports failure even when these Job tests pass. Collect
each Job explicitly using the lab kubeconfig:

```bash
kubectl --kubeconfig "$FEL_LAB_STATE/kubeconfig" -n fel-lab logs job/fel-lab-web-smoke -c web-smoke
kubectl --kubeconfig "$FEL_LAB_STATE/kubeconfig" -n fel-lab logs job/fel-lab-acceptance -c acceptance
```

Default container memory limits total 5 GiB (4 GiB runner, 512 MiB Web,
512 MiB PostgreSQL); allow additional memory for Kubernetes and image builds.
These are initial lab limits, not measured performance or production sizing.
