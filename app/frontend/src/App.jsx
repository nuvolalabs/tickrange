import { useEffect, useRef, useState } from 'react'
import { createChart, LineStyle } from 'lightweight-charts'
import { evaluateAll, buildBars, FRAMES } from './lib/rangeEngine.js'
import { createSimulator } from './lib/simulator.js'

const FRAME_COLORS = { 100: '#22d3ee', 500: '#f59e0b', 1000: '#e879f9' }
const MAX_BUFFER = 60000
const TICKS_PER_TICK = 60
const INTERVAL_MS = 150
const WS_URL = `ws://${typeof location !== 'undefined' ? location.hostname : 'localhost'}:8765/ws/ticks`

export default function App() {
  const chartEl = useRef(null)
  const seriesRef = useRef(null)
  const linesRef = useRef({})
  const simRef = useRef(null)
  const bufRef = useRef([])
  const modeRef = useRef('sim')
  const wsRef = useRef(null)
  const pendingRef = useRef([])
  const metaRef = useRef({ price: 100, count: 0, regime: 'range' })

  const [mode, setMode] = useState('sim')
  const [wsState, setWsState] = useState('off')
  const [price, setPrice] = useState(100)
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
    simRef.current = createSimulator({ start: 100 })

    const timer = setInterval(() => {
      const sim = simRef.current
      const buf = bufRef.current
      if (modeRef.current === 'live') {
        const pend = pendingRef.current
        if (pend.length) { for (const p of pend) buf.push(p); pend.length = 0 }
        if (buf.length > MAX_BUFFER) buf.splice(0, buf.length - MAX_BUFFER)
        const m = metaRef.current
        setPrice(m.price); setTickCount(m.count); setRegime(m.regime)
      } else {
        for (const p of sim.batch(TICKS_PER_TICK)) buf.push(p)
        if (buf.length > MAX_BUFFER) buf.splice(0, buf.length - MAX_BUFFER)
        setPrice(sim.price); setTickCount(sim.count); setRegime(sim.regime)
      }
      const evaluation = evaluateAll(buf)
      setEv(evaluation)
      const totalBars = Math.floor(buf.length / 100)
      const bars100 = buildBars(buf, 100).slice(-140)
      const first = totalBars - bars100.length
      series.setData(bars100.map((b, i) => ({ time: first + i, open: b.o, high: b.h, low: b.l, close: b.c })))
      chart.timeScale().fitContent()
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
        if (d.type === 'ticks') { const p = pendingRef.current; for (const x of d.p) p.push(x); if (d.meta) metaRef.current = d.meta }
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
          <span className="sym">ES</span>
          <span className="px">{price.toFixed(3)}</span>
          <span className={`regime ${regime}`}>{regime}</span>
          <span className="ticks">{tickCount.toLocaleString()} ticks</span>
          <span className={`badge ${live ? 'live' : ''}`} id="source-badge">
            {live ? `live · midware ws (${wsState})` : 'simulated (no feed yet)'}
          </span>
          <button id="mode-toggle" className="modebtn" onClick={() => setMode(m => m === 'live' ? 'sim' : 'live')}>
            {live ? '⇄ switch to SIM' : '⇄ switch to LIVE'}
          </button>
        </div>
      </header>

      <div className="chart" ref={chartEl} />

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
