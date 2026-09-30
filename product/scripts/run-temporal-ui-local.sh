#!/usr/bin/env bash
set -euo pipefail

version=2.54.1
product_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_dir="${product_dir}/../.agents/runtime/temporal-ui/${version}"

case "$(uname -s)/$(uname -m)" in
  Darwin/arm64) platform=darwin_arm64; checksum=4091294aee9bed55570197a7afb401bcbf0569d0bbfb60dc2e4aec6567950355 ;;
  Darwin/x86_64) platform=darwin_amd64; checksum=983b98b56a0262481b4d855b5763c580a065a88f65a935085f50297756244c09 ;;
  Linux/aarch64|Linux/arm64) platform=linux_arm64; checksum=17a13dda159dab0861f75c5a98d0b0e732c79b5001ab276346cc72d7463c6322 ;;
  Linux/x86_64) platform=linux_amd64; checksum=6abc4e6b9400cbffa1b044edd1e68d3e369fdace32a6b2d6ad6a179bc7dfb0b0 ;;
  *) echo 'Temporal UI supports macOS and Linux on arm64 or x86_64.' >&2; exit 1 ;;
esac

runtime_dir="${runtime_dir}/${platform}"
if [[ ! -x "${runtime_dir}/ui-server" ]]; then
  mkdir -p "${runtime_dir}"
  download_dir="$(mktemp -d "${runtime_dir}/download.XXXXXX")"
  trap 'rm -rf "${download_dir}"' EXIT
  archive="ui-server_${version}_${platform}.tar.gz"
  curl --fail --silent --show-error --location --retry 3 \
    "https://github.com/temporalio/ui-server/releases/download/v${version}/${archive}" \
    --output "${download_dir}/${archive}"
  if command -v sha256sum >/dev/null 2>&1; then
    actual_checksum="$(sha256sum "${download_dir}/${archive}")"
  else
    actual_checksum="$(shasum -a 256 "${download_dir}/${archive}")"
  fi
  if [[ "${actual_checksum%% *}" != "${checksum}" ]]; then
    echo 'Temporal UI release checksum mismatch.' >&2
    exit 1
  fi
  tar -xzf "${download_dir}/${archive}" -C "${download_dir}" ui-server
  mv "${download_dir}/ui-server" "${runtime_dir}/ui-server"
  rm -rf "${download_dir}"
  trap - EXIT
fi

exec "${runtime_dir}/ui-server" --root "${product_dir}" --config scripts/temporal-ui --env development start
