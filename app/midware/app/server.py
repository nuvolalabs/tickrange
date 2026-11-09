"""Midware: ingests live ticks (tickstream WS), computes 100/500/1000-tick
ranges with the Python engine, persists to Postgres and relays to browsers.

The DB is persistence-only, off the live path. The feed is the delayed tier, so
ticks land ~15 min behind the market - fine for range geometry.
"""
import asyncio
import contextlib
import datetime
import json
import os
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import feed
from .engine import build_bars, evaluate_all, FRAMES

SYMBOL = os.environ.get("TICKRANGE_SYMBOL", "NQ")
DSN = os.environ.get("TICKRANGE_DSN", "postgresql://tickrange:tickrange@127.0.0.1:5432/tickrange")
EXCH = {"NQ": "CME", "ES": "CME", "YM": "CBOT", "RTY": "CME"}
MAX_BUFFER = 60000
INTERVAL = 0.15


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
S = {"buf": [], "count": 0, "price": None, "eval": None, "pending": [],
     "rows": [], "status": "init"}


def _ts(epoch):
    return datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc)


async def feed_task():
    def status(m):
        S["status"] = m
    async for d in feed.stream([SYMBOL], on_status=status):
        if d.get("symbol") != SYMBOL:
            continue
        p = d["price"]
        buf = S["buf"]
        buf.append(p)
        if len(buf) > MAX_BUFFER:
            del buf[: len(buf) - MAX_BUFFER]
        S["count"] += 1
        S["price"] = p
        S["pending"].append(p)
        S["rows"].append((d.get("tsu") or (d.get("ts") or 0) * 1_000_000,
                          p, d.get("size", 0), d.get("side")))
        if len(S["rows"]) > 200000:
            S["rows"] = S["rows"][-100000:]


async def compute_task():
    db = None
    inst = None
    try:
        from .db import DB
        db = DB(DSN)
        inst = db.ensure_instrument(SYMBOL, EXCH.get(SYMBOL, "CME"), 0.25)
        print("[engine] DB ok, instrument", SYMBOL, "=", inst, flush=True)
    except Exception as e:
        print("[engine] DB off:", e, flush=True)
        db = None

    if inst is not None:
        try:
            S["buf"] = db.recent_prices(inst, MAX_BUFFER)
            S["count"] = len(S["buf"])
            print("[engine] seeded buffer with", len(S["buf"]), "historical ticks", flush=True)
        except Exception as e:
            print("[engine] seed err:", e, flush=True)

    last_bar_key = {n: None for n in FRAMES}
    last_range = 0.0
    while True:
        buf = S["buf"]
        ev = evaluate_all(list(buf)) if len(buf) >= 100 else S["eval"]
        if ev:
            S["eval"] = ev
        pend = S["pending"]
        if pend:
            S["pending"] = []
            regime = ("range" if ev and ev["combined"] >= 55 else "trend") if ev else "warmup"
            await hub.broadcast(json.dumps({
                "type": "ticks", "p": pend,
                "meta": {"symbol": SYMBOL, "price": S["price"], "count": S["count"], "regime": regime}}))
        if ev:
            await hub.broadcast(json.dumps({"type": "eval", "ev": ev}))

        if db is not None:
            try:
                now = time.time()
                rows = S["rows"]
                if rows:
                    db.copy_ticks(inst, rows)
                    S["rows"] = []
                for n in FRAMES:
                    key = S["count"] // n
                    if key != last_bar_key[n]:
                        bars = build_bars(list(buf), n)
                        if bars:
                            b = bars[-1]
                            db.insert_bar(n, _ts(now), b["o"], b["h"], b["l"], b["c"], b["n"])
                        last_bar_key[n] = key
                if ev and now - last_range > 2.0:
                    for n in FRAMES:
                        db.insert_range(n, _ts(now), ev["out"][n])
                    db.insert_combined(_ts(now), ev)
                    last_range = now
            except Exception as e:
                print("[engine] persist err:", e, flush=True)
                db = None
        await asyncio.sleep(INTERVAL)


@contextlib.asynccontextmanager
async def lifespan(app):
    t1 = asyncio.create_task(feed_task())
    t2 = asyncio.create_task(compute_task())
    print(f"[server] engine up, symbol={SYMBOL}", flush=True)
    yield
    for t in (t1, t2):
        t.cancel()
    for t in (t1, t2):
        with contextlib.suppress(Exception):
            await t


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    ev = S["eval"]
    return {"ok": True, "symbol": SYMBOL, "feed": S["status"], "ticks": S["count"],
            "price": S["price"], "clients": len(hub.clients),
            "combined": round(ev["combined"], 1) if ev else None}


@app.get("/snapshot")
async def snapshot():
    return {"symbol": SYMBOL, "count": S["count"], "price": S["price"],
            "ticks": S["buf"][-2000:], "eval": S["eval"]}


@app.websocket("/ws/ticks")
async def ws_ticks(ws: WebSocket):
    await hub.connect(ws)
    try:
        await ws.send_text(json.dumps({"type": "hello", "symbol": SYMBOL}))
        await ws.send_text(json.dumps({
            "type": "ticks", "p": S["buf"][-20000:],
            "meta": {"symbol": SYMBOL, "price": S["price"], "count": S["count"], "regime": "warmup"}}))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hub.disconnect(ws)
