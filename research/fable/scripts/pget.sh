#!/bin/zsh
# Parallel-range downloader: beats per-connection throttling by splitting the
# file into N ranges fetched concurrently, then concatenating.
# Usage: pget.sh <url> <output> [num_connections]
set -euo pipefail
URL="$1"; OUT="$2"; N="${3:-16}"
FINAL=$(curl -sIL -o /dev/null -w '%{url_effective}' "$URL")
LEN=$(curl -sIL "$FINAL" | grep -i '^content-length' | tail -1 | tr -dc '0-9')
if [[ -z "$LEN" || "$LEN" -eq 0 ]]; then echo "no content-length for $URL" >&2; exit 1; fi
echo "downloading $LEN bytes in $N parts -> $OUT"
CHUNK=$(( (LEN + N - 1) / N ))
TMP="$OUT.parts"
mkdir -p "$TMP"
pids=()
for i in $(seq 0 $((N-1))); do
  START=$(( i * CHUNK ))
  END=$(( START + CHUNK - 1 ))
  (( END >= LEN )) && END=$(( LEN - 1 ))
  (( START >= LEN )) && break
  ( for attempt in 1 2 3 4 5; do
      have=0
      [[ -f "$TMP/p$i" ]] && have=$(stat -f%z "$TMP/p$i")
      want=$(( END - START + 1 ))
      (( have == want )) && exit 0
      curl -s --retry 3 -r $(( START + have ))-$END -o "$TMP/p$i.new" "$FINAL" || true
      if [[ -f "$TMP/p$i.new" ]]; then cat "$TMP/p$i.new" >> "$TMP/p$i"; rm -f "$TMP/p$i.new"; fi
    done
    have=0; [[ -f "$TMP/p$i" ]] && have=$(stat -f%z "$TMP/p$i")
    (( have == END - START + 1 )) || { echo "part $i incomplete: $have" >&2; exit 1; } ) &
  pids+=($!)
done
fail=0
for p in "${pids[@]}"; do wait "$p" || fail=1; done
(( fail )) && { echo "FAILED: some parts incomplete" >&2; exit 1; }
cat "$TMP"/p*(n) > "$OUT"
GOT=$(stat -f%z "$OUT")
if [[ "$GOT" -ne "$LEN" ]]; then echo "SIZE MISMATCH: got $GOT want $LEN" >&2; exit 1; fi
rm -rf "$TMP"
echo "OK: $OUT ($GOT bytes)"
