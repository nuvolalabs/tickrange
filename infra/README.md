# tickrange infra — three host-networked boxes

Containers: `frontend` (Node 20), `midware` (Python 3), `supabase` (PostgreSQL 16),
all on `--network host`, each running an sshd on a UNIQUE port:

| name     | sshd port | toolchain               |
|----------|-----------|-------------------------|
| frontend | 2222      | Node 20 / npm            |
| midware  | 2223      | Python 3 / pip / venv    |
| supabase | 2224      | PostgreSQL 16 (host 5432)|

## Build & run

    ./build-and-run.sh          # or:  docker compose up -d --build

(host networking ignores compose `ports:`; sshd binds the host port directly)

## Connect (from the Hermes sandbox)

    ssh -i ~/.ssh/tickrange_ed25519 -o StrictHostKeyChecking=no -p 2222 root@127.0.0.1   # frontend
    ssh -i ~/.ssh/tickrange_ed25519 -o StrictHostKeyChecking=no -p 2223 root@127.0.0.1   # midware
    ssh -i ~/.ssh/tickrange_ed25519 -o StrictHostKeyChecking=no -p 2224 root@127.0.0.1   # supabase

The public key above is baked into each image's /root/.ssh/authorized_keys.
Root login is KEY-ONLY (PasswordAuthentication no).

## Ports to watch (host netns is shared — collisions matter)

- ssh: 2222 / 2223 / 2224
- postgres: 5432 (supabase)
- reserve for later: frontend dev 5173 or 3000, midware API 8001, PostgREST 3001
