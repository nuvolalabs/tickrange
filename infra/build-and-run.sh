#!/usr/bin/env bash
# Build + (re)create the three containers with host networking.
set -euo pipefail
cd "$(dirname "$0")"

echo ">> removing old containers if present"
docker rm -f frontend midware supabase 2>/dev/null || true

echo ">> building images"
docker build -t tr-frontend -f frontend/Dockerfile .
docker build -t tr-midware  -f midware/Dockerfile  .
docker build -t tr-supabase -f supabase/Dockerfile .

echo ">> starting containers (host networking)"
docker run -d --name frontend --hostname frontend --network host \
  -v "$(cd .. && pwd)/frontend:/workspace" --restart unless-stopped tr-frontend
docker run -d --name midware --hostname midware --network host \
  -v "$(cd .. && pwd)/midware:/workspace" --restart unless-stopped tr-midware
docker run -d --name supabase --hostname supabase --network host \
  -v tr-pgdata:/var/lib/postgresql --restart unless-stopped tr-supabase

echo ">> done. sshd ports: frontend 2222, midware 2223, supabase 2224"
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
