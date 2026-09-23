#!/bin/sh
set -eu
# shellcheck disable=SC2016
test "$1" = 'literal $(false)'
test -f "$GRADIATED_RUNTIME_ROOT/base-id"
printf 'runtime fixture passed\n'
