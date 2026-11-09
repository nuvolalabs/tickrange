-- Raw tick store (one table per symbol via instrument_id).
CREATE TABLE IF NOT EXISTS ticks (
  id            bigserial PRIMARY KEY,
  instrument_id integer NOT NULL REFERENCES instruments(id),
  ts_us         bigint  NOT NULL,   -- exchange timestamp, unix microseconds
  price         numeric NOT NULL,
  size          integer NOT NULL,
  side          text                -- aggressor: 'buy' | 'sell' | 'unknown'
);
CREATE INDEX IF NOT EXISTS ticks_inst_ts_idx ON ticks (instrument_id, ts_us);
