#!/usr/bin/env bash
# Install pinned lab CLIs into an explicit directory, without sudo or shell edits.
set -euo pipefail
dest=${1:?Usage: bootstrap-tools.sh /absolute/path/to/bin}
[[ "$dest" = /* ]] || { echo 'Use an absolute destination.' >&2; exit 2; }
case $(uname -s) in Darwin) os=darwin ;; Linux) os=linux ;; *) exit 2 ;; esac
case $(uname -m) in arm64|aarch64) arch=arm64 ;; x86_64) arch=amd64 ;; *) exit 2 ;; esac
for cmd in curl tar shasum; do command -v "$cmd" >/dev/null; done
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$dest"
cd "$tmp"
helm_archive="helm-v3.22.1-$os-$arch.tar.gz"
curl --fail --location --retry 3 -o "$helm_archive" "https://get.helm.sh/$helm_archive"
curl --fail --location --retry 3 -o helm.sha256 "https://get.helm.sh/$helm_archive.sha256sum"
shasum -a 256 -c helm.sha256
tar -xzf "$helm_archive"
install -m 755 "$os-$arch/helm" "$dest/helm"
kind_binary="kind-$os-$arch"
kind_url="https://github.com/kubernetes-sigs/kind/releases/download/v0.33.0/$kind_binary"
curl --fail --location --retry 3 -o "$kind_binary" "$kind_url"
curl --fail --location --retry 3 -o kind.sha256 "$kind_url.sha256sum"
shasum -a 256 -c kind.sha256
install -m 755 "$kind_binary" "$dest/kind"
kubectl_url="https://dl.k8s.io/release/v1.37.0/bin/$os/$arch/kubectl"
curl --fail --location --retry 3 -o kubectl "$kubectl_url"
curl --fail --location --retry 3 -o kubectl.sha256 "$kubectl_url.sha256"
printf '%s  kubectl\n' "$(cat kubectl.sha256)" | shasum -a 256 -c -
install -m 755 kubectl "$dest/kubectl"
"$dest/helm" version --short
"$dest/kind" version
"$dest/kubectl" version --client
