#!/usr/bin/env bash
# Keeps a reverse tunnel open so fbf8's 127.0.0.1:18777 reaches the Codex judge relay on this machine.
while true; do
  ssh -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
      -N -R 127.0.0.1:18777:127.0.0.1:18777 root@100.106.163.119
  sleep 10
done
