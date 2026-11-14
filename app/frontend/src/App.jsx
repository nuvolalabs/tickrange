import { useEffect, useRef, useState } from 'react'
import { createChart, LineStyle } from 'lightweight-charts'
import { evaluateAll, buildBars, FRAMES } from './lib/rangeEngine.js'
import { createSimulator } from './lib/simulator.js'

const FRAME_COLORS = { 100: '#22d3ee', 500: '#f59e0b', 1000: '#e879f9' }
const MAX_BUFFER = 60000
const TICKS_PER_TICK = 60
const INTERVAL_MS = 150
const VIEW_BARS = 60      // FIXED number of candles on screen; viewport never resizes
const WS_URL = `ws://${typeof location !== 'undefined' ? location.hostname : 'localhost'}:8765/ws/ticks`

export default function App() {
  const chartEl = useRef(null)
  const seriesRef = useRef(null)
  const linesRef = useRef({})
  const simRef = useRef(null)
  const bufRef = useRef([])
  const modeRef = useRef('live')
  const wsRef = useRef(null)
  const pendingRef = useRef([])
  const metaRef = useRef({ price: 100, count: 0, regime: 'range' })
  const baseRef = useRef(0)

  const [mode, setMode] = useState('live')
  const [symbol, setSymbol] = useState('NQ')
  const [wsState, setWsState] = useState('off')
  const [source, setSource] = useState('live')
  const [price, setPrice] = useState(27850)
  const [regime, setRegime] = useState('range')
  const [tickCount, setTickCount] = useState(0)
  const [ev, setEv] = useState(null)

  // chart + render loop (mount once)
  useEffect(() => {
    const chart = createChart(chartEl.current, {
      layout: { background: { color: '#0b0f14' }, textColor: '#9aa4b2', attributionLogo: false },
      grid: { vertLines: { color: '#1b2430' }, horzLines: { color: '#1b2430' } },
      timeScale: { timeVisible: true, secondsVisible: true, rightOffset: 2 },
      rightPriceScale: { borderColor: '#1b2430' }
    })
    const series = chart.addCandlestickSeries({
      upColor: '#16a34a', downColor: '#dc2626', borderVisible: false,
      wickUpColor: '#16a34a', wickDownColor: '#dc2626'
    })
    seriesRef.current = series
    const lines = {}
    for (const n of FRAMES) {
      lines[n] = {
        up: series.createPriceLine({ price: 100, color: FRAME_COLORS[n], lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: `${n}t hi` }),
        lo: series.createPriceLine({ price: 100, color: FRAME_COLORS[n], lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: `${n}t lo` })
      }
    }
    linesRef.current = lines
    simRef.current = createSimulator({ start: 27850 })

    const inited = { v: false }
    const lastComplete = { v: -1 }
    const lastLen = { v: 0 }

    const timer = setInterval(() => {
      const sim = simRef.current
      const buf = bufRef.current
      if (modeRef.current === 'live') {
        const pend = pendingRef.current
        if (pend.length) { for (const p of pend) buf.push(p); pend.length = 0 }
        const m = metaRef.current
        setPrice(m.price); setTickCount(m.count); setRegime(m.regime)
      } else {
        for (const p of sim.batch(TICKS_PER_TICK)) buf.push(p)
        setPrice(sim.price); setTickCount(sim.count); setRegime(sim.regime)
      }
      // Switching SIM<->LIVE clears the buffer -> reset the absolute bar origin.
      if (buf.length < lastLen.v) { baseRef.current = 0; inited.v = false; lastComplete.v = -1 }
      lastLen.v = buf.length
      // Trim WHOLE bars only (LCM(100,500,1000)=1000). A non-aligned trim re-chunks
      // every bar and reshapes the whole chart - the bug we're fixing.
      if (buf.length > MAX_BUFFER) {
        let drop = buf.length - MAX_BUFFER
        drop = Math.ceil(drop / 1000) * 1000
        if (drop > 0 && drop < buf.length) { buf.splice(0, drop); baseRef.current += drop }
      }
      const base = baseRef.current
      const evaluation = evaluateAll(buf, FRAMES, 50, base)
      setEv(evaluation)

      // 100-tick candles anchored to the ABSOLUTE bar index => closed bars never move.
      const baseBar = base / 100
      const complete = buildBars(buf, 100).slice(-160)
      const data = complete.map((b, i) => ({ time: baseBar + i, open: b.o, high: b.h, low: b.l, close: b.c }))
      // The still-forming last bar, built from the leftover (<100) ticks: this is the
      // only candle that resizes/shapes in realtime, and it settles on close.
      const tail = buf.length % 100
      if (tail) {
        const chunk = buf.slice(buf.length - tail)
        let hi = -Infinity, lo = Infinity
        for (const p of chunk) { if (p > hi) hi = p; if (p < lo) lo = p }
        data.push({ time: baseBar + complete.length, open: chunk[0], high: hi, low: lo, close: chunk[chunk.length - 1] })
      }
      if (typeof window !== 'undefined') window.__trData = data.map(d => ({ t: d.time, o: d.open, h: d.high, l: d.low, c: d.close }))
      if (!inited.v || complete.length !== lastComplete.v) {
        series.setData(data)                  // full repaint ONLY when a bar closes
        lastComplete.v = complete.length
        // FIXED-size viewport: constant width (VIEW_BARS). It only re-anchors when a
        // bar CLOSES (sliding one slot), never on a tick -> closed candles hold their
        // position and only the active last candle moves. `from` may go negative early
        // on: that just shows blank space on the left instead of a growing viewport.
        const to = data.length + 2
        chart.timeScale().setVisibleLogicalRange({ from: to - VIEW_BARS, to })
        inited.v = true
      } else if (data.length) {
        series.update(data[data.length - 1])   // live: update the ACTIVE candle only
      }
      for (const n of FRAMES) {
        lines[n].up.applyOptions({ price: evaluation.out[n].upper })
        lines[n].lo.applyOptions({ price: evaluation.out[n].lower })
      }
    }, INTERVAL_MS)

    return () => { clearInterval(timer); chart.remove() }
  }, [])

  // websocket (live mode)
  useEffect(() => {
    modeRef.current = mode
    bufRef.current = []
    pendingRef.current = []
    if (mode !== 'live') { setWsState('off'); if (wsRef.current) { wsRef.current.close(); wsRef.current = null } return }
    let closed = false
    setWsState('connecting')
    const connect = () => {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws
      ws.onopen = () => setWsState('open')
      ws.onmessage = (e) => {
        const d = JSON.parse(e.data)
        if (d.type === 'ticks') { const p = pendingRef.current; for (const x of d.p) p.push(x); if (d.meta) { metaRef.current = d.meta; if (d.meta.symbol) setSymbol(d.meta.symbol); if (d.meta.source) setSource(d.meta.source) } }
      }
      ws.onclose = () => { setWsState('connecting'); if (!closed) setTimeout(connect, 1000) }
      ws.onerror = () => ws.close()
    }
    connect()
    return () => { closed = true; if (wsRef.current) wsRef.current.close() }
  }, [mode])

  const live = mode === 'live'
  return (
    <div className="wrap">
      <header>
        <h1>tickrange</h1>
        <div className="hdr">
          <span className="sym">{symbol}</span>
          <span className="px">{price.toFixed(3)}</span>
          <span className={`regime ${regime}`}>{regime}</span>
          <span className="ticks">{tickCount.toLocaleString()} ticks</span>
          <span className={`badge ${live ? 'live' : ''}`} id="source-badge">
            {live ? `${source} · midware ws (${wsState})` : 'simulated (no feed yet)'}
          </span>
          <button id="mode-toggle" className="modebtn" onClick={() => setMode(m => m === 'live' ? 'sim' : 'live')}>
            {live ? '⇄ switch to SIM' : '⇄ switch to LIVE'}
          </button>
        </div>
      </header>

      <div className="chartbox">
        {live && source === 'replay' && (
          <div className="replaybar" id="replay-bar">
            ⏸ REPLAY — historical data, not live. The market feed is silent (closed), so real ticks from earlier sessions are being replayed.
          </div>
        )}
        <div className="chart" ref={chartEl} />
      </div>

      {ev && (
        <div className="panels">
          <div className="gauges">
            {FRAMES.map(n => (
              <Gauge key={n} frame={n} conf={ev.out[n].conf} lower={ev.out[n].lower} upper={ev.out[n].upper} />
            ))}
          </div>
          <div className="combined">
            <div className="cval">{ev.combined.toFixed(1)}</div>
            <div className="clabel">COMBINED CONFIDENCE</div>
            <div className="cmeta">spread {ev.spread.toFixed(1)} · mean {ev.meanConf.toFixed(1)} · pos {ev.pos.toFixed(2)}</div>
            <div className="czone">{ev.zone}</div>
          </div>
        </div>
      )}
    </div>
  )
}

function Gauge({ frame, conf, lower, upper }) {
  const color = FRAME_COLORS[frame]
  return (
    <div className="gauge">
      <div className="gtop"><span style={{ color }}>{frame}-tick</span><span className="gconf" style={{ color }}>{conf.toFixed(1)}</span></div>
      <div className="bar"><div className="fill" style={{ width: `${conf}%`, background: color }} /></div>
      <div className="glvls">[{lower.toFixed(3)} , {upper.toFixed(3)}]</div>
    </div>
  )
}
