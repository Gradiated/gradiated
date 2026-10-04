#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
credentials=${1:?Pass the private artifact credential file}
[[ $(id -u) == 0 ]] || {
  echo 'Host tools require root' >&2
  exit 1
}
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || {
  echo 'Unsupported host OS' >&2
  exit 1
}
[[ $(uname -m) == x86_64 ]] || {
  echo 'Unsupported host architecture' >&2
  exit 1
}
for user in runtime downloader desmond; do id "$user" >/dev/null; done
for binary in runtime-launch desmondd bsdtar curl; do
  dependencies=$(ldd "$root/bin/$binary")
  [[ "$dependencies" != *'not found'* ]] || {
    echo "Missing libraries for $binary" >&2
    exit 1
  }
done
"$root/bin/s5cmd" version >/dev/null
"$root/bin/curl" --version >/dev/null
bash -n "$root/bin/fetch-runtime" "$root/bin/start-desmond"
[[ -s /etc/gradiated/runtime-access.token ]] || {
  echo 'Serving enrollment is missing' >&2
  exit 1
}
[[ -s "$credentials" ]] || {
  echo 'Artifact enrollment is missing' >&2
  exit 1
}
runuser -u runtime -- mkdir -p /home/runtime/.cache/huggingface
runuser -u runtime -- test -w /home/runtime/.cache/huggingface

install -d /opt/gradiated/bin /etc/gradiated
install -d -m 700 -o downloader -g downloader /var/cache/gradiated/runtime-bundles
for binary in s5cmd bsdtar curl; do
  install -m 755 "$root/bin/$binary" "/usr/local/bin/$binary.new"
  mv -f "/usr/local/bin/$binary.new" "/usr/local/bin/$binary"
done
for binary in runtime-launch desmondd download-runtime fetch-runtime start-desmond; do
  install -m 755 "$root/bin/$binary" "/opt/gradiated/bin/$binary.new"
  mv -f "/opt/gradiated/bin/$binary.new" "/opt/gradiated/bin/$binary"
done
if [[ ! "$credentials" -ef /etc/gradiated/artifact.env ]]; then
  install -o downloader -g downloader -m 600 "$credentials" /etc/gradiated/artifact.env
fi
chown downloader:downloader /etc/gradiated/artifact.env
chmod 600 /etc/gradiated/artifact.env
umask 077
token=$(cat /etc/gradiated/runtime-access.token)
[[ "$token" =~ ^[A-Za-z0-9_-]{32,256}$ ]] || {
  echo 'Invalid serving token' >&2
  exit 1
}
printf '"Bearer %s" 1;\n' "$token" >/etc/gradiated/runtime-proxy-auth.conf
chown desmond:desmond /etc/gradiated/runtime-proxy-auth.conf
chmod 600 /etc/gradiated/runtime-proxy-auth.conf
printf 'Host tools installed for %s; running workloads were not restarted\n' "$(cat "$root/base-id")"
