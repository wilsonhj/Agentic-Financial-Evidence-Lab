#!/usr/bin/env bash
# Disposable TLS OCI registry for the owned kind lab. No public listener/auth token.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
state=${FEL_LAB_STATE:?Set the owned lab state directory}
cluster=${FEL_LAB_CLUSTER:-fel-helm-lab}
port=${FEL_REGISTRY_PORT:-55439}
[[ "$port" =~ ^[1-9][0-9]{0,4}$ ]] && (( port <= 65535 )) || exit 2
bash "$root/infra/kubernetes/lab.sh" status >/dev/null
name="$cluster-registry"
node="$cluster-control-plane"
directory="$state/registry"
host=registry.fel-registry.svc.cluster.local
image='registry:3@sha256:82f6ff4a7f982960c8aa51617fea3aabc485df6e55cce80d22deb1de36f1bc3c'
k() { kubectl --kubeconfig "$state/kubeconfig" --context "kind-$cluster" "$@"; }
case ${1:-help} in
  create)
    [[ ! -e "$directory" ]] || { echo 'Registry state already exists; inspect it before retrying.' >&2; exit 2; }
    if docker inspect "$name" >/dev/null 2>&1; then
      echo 'Registry container name already exists; refusing to replace it.' >&2; exit 2
    fi
    existing_namespace=$(k get namespace fel-registry --ignore-not-found=true -o name --request-timeout=15s)
    if [[ -n "$existing_namespace" ]]; then
      echo 'Registry namespace already exists; refusing to adopt it.' >&2; exit 2
    fi
    umask 077
    mkdir -p "$directory/tls" "$directory/data"
    cat > "$directory/tls/openssl.cnf" <<EOF
[req]
distinguished_name=dn
x509_extensions=ext
prompt=no
[dn]
CN=FEL disposable local registry
[ext]
basicConstraints=critical,CA:TRUE
keyUsage=critical,digitalSignature,keyEncipherment,keyCertSign
extendedKeyUsage=serverAuth
subjectAltName=DNS:$host,DNS:$name,DNS:localhost,IP:127.0.0.1
EOF
    openssl req -x509 -newkey rsa:2048 -nodes -days 7 \
      -config "$directory/tls/openssl.cnf" \
      -keyout "$directory/tls/server.key" -out "$directory/tls/ca.crt" \
      2> "$directory/tls/generation.log"
    docker run -d --name "$name" --network kind \
      --label "org.fel.lab=$cluster" --cpus 0.5 --memory 256m \
      -p "127.0.0.1:$port:5000" \
      -v "$directory/data:/var/lib/registry" -v "$directory/tls:/tls:ro" \
      -e REGISTRY_HTTP_TLS_CERTIFICATE=/tls/ca.crt \
      -e REGISTRY_HTTP_TLS_KEY=/tls/server.key "$image" > "$directory/container-id"
    address=$(docker inspect --format '{{(index .NetworkSettings.Networks "kind").IPAddress}}' "$name")
    [[ "$address" =~ ^[0-9.]+$ ]] || { echo 'Expected IPv4 kind network.' >&2; exit 2; }
    k create namespace fel-registry -o jsonpath='{.metadata.uid}' > "$directory/namespace-uid"
    k apply -f - <<EOF
apiVersion: v1
kind: Service
metadata: {name: registry, namespace: fel-registry}
spec:
  ports: [{name: https, port: 5000, targetPort: 5000}]
---
apiVersion: discovery.k8s.io/v1
kind: EndpointSlice
metadata:
  name: fel-local-registry
  namespace: fel-registry
  labels: {kubernetes.io/service-name: registry}
addressType: IPv4
ports: [{name: https, protocol: TCP, port: 5000}]
endpoints:
  - addresses: ["$address"]
EOF
    # Kubelets resolve the registry via Docker networking; controllers use the
    # ClusterIP Service. Both names are covered by the same trusted certificate.
    certdir="/etc/containerd/certs.d/$host:5000"
    docker exec "$node" mkdir -p "$certdir"
    docker cp "$directory/tls/ca.crt" "$node:$certdir/ca.crt"
    docker exec -i "$node" tee "$certdir/hosts.toml" >/dev/null <<EOF
server = "https://$name:5000"
[host."https://$name:5000"]
  capabilities = ["pull", "resolve"]
  ca = "$certdir/ca.crt"
EOF
    for attempt in {1..30}; do
      if curl --silent --fail --cacert "$directory/tls/ca.crt" "https://localhost:$port/v2/" >/dev/null; then
        printf 'Publisher: localhost:%s\nCluster: %s:5000\nCA file: %s/tls/ca.crt\n' "$port" "$host" "$directory"
        exit 0
      fi
      sleep 1
    done
    echo 'Registry did not become ready.' >&2; exit 1
    ;;
  delete)
    [[ -s "$directory/container-id" ]] || exit 2
    recorded_container=$(cat "$directory/container-id")
    recorded_namespace=
    if [[ -f "$directory/namespace-uid" ]]; then
      recorded_namespace=$(cat "$directory/namespace-uid")
    fi
    [[ "$recorded_container" =~ ^[0-9a-f]{64}$ ]] || exit 2
    [[ -z "$recorded_namespace" || "$recorded_namespace" =~ ^[0-9a-f-]{36}$ ]] || exit 2
    # Successful empty queries mean absent. Docker/API failures must stop before
    # deletion; a partially completed cleanup can then resume with its records.
    actual=$(docker container ls --all --no-trunc --filter "name=^/$name$" --format '{{.ID}}')
    [[ -z "$actual" || "$actual" = "$recorded_container" ]] || exit 2
    namespace_uid=$(k get namespace fel-registry --ignore-not-found=true -o jsonpath='{.metadata.uid}' --request-timeout=15s)
    if [[ -n "$recorded_namespace" ]]; then
      [[ -z "$namespace_uid" || "$namespace_uid" = "$recorded_namespace" ]] || exit 2
    fi
    if [[ -n "$actual" ]]; then
      # An ID target cannot remove a same-name replacement after the check.
      docker rm -f "$recorded_container"
    fi
    if [[ -z "$recorded_namespace" && -n "$namespace_uid" ]]; then
      # A failed create response might have created this namespace, but gives
      # us no proof. Remove only known-owned resources, retain diagnostic state.
      rm -f "$directory/tls/server.key"
      echo 'Owned registry container and TLS key removed; namespace has no recorded UID and is preserved for operator inspection.' >&2
      exit 2
    fi
    if [[ -n "$namespace_uid" ]]; then
      # kubectl's normal name-based delete has no UID precondition. Send one
      # through the raw API so a racing replacement namespace is preserved.
      printf '{"apiVersion":"v1","kind":"DeleteOptions","preconditions":{"uid":"%s"}}\n' "$recorded_namespace" |
        k delete --raw /api/v1/namespaces/fel-registry -f - --request-timeout=15s
      k wait --for=delete namespace/fel-registry --timeout=60s --request-timeout=70s
    fi
    # Keep published artifacts for inspection, erase only this lab's TLS key.
    rm -f "$directory/tls/server.key" "$directory/container-id" "$directory/namespace-uid"
    ;;
  *) echo 'Usage: local-registry.sh create|delete' >&2; exit 2 ;;
esac
