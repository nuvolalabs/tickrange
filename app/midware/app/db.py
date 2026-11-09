"""Postgres persistence (psycopg3). History/persistence only - never on the live path."""
import psycopg


class DB:
    def __init__(self, dsn):
        self.conn = psycopg.connect(dsn, autocommit=True)
        self.instrument_id = None

    def ensure_instrument(self, symbol="ES", exchange="CME", tick_size=0.25):
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO instruments(symbol,exchange,tick_size) VALUES(%s,%s,%s) "
                "ON CONFLICT(symbol) DO UPDATE SET exchange=EXCLUDED.exchange RETURNING id",
                (symbol, exchange, tick_size))
            self.instrument_id = cur.fetchone()[0]
        return self.instrument_id

    def insert_bar(self, frame, ts, o, h, l, c, n):
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tick_bars(instrument_id,frame_ticks,bar_ts,o,h,l,c,n_ticks) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT(instrument_id,frame_ticks,bar_ts) DO NOTHING",
                (self.instrument_id, frame, ts, o, h, l, c, n))

    def insert_range(self, frame, ts, r):
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO range_snapshots(instrument_id,frame_ticks,as_of,lower,upper,height,"
                "confidence,er,flatness,touches,containment) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (self.instrument_id, frame, ts, r["lower"], r["upper"], r["height"], r["conf"],
                 r["er"], r["flat"], r["touches"], r["contain"]))

    def insert_combined(self, ts, ev):
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO range_combined(instrument_id,as_of,combined_conf,spread,position,zone) "
                "VALUES(%s,%s,%s,%s,%s,%s)",
                (self.instrument_id, ts, ev["combined"], ev["spread"], ev["pos"], ev["zone"]))

    def ping(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone()[0]
