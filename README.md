# tickrange — live tick range finder

Finds ranges on tick charts: builds 100 / 500 / 1000-tick bars, computes a range
box `[lower, upper]` + a 1-100 confidence per frame and a combined score, live.

## Data (tickstream)
Live + historical ticks come from **tickstream** (`https://tick-stream.xyz`).
This plan is the **delayed tier**: 15-min-delayed live ticks, **7 days** of REST
history, 10 symbols / 1 connection.

- REST backfill: `GET /v1/ticks?symbol=NQ&start=&end=&limit=100000&order=asc`
  reaches back 7 days; page with `start = last_ts // 1_000_000` (ts is unix µs).
- Live stream: `wss://stream.tick-stream.xyz/v1/stream?key=…&symbols=NQ`
  (tick frames: `{symbol,price,size,side,ts,tsu}`; answer `{"type":"ping"}` with a pong).
- Key lives in `/workspace/.env` (midware) as `TICKSTREAM_KEY` — never committed.

## Architecture (three containers, host networking)

    tickstream ─▶ MIDWARE ─┬─▶ websocket  ─▶ FRONTEND (browser, computes ranges live)
    (WS + REST)            └─▶ Postgres (ticks + bars + range snapshots; history only)

  - FRONTEND  Vite + React + PWA (:5173). Computes bars + ranges in the tab.
              SIM / LIVE toggle in the header; symbol comes from the feed (NQ).
  - MIDWARE   FastAPI + uvicorn (:8765). WS ingester -> Python range engine ->
              persist + relay. Seeded from the last 60k DB ticks on startup.
              `GET /health`, `GET /snapshot`, `WS /ws/ticks`  (20k-tick backlog on connect).
  - SUPABASE  Postgres 16 (:5432), DB `tickrange`, role `tickrange`. Tables:
              instruments, ticks, tick_bars, range_snapshots, range_combined.

  SSH (key auth): frontend :2222 | midware :2223 | supabase :2224

## Components
  frontend/   Vite+React app; src/lib/rangeEngine.js = JS engine
  midware/    FastAPI service; app/engine.py = Python engine (kept in lockstep),
              app/feed.py = tickstream WS client, scripts/backfill.py = REST backfill
  infra/      docker-compose kit for the 3-container stack

## Run
  # one-time history seed (NQ, 7 days) -> Postgres `ticks`
  TICKSTREAM_KEY=… TICKRANGE_DSN=… python midware/scripts/backfill.py NQ 7

  ./deploy_tickrange.sh     # sync source to both containers + restart services
  open http://localhost:5173   (header toggle SIM ⇄ LIVE)

## Env (midware /workspace/.env)
  TICKSTREAM_KEY   tickstream API key
  TICKRANGE_DSN    postgres DSN (role tickrange)
  TICKRANGE_SYMBOL symbol to stream (default NQ)

## Notes / TODO
  - Containers have NO bind mount: /workspace is container-local, lost on `docker rm`.
    Source backup: Documents\2026\resumes\tickrange-app
  - The delayed tier's live ticks are ~15 min behind — fine for range geometry.
  - PostgREST / history-read UI not built yet.
