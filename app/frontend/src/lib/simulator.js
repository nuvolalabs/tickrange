// Synthetic tick source for the standalone frontend (swap for the midware ws later).
function gauss() {
  let u = 0, v = 0
  while (!u) u = Math.random()
  while (!v) v = Math.random()
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v)
}

export function createSimulator({ start = 100 } = {}) {
  let price = start
  let anchor = start
  let regime = 'range'
  let count = 0

  function step() {
    count++
    if (count % 20000 === 0) {           // flip regime every ~20k ticks
      regime = regime === 'range' ? 'trend' : 'range'
      if (regime === 'range') anchor = price
    }
    const drift = regime === 'range' ? -0.06 * (price - anchor) : 0.0004
    price += drift + gauss() * 0.02
    return +price.toFixed(3)
  }

  return {
    batch(k) { const a = []; for (let i = 0; i < k; i++) a.push(step()); return a },
    get regime() { return regime },
    get price() { return price },
    get count() { return count }
  }
}
