# FEL GitOps lab

This optional path promotes the [FEL chart](../helm/fel/README.md) through
Kargo into Argo CD. It runs the fixture Web Service smoke test and the separate
synthetic PostgreSQL/API/worker/browser acceptance stack. It does not establish
hosted or production readiness. Start with the [local lab guide](../../docs/research/2026-11-15-kubernetes-helm-lab.md).

Use release/namespace `fel-local` here; `lab.sh` uses `fel-lab`. Do not run both
acceptance environments simultaneously on a 16 GB Mac. Never manage the same
release with Helm and Argo CD. Commands below are operator recipes, not evidence
that images, charts, or this GitOps deployment have already been published/run.

## 1. Prepare controllers and registry access

Use Kubernetes >=1.33 (the lab pins 1.37.0), Helm 3.22.1, Argo CD 3.6.1 and
Kargo 1.12.5. Run shell examples in Bash from the repository root. Use the
dedicated lab kubeconfig, or explicitly select your Vagrant cluster instead:

```bash
set -euo pipefail
export FEL_KUBECONFIG="${FEL_LAB_STATE:?Set the state directory used by lab.sh}/kubeconfig"
export FEL_KUBE_CONTEXT="kind-${FEL_LAB_CLUSTER:-fel-helm-lab}"
k() { kubectl --kubeconfig "$FEL_KUBECONFIG" --context "$FEL_KUBE_CONTEXT" "$@"; }
h() { helm --kubeconfig "$FEL_KUBECONFIG" --kube-context "$FEL_KUBE_CONTEXT" "$@"; }
k get nodes -o wide
```

If the controllers are absent, these pinned commands install them. This example
disables Kargo's API/UI and uses Kubernetes resources directly; enabling its UI
later requires the authentication setup in the [official installation guide](https://docs.kargo.io/operator-guide/basic-installation/).

```bash
k create namespace argocd --dry-run=client -o yaml | k apply -f -
k apply --server-side -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.6.1/manifests/install.yaml
k -n argocd wait --for=condition=Available deployment --all --timeout=600s
k -n argocd rollout status statefulset/argocd-application-controller --timeout=600s
k apply --server-side -f https://github.com/cert-manager/cert-manager/releases/download/v1.20.5/cert-manager.yaml
k -n cert-manager wait --for=condition=Available deployment --all --timeout=300s
h upgrade --install kargo oci://ghcr.io/akuity/kargo-charts/kargo \
  --version 1.12.5 --namespace kargo --create-namespace \
  --set api.enabled=false --set api.adminAccount.enabled=false --wait --timeout 10m
```

Use your existing GitHub/GHCR credential setup; never put tokens into Git,
chart values, or command examples. Permissions are separate:

| Consumer | Access and configuration |
|---|---|
| Image/chart publisher | GHCR package write; authenticate Docker and Helm separately |
| Kargo | Git contents write for the deployment branch; chart read; project Secrets in `fel-delivery`, labeled `kargo.akuity.io/cred-type: git` or `helm` |
| Argo repo-server | Git/chart read; repository Secrets in `argocd` |
| Workload kubelet | Private image pull credentials in `fel-local` |

Kargo's Git credential URL is `https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab.git`;
its Helm credential URL is `oci://ghcr.io/wilsonhj/charts/fel`. Argo's private
Helm repository uses `url: ghcr.io/wilsonhj/charts`, `type: helm`, and
`enableOCI: "true"`. Public reads may be anonymous, but Git writes require an
identity allowed by repository rules. The chart intentionally exposes no arbitrary
secret values. For private images, pre-create `fel-local` and attach an existing
image-pull Secret to its default ServiceAccount before syncing. [Kargo credentials](https://github.com/akuity/kargo/blob/v1.12.5/docs/docs/50-user-guide/50-security/30-managing-secrets.md), [Argo repositories](https://argo-cd.readthedocs.io/en/release-3.6/user-guide/private-repositories/)

## 2. Publish ARM64 images and a chart with fixed image digests

After the local acceptance passes, build from its clean committed source.
The following commands publish packages: run them only when intentionally
releasing. They require Docker Buildx, Python 3 and Ruby/Psych, plus an existing
GHCR login. Pick a new chart version on every release; never replace a published
version. `linux/arm64,linux/amd64` is optional when both builds are validated.

```bash
test -z "$(git status --porcelain --untracked-files=normal)"
export FEL_SOURCE_SHA=$(git rev-parse HEAD)
export FEL_CHART_VERSION=0.1.0
export FEL_RELEASE_DIR=$(mktemp -d)
mkdir "$FEL_RELEASE_DIR/source"
git archive --format=tar "$FEL_SOURCE_SHA" | tar -xf - -C "$FEL_RELEASE_DIR/source"
export FEL_WEB_REPO=ghcr.io/wilsonhj/fel-web-fixture
export FEL_ACCEPTANCE_REPO=ghcr.io/wilsonhj/fel-acceptance
docker buildx build --platform linux/arm64 --build-arg SOURCE_SHA="$FEL_SOURCE_SHA" \
  -f "$FEL_RELEASE_DIR/source/infra/kubernetes/images/web-fixture.Dockerfile" -t "$FEL_WEB_REPO:$FEL_SOURCE_SHA" \
  --metadata-file "$FEL_RELEASE_DIR/web.json" --push "$FEL_RELEASE_DIR/source"
docker buildx build --platform linux/arm64 --build-arg SOURCE_SHA="$FEL_SOURCE_SHA" \
  -f "$FEL_RELEASE_DIR/source/infra/kubernetes/images/acceptance.Dockerfile" -t "$FEL_ACCEPTANCE_REPO:$FEL_SOURCE_SHA" \
  --metadata-file "$FEL_RELEASE_DIR/acceptance.json" --push "$FEL_RELEASE_DIR/source"
export FEL_WEB_DIGEST=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["containerimage.digest"])' "$FEL_RELEASE_DIR/web.json")
export FEL_ACCEPTANCE_DIGEST=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["containerimage.digest"])' "$FEL_RELEASE_DIR/acceptance.json")
docker buildx imagetools inspect pgvector/pgvector:0.8.5-pg17 \
  --format '{{json .Manifest}}' > "$FEL_RELEASE_DIR/postgres.json"
export FEL_POSTGRES_DIGEST=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert any(m.get("platform",{}).get("architecture")=="arm64" and m["platform"].get("os")=="linux" for m in d["manifests"]); print(d["digest"])' "$FEL_RELEASE_DIR/postgres.json")
cp -R infra/helm/fel "$FEL_RELEASE_DIR/fel"
ruby -ryaml - "$FEL_RELEASE_DIR/fel/values.yaml" <<'RUBY'
path = ARGV.fetch(0)
values = YAML.safe_load(File.read(path))
[
  [values.fetch('web').fetch('image'), ENV.fetch('FEL_WEB_REPO'), ENV.fetch('FEL_WEB_DIGEST')],
  [values.fetch('acceptance').fetch('image'), ENV.fetch('FEL_ACCEPTANCE_REPO'), ENV.fetch('FEL_ACCEPTANCE_DIGEST')],
  [values.fetch('acceptance').fetch('postgres').fetch('image'), 'pgvector/pgvector', ENV.fetch('FEL_POSTGRES_DIGEST')]
].each do |image, repo, digest|
  raise 'Invalid digest' unless digest.match?(/\Asha256:[0-9a-f]{64}\z/)
  image.merge!('repository' => repo, 'tag' => '', 'digest' => digest, 'pullPolicy' => 'IfNotPresent')
end
File.write(path, YAML.dump(values))
RUBY
helm lint "$FEL_RELEASE_DIR/fel" --strict
helm template fel-local "$FEL_RELEASE_DIR/fel" --namespace fel-local \
  --kube-version 1.37.0 --set tests.hookMode=argocd > "$FEL_RELEASE_DIR/rendered.yaml"
helm package "$FEL_RELEASE_DIR/fel" --version "$FEL_CHART_VERSION" \
  --app-version "$FEL_SOURCE_SHA" --destination "$FEL_RELEASE_DIR"
helm push "$FEL_RELEASE_DIR/fel-$FEL_CHART_VERSION.tgz" oci://ghcr.io/wilsonhj/charts
```

Keep the release directory as provenance: it contains source/version-related
metadata, actual digests, packaged defaults and rendered manifests. The package
contains `IfNotPresent` and digest references; the source chart's `Never` defaults
are only for preloaded local images. Buildx metadata contains the pushed digest,
not a guessed local image ID. [Buildx metadata](https://docs.docker.com/reference/cli/docker/buildx/build/#metadata-file), [registry inspection](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/), [Helm OCI](https://helm.sh/docs/v3/topics/registries/)

## 3. Bootstrap the environment branch

In a separate clean clone, create `deploy/local` from a `main` commit containing
the lab files: `git switch -c deploy/local origin/main`. If the remote branch
already exists, use it instead; never reset it. Create these three files there.

`deploy/environments/local/Chart.yaml`:

```yaml
apiVersion: v2
name: fel-local
type: application
version: 0.1.0
dependencies:
  - name: fel
    version: 0.1.0 # The chart version actually published above.
    repository: oci://ghcr.io/wilsonhj/charts
```

`deploy/environments/local/values.yaml`:

```yaml
fel:
  tests:
    hookMode: argocd
  acceptance:
    enabled: true
```

`deploy/environments/local/.gitignore` contains `/charts/`. Generate the lockfile,
review the rendered image digests and two PostSync Jobs, then commit and push:

```bash
helm dependency update deploy/environments/local
helm template fel-local deploy/environments/local --namespace fel-local --kube-version 1.37.0
git add deploy/environments/local/Chart.yaml deploy/environments/local/Chart.lock \
  deploy/environments/local/values.yaml deploy/environments/local/.gitignore
git commit -m 'Bootstrap local FEL chart environment'
git push -u origin deploy/local
```

Commit the generated `Chart.lock`; do not handcraft its digest. Reconstruct later
with `helm dependency build`. Kargo's updater regenerates the lock automatically.
The parent URI in Chart.yaml/updater is different from the **full** chart URI
used by Warehouse/`chartFrom`. A missing Kargo branch with `create: true` becomes
an empty orphan, so this guide uses `create: false`. [Kargo chart update](https://github.com/akuity/kargo/blob/v1.12.5/docs/docs/50-user-guide/60-reference-docs/30-promotion-steps/helm-update-chart.md), [lockfile implementation](https://github.com/akuity/kargo/blob/v1.12.5/pkg/helm/dependency_manager.go), [git-clone](https://github.com/akuity/kargo/blob/v1.12.5/docs/docs/50-user-guide/60-reference-docs/30-promotion-steps/git-clone.md)

## 4. Apply the Application and promotion pipeline

Save as `fel-application.yaml` and apply with `k apply -f fel-application.yaml`.
The default AppProject must permit the source and destination; use a scoped
AppProject if your installation restricts `default`.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: fel-local
  namespace: argocd
  annotations:
    kargo.akuity.io/authorized-stage: fel-delivery:local
spec:
  project: default
  source:
    repoURL: https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab.git
    targetRevision: deploy/local
    path: deploy/environments/local
    helm:
      releaseName: fel-local
  destination:
    server: https://kubernetes.default.svc
    namespace: fel-local
  syncPolicy:
    automated:
      enabled: false
    retry:
      limit: 0
    syncOptions: [CreateNamespace=true]
```

Apply this Project first, then wait for its namespace before credentials and the
remaining resources: `k wait --for=create namespace/fel-delivery --timeout=60s`.
The Project creates the namespace; do not use the workload namespace for Kargo.

```yaml
apiVersion: kargo.akuity.io/v1alpha1
kind: Project
metadata:
  name: fel-delivery
```

Save the following as `fel-pipeline.yaml` and apply it. Auto-promotion is disabled
explicitly. Only this Stage/operator should write `deploy/local`.

```yaml
apiVersion: kargo.akuity.io/v1alpha1
kind: ProjectConfig
metadata: {name: fel-delivery, namespace: fel-delivery}
spec:
  promotionPolicies:
    - stageSelector: {name: local}
      autoPromotionEnabled: false
---
apiVersion: kargo.akuity.io/v1alpha1
kind: Warehouse
metadata: {name: fel-chart, namespace: fel-delivery}
spec:
  subscriptions:
    - chart:
        repoURL: oci://ghcr.io/wilsonhj/charts/fel
        semverConstraint: ">=0.1.0 <1.0.0"
---
apiVersion: kargo.akuity.io/v1alpha1
kind: Stage
metadata: {name: local, namespace: fel-delivery}
spec:
  requestedFreight:
    - origin: {kind: Warehouse, name: fel-chart}
      sources: {direct: true}
  promotionTemplate:
    spec:
      vars:
        - name: gitRepo
          value: https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab.git
      steps:
        - uses: git-clone
          config:
            repoURL: ${{ vars.gitRepo }}
            checkout:
              - {branch: deploy/local, create: false, path: ./out}
        - uses: helm-update-chart
          config:
            path: ./out/deploy/environments/local
            charts:
              - repository: oci://ghcr.io/wilsonhj/charts
                name: fel
                version: ${{ chartFrom('oci://ghcr.io/wilsonhj/charts/fel').Version }}
        - uses: git-commit
          config:
            path: ./out
            message: Promote FEL ${{ chartFrom('oci://ghcr.io/wilsonhj/charts/fel').Version }}
        - uses: git-push
          as: push
          config: {path: ./out, targetBranch: deploy/local}
        - uses: argocd-update
          retry: {errorThreshold: 1, timeout: 20m}
          config:
            apps:
              - name: fel-local
                namespace: argocd
                sources:
                  - repoURL: ${{ vars.gitRepo }}
                    desiredRevision: ${{ outputs.push.commit }}
                    updateTargetRevision: false
        - uses: argocd-wait
          retry: {errorThreshold: 1, timeout: 20m}
          config:
            apps:
              - name: fel-local
                namespace: argocd
                waitFor: [health, sync, operation]
```

The final pushed SHA is used because a Git push may integrate remote changes.
Argo keeps tracking the branch, while Kargo checks that exact SHA. The updater
observes the sync operation, including PostSync failure; `argocd-wait` alone
only checks health/sync/idle. Its `operation` condition is not proof of a
successful acceptance run. [Kargo updater](https://github.com/akuity/kargo/blob/v1.12.5/pkg/promotion/runner/builtin/argocd_updater.go), [waiter](https://github.com/akuity/kargo/blob/v1.12.5/docs/docs/50-user-guide/60-reference-docs/30-promotion-steps/argocd-wait.md)

## 5. Promote, preserve evidence, and retry deliberately

Select the intended Freight from `k -n fel-delivery get freight -o yaml`; use
its actual name, not a guessed chart tag. Set `FEL_FREIGHT` to that name, then:

```bash
: "${FEL_FREIGHT:?Set the reviewed Freight resource name}"
FEL_PROMOTION=$(k create -f - -o jsonpath='{.metadata.name}' <<YAML
apiVersion: kargo.akuity.io/v1alpha1
kind: Promotion
metadata: {generateName: local-, namespace: fel-delivery}
spec: {stage: local, freight: "$FEL_FREIGHT"}
YAML
)
k -n fel-delivery get promotion "$FEL_PROMOTION" -w
```

Stop watching after a terminal phase, and collect evidence **before** another
promotion/sync. Both hook Jobs use `BeforeHookCreation`, so the next run deletes
the previous Jobs and their logs. Failed Jobs have no Kubernetes retry. Argo sync
retry is disabled, and Kargo stops on the first step error with a 20-minute bound
for polling (15-minute acceptance deadline plus rollout/pull margin). Diagnose,
archive, then create a new Promotion to rerun or promote corrected Freight;
increasing retries must not hide a deterministic test failure.

```bash
FEL_EVIDENCE_DIR=$(mktemp -d)
k -n fel-delivery get promotion "$FEL_PROMOTION" -o json > "$FEL_EVIDENCE_DIR/promotion.json"
k -n argocd get application fel-local -o json > "$FEL_EVIDENCE_DIR/application.json"
k -n fel-local get jobs,pods -o yaml > "$FEL_EVIDENCE_DIR/workloads.yaml"
k -n fel-local logs job/fel-local-web-smoke -c web-smoke > "$FEL_EVIDENCE_DIR/web-smoke.log"
k -n fel-local logs job/fel-local-acceptance -c acceptance > "$FEL_EVIDENCE_DIR/acceptance.log"
k -n fel-local logs job/fel-local-acceptance -c postgres > "$FEL_EVIDENCE_DIR/postgres.log"
```

Require all of these in the archived evidence: Promotion phase `Succeeded`;
`promotion.status.state.push.commit` equals both the Application sync revision
and `operationState.syncResult.revision`; operation phase `Succeeded`; operation
info `kargo.akuity.io/promotion` equals this Promotion's name; and both named Job
entries in `syncResult.resources` have `syncPhase: PostSync` and
`hookPhase: Succeeded`. Keep their Job/Pod UIDs and logs with that revision.
If an earlier hook failed, later Jobs may not exist: retain the available logs
and events and report failure, not partial success.

Keep automatic Argo sync off and avoid manual/external syncs during promotions.
Otherwise a branch push can start a competing sync before Kargo observes it,
and later operations can overwrite the evidence being inspected. Pinned Kargo
1.12.5 starts its own operation for a different/non-Kargo promotion; do not rely
on earlier green health or assume hook observations survive a race. Full syncs
run the chart's smoke Job at wave -10 and isolated acceptance Job at wave 0.
Selective sync and `ApplyOutOfSyncOnly` are inappropriate for this acceptance
path. Helm test hooks are skipped by Argo; `tests.hookMode: argocd` is essential.
[Argo hook behavior](https://argo-cd.readthedocs.io/en/release-3.6/user-guide/sync-waves/), [Helm test-hook handling](https://argo-cd.readthedocs.io/en/release-3.6/user-guide/helm/#helm---skip-tests)

For an initial Git-only exercise, Argo can instead read `infra/helm/fel` at a
reviewed Git SHA, with registry digest/`IfNotPresent` values and
`tests.hookMode: argocd` supplied directly (without the wrapper's `fel:` prefix).
That needs no OCI chart publication. The Warehouse/Stage above specifically
promote **packaged chart versions**; do not point that Warehouse at a Git URL.
Argo's Helm renderer does not create a Helm-managed release, so use full Argo
sync and its retained hook evidence for that variant too.

## 6. Separate persistent environment configuration

For persistent/shared environments, use a new private deployment-state
repository. Keep this reusable chart, image recipes and synthetic lab with the
application. Put actual environment wrappers, cluster/controller configuration,
Argo Applications/AppProjects, Kargo promotion policies and secret references
in the private repository. This follows
[Argo CD's repository separation guidance](https://argo-cd.readthedocs.io/en/release-3.6/user-guide/best_practices/).

Bootstrap the wrapper from that private repository's own reviewed history.
Update the Application Git URL, Kargo `gitRepo` variable, credential repository
URLs and scoped AppProject together. Keep the OCI chart URLs unchanged unless
moving the registry separately. A private Git repository does not make public
images/charts private, and it is not a plaintext secret store. Use an external
secret store or an approved encrypted-secret workflow for persistent secrets.

Confirm branch protections, reviewer access, secret scanning and push
protection are available under the private repository's owner/plan before
cutover; these settings are not inherited. If the environment branch requires
PRs, use Kargo's PR promotion steps and verify the post-merge SHA instead of
granting the bot a broad bypass. Creating or migrating that repository is a
separate operation from this local example.
