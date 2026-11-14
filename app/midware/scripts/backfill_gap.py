"""Backfill ONLY ticks newer than the DB's current max(ts_us) for a symbol.

The stock backfill.py inserts from a fresh window and would duplicate rows (the
`ticks` table has no unique constraint), so resume from the DB high-water mark.
"""
import json, os, sys, time, urllib.request
import psycopg

KEY = os.environ["TICKSTREAM_KEY"]
DSN = os.environ["TICKRANGE_DSN"]
API = "https://api.tick-stream.xyz/v1/ticks"
EXCH = {"NQ": "CME", "ES": "CME", "YM": "CBOT", "RTY": "CME"}
symbol = sys.argv[1] if len(sys.argv) > 1 else "NQ"


def get(url):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {KEY}",
        "User-Agent": "tickrange/1.0 (+https://nuvolalabs.github.io)",
        "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


conn = psycopg.connect(DSN)
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute("INSERT INTO instruments(symbol,exchange,tick_size) VALUES(%s,%s,%s) "
                "ON CONFLICT(symbol) DO UPDATE SET exchange=EXCLUDED.exchange RETURNING id",
                (symbol, EXCH.get(symbol, "CME"), 0.25))
    inst = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(max(ts_us),0) FROM ticks WHERE instrument_id=%s", (inst,))
    last_us = cur.fetchone()[0]

end = int(time.time())
cur_s = max(last_us // 1_000_000, end - 7 * 86400)
print(f"resume {symbol} inst={inst} after ts_us={last_us} from {cur_s} to {end}", flush=True)
total = pages = 0
t0 = time.time()
while cur_s < end:
    url = f"{API}?symbol={symbol}&start={cur_s}&end={end}&limit=100000&order=asc"
    r = get(url)
    ticks = r.get("ticks") or []
    rows = [(inst, t["ts"], t["price"], t["size"], t.get("side")) for t in ticks if t["ts"] > last_us]
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
        print(f"  pages={pages} new={total} at={cur_s} behind={(end-cur_s)/3600:.1f}h "
              f"({total/max(time.time()-t0,1):.0f}/s)", flush=True)
    if rows and not r.get("truncated"):
        break
print(f"DONE {symbol}: {total} new ticks, {pages} pages, {time.time()-t0:.0f}s", flush=True)
