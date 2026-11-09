# tickrange — midware

Ingests ticks, computes 100/500/1000-tick ranges (Python engine, lockstep with the
frontend JS port), persists bars + range snapshots to Postgres, and relays live
ticks to browsers over websocket. The DB is persistence-only, never on the live path.

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    TICKRANGE_DSN="postgresql://tickrange:PW@127.0.0.1:5432/tickrange" \
      .venv/bin/uvicorn app.server:app --host 0.0.0.0 --port 8765

Endpoints: GET /health, GET /snapshot, WS /ws/ticks
