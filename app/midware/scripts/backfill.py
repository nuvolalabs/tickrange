"""Backfill recent ticks from tickstream REST into Postgres.

    TICKSTREAM_KEY=... TICKRANGE_DSN=... python backfill.py NQ 7

Pages /v1/ticks (asc, limit 100k) via start = last_ts // 1e6, bulk-COPY into `ticks`.
REST reaches back 7 days on this plan; a start further back is clamped by the API.
"""
import json
import os
import sys
import time
import urllib.request

import psycopg

KEY = os.environ["TICKSTREAM_KEY"]
DSN = os.environ["TICKRANGE_DSN"]
API = "https://api.tick-stream.xyz/v1/ticks"
EXCH = {"NQ": "CME", "ES": "CME", "YM": "CBOT", "RTY": "CME"}


def get(url):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {KEY}",
        "User-Agent": "tickrange/1.0 (+https://nuvolalabs.github.io)",
        "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    days = float(sys.argv[2]) if len(sys.argv) > 2 else 7.0

    conn = psycopg.connect(DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO instruments(symbol,exchange,tick_size) VALUES(%s,%s,%s) "
            "ON CONFLICT(symbol) DO UPDATE SET exchange=EXCLUDED.exchange RETURNING id",
            (symbol, EXCH.get(symbol, "CME"), 0.25))
        inst = cur.fetchone()[0]

    end = int(time.time())
    cur_s = end - int(days * 86400)
    last_us = 0
    total = 0
    pages = 0
    t0 = time.time()
    print(f"backfill {symbol} inst={inst} window {cur_s}..{end} ({days}d)", flush=True)

    while cur_s < end:
        url = f"{API}?symbol={symbol}&start={cur_s}&end={end}&limit=100000&order=asc"
        r = get(url)
        ticks = r.get("ticks") or []
        rows = [(inst, t["ts"], t["price"], t["size"], t.get("side"))
                for t in ticks if t["ts"] > last_us]
        if rows:
            with conn.cursor() as cur:
                with cur.copy("COPY ticks (instrument_id, ts_us, price, size, side) FROM STDIN") as cp:
                    for row in rows:
                        cp.write_row(row)
            total += len(rows)
            last_us = ticks[-1]["ts"]
            cur_s = last_us // 1_000_000
        else:
            cur_s += 3600
        pages += 1
        if pages % 10 == 0 or not rows:
            el = time.time() - t0
            print(f"  pages={pages} ticks={total} at={cur_s} behind={(end-cur_s)/3600:.1f}h "
                  f"({total/max(el,1):.0f}/s)", flush=True)
        if rows and not r.get("truncated"):
            break

    print(f"DONE {symbol}: {total} ticks, {pages} pages, {time.time()-t0:.0f}s", flush=True)


main()
