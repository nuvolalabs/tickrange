"""Midware: ingests ticks, persists derived bars/ranges to Postgres, and relays
live ticks to browser clients over websocket. The DB is off the live path."""
import asyncio
import contextlib
import json
import os
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .engine import build_bars, evaluate_all, FRAMES
from .simulator import Simulator

MAX_BUFFER = 60000
BATCH = 60
INTERVAL = 0.15
DSN = os.environ.get("TICKRANGE_DSN", "postgresql://tickrange:tickrange@127.0.0.1:5432/tickrange")


class Hub:
    def __init__(self):
        self.clients = set()

    async def connect(self, ws):
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws):
        self.clients.discard(ws)

    async def broadcast(self, msg):
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


hub = Hub()
state = {"ticks": [], "sim": Simulator(), "eval": None, "count": 0}


async def run_engine():
    db = None
    try:
        from .db import DB
        db = DB(DSN)
        db.ensure_instrument()
        print("[engine] DB connected, instrument_id =", db.instrument_id, flush=True)
    except Exception as e:
        print("[engine] DB unavailable, running without persistence:", e, flush=True)

    sim = state["sim"]
    last_bar_key = {n: None for n in FRAMES}
    last_range_persist = 0.0

    while True:
        batch = sim.batch(BATCH)
        state["ticks"].extend(batch)
        if len(state["ticks"]) > MAX_BUFFER:
            del state["ticks"][: len(state["ticks"]) - MAX_BUFFER]
        state["count"] = sim.count

        ev = evaluate_all(state["ticks"])
        state["eval"] = ev

        await hub.broadcast(json.dumps({
            "type": "ticks", "p": batch,
            "meta": {"price": sim.price, "count": sim.count, "regime": sim.regime},
        }))
        await hub.broadcast(json.dumps({"type": "eval", "ev": ev}))

        if db is not None:
            try:
                now = time.time()
                for n in FRAMES:
                    key = state["count"] // n
                    if key != last_bar_key[n]:
                        bars = build_bars(state["ticks"], n)
                        if bars:
                            b = bars[-1]
                            db.insert_bar(n, _ts(now), b["o"], b["h"], b["l"], b["c"], b["n"])
                        last_bar_key[n] = key
                if now - last_range_persist > 2.0:
                    for n in FRAMES:
                        db.insert_range(n, _ts(now), ev["out"][n])
                    db.insert_combined(_ts(now), ev)
                    last_range_persist = now
            except Exception as e:
                print("[engine] persist error:", e, flush=True)
                db = None

        await asyncio.sleep(INTERVAL)


def _ts(epoch):
    import datetime
    return datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc)


@contextlib.asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(run_engine())
    print("[server] engine task started", flush=True)
    yield
    task.cancel()
    with contextlib.suppress(Exception):
        await task


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    ev = state["eval"]
    return {"ok": True, "ticks": state["count"], "clients": len(hub.clients),
            "combined": round(ev["combined"], 1) if ev else None}


@app.get("/snapshot")
async def snapshot():
    return {"count": state["count"], "ticks": state["ticks"][-2000:], "eval": state["eval"]}


@app.websocket("/ws/ticks")
async def ws_ticks(ws: WebSocket):
    await hub.connect(ws)
    try:
        await ws.send_text(json.dumps({"type": "hello", "count": state["count"]}))
        await ws.send_text(json.dumps({"type": "ticks", "p": state["ticks"][-20000:],
                                       "meta": {"price": state["sim"].price, "count": state["count"],
                                                "regime": state["sim"].regime}}))
        while True:
            await ws.receive_text()  # drain client pings/keepalive
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hub.disconnect(ws)
