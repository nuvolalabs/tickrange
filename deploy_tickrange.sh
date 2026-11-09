#!/usr/bin/env bash
# Redeploy tickrange to the three containers and (re)start the live services.
set -e
KEY=~/.ssh/tickrange_ed25519
BASE=/var/lib/hermes/.hermes/profiles/teddy/home/trading/tickrange/app
SSH="ssh -n -i $KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes"
SCPF="scp -P 2222 -i $KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
SCPM="scp -P 2223 -i $KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

echo "[frontend] sync + restart vite"
$SCPF -r "$BASE/frontend/." root@127.0.0.1:/workspace/
$SSH -p 2222 root@127.0.0.1 'cd /workspace && npm install --no-audit --no-fund >/dev/null 2>&1; tmux kill-session -t vite 2>/dev/null; tmux new-session -d -s vite "cd /workspace && npm run dev 2>&1 | tee /tmp/vite.log"'

echo "[midware] sync + restart uvicorn"
$SCPM -r "$BASE/midware/." root@127.0.0.1:/workspace/
$SSH -p 2223 root@127.0.0.1 'cd /workspace && .venv/bin/pip install -q -r requirements.txt; tmux kill-session -t midware 2>/dev/null; tmux new-session -d -s midware "set -a; . /workspace/.env; set +a; cd /workspace && exec .venv/bin/uvicorn app.server:app --host 0.0.0.0 --port 8765 2>&1 | tee /tmp/midware.log"'

echo "deployed."
echo "  frontend  http://localhost:5173"
echo "  midware   http://localhost:8765/health"
