#!/usr/bin/env bash
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
build_dir=${TMPDIR:-/tmp}/gradiated-desmond-build

cmake -S "$repo_root/product/inference" -B "$build_dir" -DCMAKE_BUILD_TYPE=Debug
cmake --build "$build_dir" --target desmondd desmond_tests -j
(cd "$build_dir" && ctest -R desmond --output-on-failure)
