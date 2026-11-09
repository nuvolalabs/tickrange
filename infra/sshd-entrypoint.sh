#!/usr/bin/env bash
# Shared entrypoint: start sshd on $SSH_PORT, then run CMD (or stay alive).
set -euo pipefail
PORT="${SSH_PORT:-22}"
mkdir -p /run/sshd
ssh-keygen -A >/dev/null 2>&1 || true

if grep -qE '^[[:space:]]*#?[[:space:]]*Port[[:space:]]' /etc/ssh/sshd_config; then
  sed -i -E "s/^[[:space:]]*#?[[:space:]]*Port[[:space:]].*/Port ${PORT}/" /etc/ssh/sshd_config
else
  echo "Port ${PORT}" >> /etc/ssh/sshd_config
fi

/usr/sbin/sshd
echo "[entrypoint] sshd listening on port ${PORT}"
if [ "$#" -gt 0 ]; then
  exec "$@"
else
  exec tail -f /dev/null
fi
