"""Midware: ingests live ticks (tickstream WS), computes 100/500/1000-tick
ranges with the Python engine, persists to Postgres and relays to browsers.

The DB is persistence-only, off the live path. The feed is the delayed tier, so
ticks land ~15 min behind the market - fine for range geometry.

When the live feed goes silent (market closed / weekend / CME halt) a replay
source keeps the chart moving by re-emitting real DB history at REPLAY_RATE
ticks/s. Live always wins: a single fresh tick stands replay down for
STALE_AFTER seconds.
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
DSN = os.environ.get("TICKRANGE_DSN", "postgresql://tickrange:***@127.0.0.1:5432/tickrange")
EXCH = {"NQ": "CME", "ES": "CME", "YM": "CBOT", "RTY": "CME"}
MAX_BUFFER = 60000
# Historical ticks loaded into the engine buffer at startup. Keep small to watch
# ranges build from LIVE ticks; raise via TICKRANGE_SEED for instant full ranges.
SEED = int(os.environ.get("TICKRANGE_SEED", "5000"))
INTERVAL = 0.15
# Replay fallback: seconds of live silence before replay kicks in, and its rate.
STALE_AFTER = float(os.environ.get("TICKRANGE_STALE_AFTER", "45"))
REPLAY_RATE = int(os.environ.get("TICKRANGE_REPLAY_RATE", "25"))   # ticks/sec while replaying


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
     "rows": [], "status": "init", "base": 0, "last_live": 0.0, "source": "live"}


def _ts(epoch):
    return datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc)


def _push(p, ts_us, size, side, persist=True):
    """Append one tick to the shared buffer + ws queue. `persist` controls whether
    it is also written to Postgres (replay ticks are NOT - they are history already)."""
    buf = S["buf"]
    buf.append(p)
    # Trim WHOLE bars only (LCM(100,500,1000)=1000) so bar boundaries never shift.
    # Dropping a non-multiple of 1000 re-chunks every bar (chart reshapes).
    if len(buf) > MAX_BUFFER:
        drop = -(-(len(buf) - MAX_BUFFER) // 1000) * 1000
        if 0 < drop < len(buf):
            del buf[:drop]
            S["base"] += drop
    S["count"] += 1
    S["price"] = p
    S["pending"].append(p)
    if persist:
        S["rows"].append((ts_us, p, size, side))
        if len(S["rows"]) > 200000:
            S["rows"] = S["rows"][-100000:]


async def feed_task():
    """Live ticks from tickstream. Stamps last_live so replay knows to stand down."""
    def status(m):
        S["status"] = m
    async for d in feed.stream([SYMBOL], on_status=status):
        if d.get("symbol") != SYMBOL:
            continue
        S["last_live"] = time.time()
        S["source"] = "live"
        _push(d["price"], d.get("tsu") or (d.get("ts") or 0) * 1_000_000,
              d.get("size", 0), d.get("side"))


async def replay_task():
    """Keeps the chart moving when the live feed is silent (weekend / market closed).
    Re-emits real DB history at REPLAY_RATE ticks/s, ONLY while no live tick has
    arrived for STALE_AFTER seconds. Loops; never persisted."""
    prices = []
    try:
        from .db import DB
        db = DB(DSN)
        inst = db.ensure_instrument(SYMBOL, EXCH.get(SYMBOL, "CME"), 0.25)
        prices = db.recent_prices(inst, 60000)
        print("[replay] loaded", len(prices), "historical prices", flush=True)
    except Exception as e:
        print("[replay] off:", e, flush=True)
        return
    if len(prices) < 1000:
        print("[replay] not enough history to replay:", len(prices), flush=True)
        return
    per = max(1, int(round(REPLAY_RATE * INTERVAL)))
    i = 0
    seeded = False
    ts = int(time.time() * 1_000_000)
    while True:
        if time.time() - S["last_live"] > STALE_AFTER:
            S["source"] = "replay"
            if not seeded:
                # Take over the engine buffer with a CONTIGUOUS slice of history. The
                # DB-seeded tail holds the NEWEST prices, so replay starting at the
                # OLDEST price painted a giant phantom candle at the seam - don't.
                head = min(6000, max(1000, len(prices) - 1))
                S["buf"] = prices[:head]
                S["count"] = head
                S["base"] = 0
                i = head
                seeded = True
                print("[replay] took over buffer, replaying from tick", i, flush=True)
            for _ in range(per):
                if i >= len(prices):
                    # Seamless loop: resume where the price matches the last price, so
                    # the wraparound doesn't draw a huge artificial jump/candle.
                    lastp = prices[-1]
                    i = min(range(len(prices)), key=lambda k: abs(prices[k] - lastp))
                _push(prices[i], ts, 1, "R", persist=False)
                i += 1
                ts += 250_000
        else:
            S["source"] = "live"
        await asyncio.sleep(INTERVAL)


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
            S["buf"] = db.recent_prices(inst, SEED)
            S["count"] = len(S["buf"])
            print("[engine] seeded buffer with", len(S["buf"]), "historical ticks", flush=True)
        except Exception as e:
            print("[engine] seed err:", e, flush=True)

    last_bar_key = {n: None for n in FRAMES}
    last_range = 0.0
    while True:
        buf = S["buf"]
        ev = evaluate_all(list(buf), FRAMES, 50, S["base"]) if len(buf) >= 100 else S["eval"]
        if ev:
            S["eval"] = ev
        pend = S["pending"]
        if pend:
            S["pending"] = []
            regime = ("range" if ev and ev["combined"] >= 55 else "trend") if ev else "warmup"
            await hub.broadcast(json.dumps({
                "type": "ticks", "p": pend,
                "meta": {"symbol": SYMBOL, "price": S["price"], "count": S["count"],
                         "regime": regime, "source": S["source"]}}))
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
    t3 = asyncio.create_task(replay_task())
    print(f"[server] engine up, symbol={SYMBOL}", flush=True)
    yield
    for t in (t1, t2, t3):
        t.cancel()
    for t in (t1, t2, t3):
        with contextlib.suppress(Exception):
            await t


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    ev = S["eval"]
    return {"ok": True, "symbol": SYMBOL, "feed": S["status"], "source": S["source"],
            "ticks": S["count"], "price": S["price"], "clients": len(hub.clients),
            "combined": round(ev["combined"], 1) if ev else None}


@app.get("/snapshot")
async def snapshot():
    return {"symbol": SYMBOL, "count": S["count"], "price": S["price"],
            "source": S["source"], "ticks": S["buf"][-2000:], "eval": S["eval"]}


@app.websocket("/ws/ticks")
async def ws_ticks(ws: WebSocket):
    await hub.connect(ws)
    try:
        await ws.send_text(json.dumps({"type": "hello", "symbol": SYMBOL}))
        await ws.send_text(json.dumps({
            "type": "ticks", "p": S["buf"][-20000:],
            "meta": {"symbol": SYMBOL, "price": S["price"], "count": S["count"],
                     "regime": "warmup", "source": S["source"]}}))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hub.disconnect(ws)
