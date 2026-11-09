# tickrange — live tick range finder

Finds ranges on tick charts. Builds 100 / 500 / 1000-tick bars, computes a range
box `[lower, upper]` + a 1–100 confidence per frame and a combined score, live.

## Architecture (three containers, host networking)

    feed adapter ─▶ MIDWARE ─┬─▶ websocket  ─▶ FRONTEND (browser, computes ranges live)
      (simulator             └─▶ Postgres (bars + range snapshots; history only,
       for now)                    never on the live path)

  - FRONTEND  Vite + React + PWA. Computes bars + ranges in the tab (latency-free).
              Served at :5173 by the vite dev server. SIM/LIVE toggle in the header.
  - MIDWARE   FastAPI + uvicorn. Ingests ticks, runs the Python range engine,
              persists derived bars/ranges to Postgres, relays live ticks over ws.
              :8765  (GET /health, GET /snapshot, WS /ws/ticks)
  - SUPABASE  Postgres 16. DB `tickrange` (role `tickrange`), tables:
              instruments, tick_bars, range_snapshots, range_combined.
              :5432

  SSH (key auth): frontend :2222 | midware :2223 | supabase :2224

## Components
  frontend/   Vite+React app; src/lib/rangeEngine.js is the JS engine
  midware/    FastAPI service; app/engine.py is the Python engine
              (the two engines are kept in lockstep — change both together)

## Run / redeploy
  ./deploy_tickrange.sh        # sync source to both containers + restart services

## Open it
  http://localhost:5173        # frontend (header toggle SIM ⇄ LIVE)

## Notes / TODO
  - Containers currently have NO bind mount: /workspace is container-local and lost
    on `docker rm`. Source is backed up at Documents\2026\resumes\tickrange-app.
    Add `-v C:\dev\tickrange\<svc>:/workspace` on recreate to persist.
  - The tick source is a synthetic regime simulator (midware/app/simulator.py and
    frontend/src/lib/simulator.js). Swap for a real feed adapter (Databento/IQFeed/
    Polygon etc.) — the rest of the pipeline is unchanged.
  - PostgREST (Supabase API) for reading history is not set up yet.
