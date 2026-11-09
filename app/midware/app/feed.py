"""tickstream WebSocket client -> async generator of tick dicts (auto-reconnect).

    wss://stream.tick-stream.xyz/v1/stream?key=...&symbols=NQ

Frames: {"type":"tick","symbol","price","size","side","ts"(s),"tsu"(us)} plus
welcome/ping/feed/warning/error. We answer the app-level ping with a pong.
"""
import asyncio
import json
import os

import websockets

WS_URL = "wss://stream.tick-stream.xyz/v1/stream"


async def stream(symbols, key=None, on_status=None):
    key = key or os.environ["TICKSTREAM_KEY"]
    url = f"{WS_URL}?key={key}&symbols={','.join(symbols)}"
    backoff = 1

    def status(m):
        if on_status:
            on_status(m)

    while True:
        try:
            async with websockets.connect(url, ping_interval=20, open_timeout=20,
                                          max_size=None, close_timeout=5) as ws:
                status("open")
                backoff = 1
                async for msg in ws:
                    d = json.loads(msg)
                    t = d.get("type")
                    if t == "tick":
                        yield d
                    elif t == "ping":
                        await ws.send(json.dumps({"op": "pong"}))
                    elif t in ("error", "warning"):
                        status(f"{t}: {d.get('error') or d}")
                    elif t == "welcome":
                        status("welcome")
        except Exception as e:
            status(f"closed: {type(e).__name__}: {e}")
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30)
        status("reconnecting")
