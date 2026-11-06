#!/usr/bin/env bash

set -euo pipefail

base_image="gitea/runner-images@sha256:e77e2b1ebba51adb1c59d8eb185bc54e397b7e22442756aa7ea0e7b841fd2906"
target_image="samuel/ci-python:20260827-3"
stage_dir="$(mktemp -d)"

cleanup() {
  rm -rf -- "$stage_dir"
}
trap cleanup EXIT

for command_name in curl docker sha256sum; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "required command is missing: $command_name" >&2
    exit 1
  fi
done

if docker image inspect "$target_image" >/dev/null 2>&1; then
  echo "refusing to replace existing image: $target_image" >&2
  exit 1
fi
base_platform="$(docker image inspect "$base_image" --format '{{.Os}}/{{.Architecture}}')"
if [[ "$base_platform" != "linux/amd64" ]]; then
  echo "unexpected base image platform: $base_platform" >&2
  exit 1
fi

download_runtime() {
  local version="$1"
  local release="$2"
  local expected_sha256="$3"
  local filename="python-$version-linux-24.04-x64.tar.gz"
  local archive="$stage_dir/$filename"
  local url="https://github.com/actions/python-versions/releases/download/$release/$filename"

  curl --fail --location --retry 2 --connect-timeout 10 --max-time 900 \
    "$url" --output "$archive"
  printf '%s  %s\n' "$expected_sha256" "$archive" | sha256sum --check --strict
}

download_runtime \
  "3.10.21" \
  "3.10.21-31661269155" \
  "3ae6d012a8c2cb41bf7a2957a99f1d6d329a264a727053e71edb76b1cfda6f52"
download_runtime \
  "3.12.14" \
  "3.12.14-31661455385" \
  "5a03168292516f6dd6dcf630f4bf5369b108abd7c699a7e1db37f1e622257fff"
download_runtime \
  "3.14.7" \
  "3.14.7-31064857500" \
  "76d5ddab6d2dd89a39c06220f6efeda486a48ed481eae97bfc596c74ac3623db"

pip_wheel="$stage_dir/pip-26.2.1-py3-none-any.whl"
curl --fail --location --retry 2 --connect-timeout 10 --max-time 300 \
  "https://files.pythonhosted.org/packages/f3/6e/1736e5b4ae2b778ef2f81c47d797de9f891d4d8acb047a24ca37a60294dd/pip-26.2.1-py3-none-any.whl" \
  --output "$pip_wheel"
printf '%s  %s\n' \
  "71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e" \
  "$pip_wheel" | sha256sum --check --strict

docker build --pull=false --no-cache \
  --label "org.opencontainers.image.title=S.A.M.U.E.L. CI Python image" \
  --label "org.opencontainers.image.base.digest=sha256:e77e2b1ebba51adb1c59d8eb185bc54e397b7e22442756aa7ea0e7b841fd2906" \
  --label "org.opencontainers.image.version=20260827-3" \
  --tag "$target_image" \
  --file - "$stage_dir" <<'DOCKERFILE'
FROM gitea/runner-images@sha256:e77e2b1ebba51adb1c59d8eb185bc54e397b7e22442756aa7ea0e7b841fd2906

COPY python-*.tar.gz /tmp/python-archives/
COPY pip-26.2.1-py3-none-any.whl /opt/hostedtoolcache/pip/

RUN set -eu; \
    install_runtime() { \
      version="$1"; \
      major="${version%%.*}"; \
      minor_patch="${version#*.}"; \
      minor="${minor_patch%%.*}"; \
      archive="/tmp/python-archives/python-$version-linux-24.04-x64.tar.gz"; \
      payload="/tmp/python-$version"; \
      version_root="/opt/hostedtoolcache/Python/$version"; \
      target="$version_root/x64"; \
      test ! -e "$version_root"; \
      mkdir -p "$payload" "$target"; \
      tar -xzf "$archive" -C "$payload"; \
      cp -a "$payload"/. "$target"/; \
      rm "$target/setup.sh"; \
      ln -s "./bin/python$major.$minor" "$target/python"; \
      ln -s "python$major.$minor" "$target/bin/python$major$minor"; \
      if test ! -e "$target/bin/python"; then ln -s "python$major.$minor" "$target/bin/python"; fi; \
      chmod +x "$target/python" "$target/bin/python$major" \
        "$target/bin/python$major.$minor" "$target/bin/python$major$minor" "$target/bin/python"; \
      test "$("$target/bin/python" --version)" = "Python $version"; \
      "$target/bin/python" -m pip install --disable-pip-version-check --no-index \
        /opt/hostedtoolcache/pip/pip-26.2.1-py3-none-any.whl; \
      test "$("$target/bin/python" -c 'import importlib.metadata; print(importlib.metadata.version("pip"))')" = "26.2.1"; \
      touch "$version_root/x64.complete"; \
      rm -rf "$payload"; \
    }; \
    install_runtime 3.10.21; \
    install_runtime 3.12.14; \
    install_runtime 3.14.7; \
    rm -rf /tmp/python-archives
DOCKERFILE

image_id="$(docker image inspect "$target_image" --format '{{.Id}}')"
image_platform="$(docker image inspect "$image_id" --format '{{.Os}}/{{.Architecture}}')"
image_base_digest="$(
  docker image inspect "$image_id" \
    --format '{{index .Config.Labels "org.opencontainers.image.base.digest"}}'
)"
test "$image_platform" = "linux/amd64"
test "$image_base_digest" = \
  "sha256:e77e2b1ebba51adb1c59d8eb185bc54e397b7e22442756aa7ea0e7b841fd2906"
docker run --rm --pull=never "$image_id" bash -ceu '
  for version in 3.10.21 3.12.14 3.14.7; do
    root="/opt/hostedtoolcache/Python/$version"
    test -f "$root/x64.complete"
    test -x "$root/x64/bin/python"
    test "$("$root/x64/bin/python" --version)" = "Python $version"
    test "$("$root/x64/bin/python" -c '\''import importlib.metadata; print(importlib.metadata.version("pip"))'\'')" = "26.2.1"
  done
  printf "%s  %s\n" \
    "71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e" \
    "/opt/hostedtoolcache/pip/pip-26.2.1-py3-none-any.whl" | sha256sum --check --strict
  test ! -S /var/run/docker.sock
  touch /opt/hostedtoolcache/container-local-write-test
'
docker run --rm --pull=never "$image_id" \
  test ! -e /opt/hostedtoolcache/container-local-write-test

echo "built and verified image: $target_image"
echo "image id: $image_id"
echo "image platform: $image_platform"
echo "base digest label: $image_base_digest"
echo "bind the runner label to the image id, never to the mutable local tag"
