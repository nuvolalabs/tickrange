# tickrange — frontend

Standalone latency-free range finder: builds 100/500/1000-tick bars and computes
the range box + confidence per frame entirely in the browser (no backend).

    npm install
    npm run dev      # http://localhost:5173  (host-networked: reachable on the host)
    npm run build    # production build -> dist/

Currently fed by `src/lib/simulator.js` (synthetic ticks). Swap that for the
midware websocket tick relay to go live.
