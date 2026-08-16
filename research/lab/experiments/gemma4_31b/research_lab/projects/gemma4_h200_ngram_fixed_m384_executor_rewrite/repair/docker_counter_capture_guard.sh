#!/bin/sh
set -eu

report=/home/glmrunner/gemma4-fixed-m384-executor/artifacts/mixed-local-m384-20260725t165205Z/counters/fixed-m384-attention.ncu-rep
expected=5bb0ef1d4f449ef8931ebf62006b86a572a970058d4a945732959c3322f8bc1c
log=/home/glmrunner/gemma4-fixed-m384-executor/artifacts/mixed-local-m384-20260725t165205Z/counters/CAPTURE_REUSE_GUARD.log

case " $* " in
  *" --export /work/artifacts/counters/fixed-m384-attention "*)
    observed=$(sha256sum "$report" | cut -d' ' -f1)
    test "$observed" = "$expected"
    printf '%s\n' "preserved completed NCU producer $observed; capture replay suppressed" >>"$log"
    exit 0
    ;;
esac

exec /usr/bin/docker "$@"
