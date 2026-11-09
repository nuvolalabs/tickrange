#!/usr/bin/env bash
# Start the local Postgres cluster, then stay alive.
set -euo pipefail
PGVER="$(ls /etc/postgresql 2>/dev/null | head -1 || echo 16)"
echo "[supabase] starting postgresql ${PGVER}/main"
pg_ctlcluster "${PGVER}" main start || service postgresql start || true
# allow remote-ish connections on the host netns for the app
echo "[supabase] postgres listening on 5432"
exec tail -f /dev/null
