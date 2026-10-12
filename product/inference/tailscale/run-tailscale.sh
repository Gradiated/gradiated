#!/usr/bin/env bash
set -euo pipefail
root=/var/lib/gradiated-tailscale
bin=/opt/gradiated/tailscale
hostname=$(python3 -c 'import json; print(json.load(open("/etc/gradiated/tailscale.json"))["hostname"])')
proxy_port=$(python3 -c 'import json; print(json.load(open("/etc/gradiated/tailscale.json")).get("proxy_port", 8888))')
[[ "$hostname" =~ ^gpu-[0-9a-f-]{36}$ ]] || exit 64
[[ "$proxy_port" == 8888 || "$proxy_port" == 8889 ]] || exit 64
umask 077
child=''
trap 'if [[ -n "$child" ]]; then kill -TERM "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true; fi; exit 0' TERM INT
while true; do
  rm -f "$root/socket"
  "$bin/tailscaled" --tun=userspace-networking --state="$root/state" --socket="$root/socket" --port=41641 &
  child=$!
  ready=false
  for _ in {1..30}; do
    if [[ -S "$root/socket" ]]; then ready=true; break; fi
    kill -0 "$child" 2>/dev/null || break
    sleep 1
  done
  if [[ "$ready" == true ]]; then
    args=(--hostname="$hostname" --accept-dns=false --accept-routes=false --timeout=30s)
    [[ ! -f "$root/auth-key" ]] || args+=(--auth-key="file:$root/auth-key")
    if "$bin/tailscale" --socket="$root/socket" up "${args[@]}"; then
      rm -f "$root/auth-key"
      if "$bin/tailscale" --socket="$root/socket" serve --bg --tcp=8888 "tcp://127.0.0.1:$proxy_port"; then
        wait "$child" || true
      fi
    fi
  fi
  kill -TERM "$child" 2>/dev/null || true
  wait "$child" 2>/dev/null || true
  child=''
  sleep 2
done
