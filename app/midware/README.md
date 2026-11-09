# tickrange — midware

Ingests live ticks (tickstream WebSocket), computes 100/500/1000-tick ranges
(Python engine, lockstep with the frontend JS port), persists ticks + bars +
range snapshots to Postgres, and relays ticks to browsers over websocket.
The DB is persistence-only, off the live path.

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt

    # env: TICKSTREAM_KEY, TICKRANGE_DSN, TICKRANGE_SYMBOL (default NQ)
    .venv/bin/uvicorn app.server:app --host 0.0.0.0 --port 8765

Endpoints: GET /health, GET /snapshot, WS /ws/ticks

## Backfill history into Postgres
    python scripts/backfill.py NQ 7      # last 7 days, bulk COPY into `ticks`

## Files
    app/server.py   FastAPI app: feed task + compute/persist/relay task
    app/feed.py     tickstream WebSocket client (auto-reconnect)
    app/engine.py   range engine (Python; mirror of the JS engine)
    app/db.py       psycopg3 writer: COPY ticks, insert bars/ranges, seed buffer
    scripts/backfill.py  REST 7-day tick backfill
    sql/001_ticks.sql    ticks table
