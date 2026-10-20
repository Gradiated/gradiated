#!/usr/bin/env bash
set -euo pipefail
# GPU hosts have no public SSH. Shell access is Tailscale SSH, limited to
# administrators by the tailnet policy. OpenSSH starts only for documented
# break-glass recovery: GRADIATED_BREAK_GLASS_SSH=1 plus PUBLIC_KEY and an
# exposed TCP 22, which requires a provider configuration change.
bootstrap_key=${GRADIATED_TAILSCALE_BOOTSTRAP_KEY:-}
break_glass=${GRADIATED_BREAK_GLASS_SSH:-}
public_key=${PUBLIC_KEY:-}
pod=${RUNPOD_POD_ID:-}
unset GRADIATED_TAILSCALE_BOOTSTRAP_KEY GRADIATED_BREAK_GLASS_SSH PUBLIC_KEY GRADIATED_GPU_BOOTSTRAP
install -d /run/gradiated
: >/run/gradiated/host-init
state=/var/lib/gradiated-tailscale

ssh_pid=''
if [[ "$break_glass" == 1 && -n "$public_key" ]]; then
  echo 'Break-glass OpenSSH is enabled for this container start.' >&2
  install -d -m 700 /root/.ssh
  printf '%s\n' "$public_key" >/root/.ssh/authorized_keys
  chmod 600 /root/.ssh/authorized_keys
  ssh-keygen -A
  /usr/sbin/sshd -D -e &
  ssh_pid=$!
else
  rm -f /root/.ssh/authorized_keys
fi

# First start: join the tailnet as an unenrolled tag:gpu-bootstrap pod using the
# single-use key from the RunPod secret. Enrollment later re-authenticates the
# pod as tag:gpu-inference. A saved identity is never replaced here.
if [[ ! -f /etc/gradiated/tailscale.json && ! -e "$state/state" ]]; then
  if [[ "$bootstrap_key" == tskey-auth-* && "$pod" =~ ^[a-z0-9]{1,40}$ ]]; then
    install -d -m 700 -o tailscale -g tailscale "$state"
    (umask 077; printf '%s' "$bootstrap_key" >"$state/auth-key")
    printf '{"hostname":"gpu-bootstrap-%s","bootstrap":true}\n' "$pod" >/etc/gradiated/tailscale.json
    chmod 600 /etc/gradiated/tailscale.json
    touch /var/log/gradiated-tailscale.log
    chmod 600 /var/log/gradiated-tailscale.log
  else
    echo 'GPU enrollment requires GRADIATED_TAILSCALE_BOOTSTRAP_KEY from a RunPod secret.' >&2
  fi
fi
bootstrap_key=''

host_pid=''
stop() {
  trap - TERM INT EXIT
  if [[ -n "$ssh_pid" ]]; then kill -TERM "$ssh_pid" 2>/dev/null || true; fi
  if [[ -n "$host_pid" ]]; then kill -TERM "$host_pid" 2>/dev/null || true; fi
  wait || true
}
trap 'stop; exit 0' TERM INT
trap stop EXIT
tick=0
while true; do
  if [[ -n "$ssh_pid" ]] && ! kill -0 "$ssh_pid" 2>/dev/null; then
    wait "$ssh_pid" || true
    /usr/sbin/sshd -D -e &
    ssh_pid=$!
  fi
  # Tailscale is the only shell access path; restart its supervisor if it exits.
  if ((tick % 15 == 0)) && [[ -f /etc/gradiated/tailscale.json ]]; then
    bash /opt/gradiated/bin/start-tailscale || true
  fi
  tick=$((tick + 1))
  if [[ -f /etc/gradiated/kubelet.json && -f /opt/gradiated/kubelet/launch-ready ]]; then
    if [[ -z "$host_pid" ]] || ! kill -0 "$host_pid" 2>/dev/null; then
      if [[ -n "$host_pid" ]]; then wait "$host_pid" || true; fi
      env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
        python3 -B /opt/gradiated/kubelet/bootstrap.py &
      host_pid=$!
    fi
  fi
  sleep 2 &
  wait $! || true
done
