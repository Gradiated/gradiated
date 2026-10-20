#!/usr/bin/env bash
set -euo pipefail
root=/var/lib/gradiated-tailscale
bin=/opt/gradiated/tailscale
config=/etc/gradiated/tailscale.json
# Tailscale SSH can open root shells only when tailscaled runs as root.
[[ "$(id -u)" == 0 ]] || exit 64
exec 9>"$root/supervisor.lock"
flock --exclusive --nonblock 9 || exit 0
umask 077
child=''
trap 'if [[ -n "$child" ]]; then kill -TERM "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true; fi; exit 0' TERM INT
# USR1 restarts tailscaled so that a staged re-authentication takes effect (nohup ignores HUP).
trap ':' USR1
while true; do
  hostname=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["hostname"])' "$config")
  proxy_port=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("proxy_port", 8888))' "$config")
  bootstrap=$(python3 -c 'import json,sys; print("true" if json.load(open(sys.argv[1])).get("bootstrap") is True else "false")' "$config")
  if [[ "$bootstrap" == true ]]; then
    [[ "$hostname" =~ ^gpu-bootstrap-[a-z0-9]{1,40}$ ]] || exit 64
  else
    [[ "$hostname" =~ ^gpu-[0-9a-f-]{36}$ ]] || exit 64
    [[ "$proxy_port" == 8888 || "$proxy_port" == 8889 ]] || exit 64
  fi
  rm -f "$root/socket"
  # --statedir gives tailscaled somewhere to keep SSH host keys; without it Tailscale SSH stays off.
  "$bin/tailscaled" --tun=userspace-networking --state="$root/state" --statedir="$root" --socket="$root/socket" --port=41641 9>&- &
  child=$!
  ready=false
  for _ in {1..30}; do
    if [[ -S "$root/socket" ]]; then ready=true; break; fi
    kill -0 "$child" 2>/dev/null || break
    sleep 1
  done
  if [[ "$ready" == true ]]; then
    # --ssh enables Tailscale SSH; the tailnet policy limits it to administrators
    # (and ops-mcp for bootstrap pods). The unprivileged control bridge keeps
    # LocalAPI access as the operator.
    args=(--hostname="$hostname" --accept-dns=false --accept-routes=false --ssh --operator=tailscale --timeout=30s)
    if [[ -f "$root/auth-key" ]]; then
      args+=(--auth-key="file:$root/auth-key")
      [[ ! -f "$root/reauth" ]] || args+=(--force-reauth)
    fi
    if ! "$bin/tailscale" --socket="$root/socket" up "${args[@]}"; then
      if [[ " ${args[*]} " == *' --force-reauth '* ]]; then
        echo 'Tailscale re-authentication failed; discarding the staged key' >&2
        rm -f "$root/auth-key" "$root/reauth"
      fi
    else
      rm -f "$root/auth-key" "$root/reauth"
      if [[ "$bootstrap" == true ]]; then
        wait "$child" || true
      elif "$bin/tailscale" --socket="$root/socket" serve --bg --tcp=8888 "tcp://127.0.0.1:$proxy_port"; then
        wait "$child" || true
      fi
    fi
  fi
  kill -TERM "$child" 2>/dev/null || true
  wait "$child" 2>/dev/null || true
  child=''
  sleep 2
done
