#!/usr/bin/env bash
set -euo pipefail
: "${PUBLIC_KEY:?A public SSH key is required for enrollment}"
install -d -m 700 /root/.ssh
printf '%s\n' "$PUBLIC_KEY" >/root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
unset PUBLIC_KEY GRADIATED_GPU_BOOTSTRAP
ssh-keygen -A
install -d /run/gradiated
: >/run/gradiated/host-init
/usr/sbin/sshd -D -e &
ssh_pid=$!
host_pid=''
stop() {
  trap - TERM INT EXIT
  kill -TERM "$ssh_pid" 2>/dev/null || true
  if [[ -n "$host_pid" ]]; then kill -TERM "$host_pid" 2>/dev/null || true; fi
  wait || true
}
trap stop TERM INT EXIT
while kill -0 "$ssh_pid" 2>/dev/null; do
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
wait "$ssh_pid"
