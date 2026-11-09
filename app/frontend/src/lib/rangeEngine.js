// JS port of the Python range engine (must stay in lockstep with the prototype).
export const FRAMES = [100, 500, 1000]
export const BARS_PER_FRAME = 50

export function buildBars(ticks, n) {
  const bars = []
  for (let i = 0; i + n <= ticks.length; i += n) {
    const chunk = ticks.slice(i, i + n)
    let hi = -Infinity, lo = Infinity
    for (const p of chunk) { if (p > hi) hi = p; if (p < lo) lo = p }
    bars.push({ o: chunk[0], h: hi, l: lo, c: chunk[chunk.length - 1], n })
  }
  return bars
}

export function efficiencyRatio(ys) {
  const net = Math.abs(ys[ys.length - 1] - ys[0])
  let path = 0
  for (let i = 1; i < ys.length; i++) path += Math.abs(ys[i] - ys[i - 1])
  return path ? net / path : 0
}

export function linregSlope(ys) {
  const n = ys.length
  if (n < 2) return 0
  const mx = (n - 1) / 2
  const my = ys.reduce((a, b) => a + b, 0) / n
  let num = 0, den = 0
  for (let i = 0; i < n; i++) { num += (i - mx) * (ys[i] - my); den += (i - mx) * (i - mx) }
  return num / (den || 1e-9)
}

export function rangeConfidence(bars) {
  if (!bars.length) return { lower: 0, upper: 0, height: 0, conf: 0, nBars: 0, feat: { er: 0, flat: 0, touches: 0, contain: 0 } }
  const highs = bars.map(b => b.h), lows = bars.map(b => b.l), closes = bars.map(b => b.c)
  const upper = Math.max(...highs), lower = Math.min(...lows)
  const height = (upper - lower) || 1e-9
  const W = bars.length

  const er = efficiencyRatio(closes)
  const erScore = (1 - er) * 100

  const slopeNorm = Math.abs(linregSlope(closes)) * W / height
  const flatScore = 100 * (1 - Math.min(1, slopeNorm))

  const eps = 0.10 * height
  let touches = 0
  for (let i = 0; i < W; i++) if (highs[i] >= upper - eps || lows[i] <= lower + eps) touches++
  const touchScore = Math.min(1, touches / 6) * 100

  let contained = 0
  const loIn = lower + eps, hiIn = upper - eps
  for (const c of closes) if (c >= loIn && c <= hiIn) contained++
  const containScore = (contained / W) * 100

  let conf = 0.35 * erScore + 0.25 * flatScore + 0.25 * touchScore + 0.15 * containScore
  conf = Math.max(1, Math.min(100, conf))

  return {
    lower, upper, height, conf, nBars: W,
    feat: { er, flat: flatScore, touches, contain: containScore }
  }
}

export function evaluateAll(ticks, frames = FRAMES, barsPerFrame = BARS_PER_FRAME) {
  const out = {}
  for (const n of frames) {
    const need = n * barsPerFrame
    const start = Math.max(0, ticks.length - need)
    const bars = buildBars(ticks.slice(start), n)
    out[n] = rangeConfidence(bars)
  }
  const confs = frames.map(n => out[n].conf)
  const meanConf = confs.reduce((a, b) => a + b, 0) / confs.length
  const spread = Math.max(...confs) - Math.min(...confs)
  const agreement = 1 - spread / 100
  const fast = out[frames[0]], slow = out[frames[frames.length - 1]]
  const slowH = (slow.upper - slow.lower) || 1e-9
  let pos = ((fast.lower + fast.upper) / 2 - slow.lower) / slowH
  pos = Math.max(0, Math.min(1, pos))
  const zone = pos < 0.33 ? 'near slow LOW (support)' : pos > 0.67 ? 'near slow HIGH (resistance)' : 'mid range (no edge)'
  const combined = meanConf * (0.65 + 0.35 * agreement)
  return { out, frames, spread, meanConf, agreement, pos, zone, combined }
}
