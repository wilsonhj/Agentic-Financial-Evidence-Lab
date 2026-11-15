#!/usr/bin/env bash
# Optional disposable kind lab. Every Kubernetes call names its own kubeconfig.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
action=${1:-help}
state=${FEL_LAB_STATE:-${TMPDIR:-/tmp}/fel-helm-lab}
cluster=${FEL_LAB_CLUSTER:-fel-helm-lab}
port=${FEL_LAB_PORT:-3000}
[[ "$port" =~ ^[1-9][0-9]{0,4}$ ]] && (( port <= 65535 )) || {
  echo 'FEL_LAB_PORT must be a TCP port from 1 to 65535.' >&2; exit 2;
}
[[ "$state" = /* && "$cluster" =~ ^fel-[a-z0-9-]+$ ]] || {
  echo 'Use an absolute FEL_LAB_STATE and a cluster name starting fel-.' >&2; exit 2;
}
config="$state/kubeconfig"
chart="$root/infra/helm/fel"
namespace=fel-lab
release=fel-lab
tag=${FEL_IMAGE_TAG:-$(git -C "$root" rev-parse --short=12 HEAD)}
[[ "$tag" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]*$ ]] || exit 2
web="fel-web-fixture:$tag"
runner="fel-acceptance:$tag"
node='kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5'
kube() { kubectl --kubeconfig "$config" --context "kind-$cluster" "$@"; }
helm_lab() { helm --kubeconfig "$config" --kube-context "kind-$cluster" "$@"; }
need() { for tool in "$@"; do command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 2; }; done; }
owned() {
  need docker
  [[ -f "$state/owner" && $(cat "$state/owner") = "$cluster" && -f "$config" && -f "$state/node-id" ]] || {
    echo 'No matching lab ownership record. Run create first.' >&2; exit 2;
  }
  actual_node=$(docker inspect --format '{{.Id}}' "$cluster-control-plane" 2>/dev/null) || {
    echo 'Recorded lab container is absent from this Docker engine.' >&2; exit 2;
  }
  [[ "$actual_node" = "$(cat "$state/node-id")" ]] || {
    echo 'Cluster identity changed. Refusing to operate on its replacement.' >&2; exit 2;
  }
}
case "$action" in
  doctor)
    need docker kind helm kubectl
    docker info --format 'Docker {{.ServerVersion}}, CPUs {{.NCPU}}, bytes RAM {{.MemTotal}}'
    kind version
    helm version --short
    kubectl version --client
    printf 'Isolated cluster: %s\nState directory: %s\nImage tag: %s\n' "$cluster" "$state" "$tag"
    ;;
  build)
    need docker git
    # Tags identify a source commit. Commit deliberate local edits before building.
    [[ -z $(git -C "$root" status --porcelain --untracked-files=normal) ]] || {
      echo 'Build from a clean checkout so image tags identify the tested source.' >&2; exit 2;
    }
    source_sha=$(git -C "$root" rev-parse HEAD)
    docker build --build-arg "SOURCE_SHA=$source_sha" -f "$root/infra/kubernetes/images/web-fixture.Dockerfile" -t "$web" "$root"
    docker build --build-arg "SOURCE_SHA=$source_sha" -f "$root/infra/kubernetes/images/acceptance.Dockerfile" -t "$runner" "$root"
    ;;
  create)
    need docker kind
    mkdir -p "$state"
    chmod 700 "$state"
    [[ ! -e "$state/owner" && ! -e "$config" ]] || { echo 'Lab state exists. Use status.' >&2; exit 2; }
    ! kind get clusters | grep -Fxq "$cluster" || { echo 'Cluster name already exists; choose another FEL_LAB_CLUSTER.' >&2; exit 2; }
    kind create cluster --name "$cluster" --image "$node" --kubeconfig "$config" --wait 180s
    docker inspect --format '{{.Id}}' "$cluster-control-plane" > "$state/node-id"
    printf '%s\n' "$cluster" > "$state/owner"
    ;;
  deploy)
    need docker kind helm kubectl
    owned
    kind load docker-image "$web" "$runner" --name "$cluster"
    helm lint "$chart" --strict
    helm_lab upgrade --install "$release" "$chart" --namespace "$namespace" --create-namespace \
      --set-string "web.image.tag=$tag" --set-string "acceptance.image.tag=$tag" \
      --wait --timeout 5m
    ;;
  test)
    need helm kubectl
    owned
    mkdir -p "$state/evidence"
    # Helm test launches a fresh DB/API/worker/browser stack in its own Job.
    # This is separate from the interactive fixture Deployment's health probe.
    set +e
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    helm_lab test "$release" -n "$namespace" --timeout 16m 2>&1 | tee "$state/evidence/helm-test-$stamp.log"
    result=${PIPESTATUS[0]}
    set -e
    # Helm 3 --logs looks up hook names as Pods; these hooks are Jobs.
    for entry in web-smoke:web-smoke acceptance:acceptance acceptance:postgres; do
      job=${entry%%:*}
      container=${entry##*:}
      kube -n "$namespace" logs "job/$release-$job" -c "$container" \
        > "$state/evidence/$job-$container-$stamp.log" 2>&1 || true
    done
    kube -n "$namespace" get pods,jobs -o wide > "$state/evidence/workloads-$stamp.txt"
    kube -n "$namespace" get events --sort-by=.metadata.creationTimestamp > "$state/evidence/events-$stamp.txt"
    exit "$result"
    ;;
  status)
    need kubectl
    owned
    kube -n "$namespace" get deployments,services,pods,jobs
    ;;
  open)
    need kubectl
    owned
    # Loopback only. Stop with Ctrl-C.
    kube -n "$namespace" port-forward "service/$release-web" "$port:3000" --address 127.0.0.1
    ;;
  delete)
    need kind
    owned
    kind delete cluster --name "$cluster" --kubeconfig "$config"
    rm -f "$state/owner" "$state/node-id" "$config"
    echo "Deleted $cluster. Evidence remains in $state/evidence."
    ;;
  *)
    echo 'Usage: lab.sh doctor|build|create|deploy|test|status|open|delete'
    ;;
esac
