"""Range engine (Python). Must stay in lockstep with the frontend JS port.
Logic identical to the validated prototype: range box + 4-feature confidence."""
FRAMES = (100, 500, 1000)
BARS_PER_FRAME = 50


def build_bars(ticks, n):
    bars = []
    for i in range(0, len(ticks) - n + 1, n):
        c = ticks[i:i + n]
        bars.append({"o": c[0], "h": max(c), "l": min(c), "c": c[-1], "n": n})
    return bars


def efficiency_ratio(ys):
    net = abs(ys[-1] - ys[0])
    path = sum(abs(ys[i] - ys[i - 1]) for i in range(1, len(ys)))
    return net / path if path else 0.0


def linreg_slope(ys):
    n = len(ys)
    if n < 2:
        return 0.0
    mx = (n - 1) / 2
    my = sum(ys) / n
    num = sum((i - mx) * (ys[i] - my) for i in range(n))
    den = sum((i - mx) ** 2 for i in range(n))
    return num / den if den else 0.0


def range_confidence(bars):
    if not bars:
        return {"lower": 0.0, "upper": 0.0, "height": 0.0, "conf": 0.0, "n_bars": 0,
                "er": 0.0, "flat": 0.0, "touches": 0, "contain": 0.0}
    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]
    closes = [b["c"] for b in bars]
    upper, lower = max(highs), min(lows)
    height = (upper - lower) or 1e-9
    W = len(bars)
    er = efficiency_ratio(closes)
    er_score = (1 - er) * 100
    slope_norm = abs(linreg_slope(closes)) * W / height
    flat_score = 100 * (1 - min(1, slope_norm))
    eps = 0.10 * height
    touches = sum(1 for i in range(W) if highs[i] >= upper - eps or lows[i] <= lower - eps)
    touch_score = min(1, touches / 6) * 100
    contained = sum(1 for c in closes if lower + eps <= c <= upper - eps)
    contain_score = contained / W * 100
    conf = 0.35 * er_score + 0.25 * flat_score + 0.25 * touch_score + 0.15 * contain_score
    conf = max(1.0, min(100.0, conf))
    return {"lower": lower, "upper": upper, "height": height, "conf": conf, "n_bars": W,
            "er": er, "flat": flat_score, "touches": touches, "contain": contain_score}


def evaluate_all(ticks, frames=FRAMES, bars_per_frame=BARS_PER_FRAME):
    out = {}
    for n in frames:
        need = n * bars_per_frame
        start = max(0, len(ticks) - need)
        out[n] = range_confidence(build_bars(ticks[start:], n))
    confs = [out[n]["conf"] for n in frames]
    mean = sum(confs) / len(confs)
    spread = max(confs) - min(confs)
    agreement = 1 - spread / 100
    fast, slow = out[frames[0]], out[frames[-1]]
    slow_h = (slow["upper"] - slow["lower"]) or 1e-9
    pos = ((fast["lower"] + fast["upper"]) / 2 - slow["lower"]) / slow_h
    pos = max(0.0, min(1.0, pos))
    zone = ("near slow LOW (support)" if pos < 0.33
            else "near slow HIGH (resistance)" if pos > 0.67 else "mid range (no edge)")
    combined = mean * (0.65 + 0.35 * agreement)
    return {"frames": list(frames), "out": out, "mean_conf": mean, "spread": spread,
            "pos": pos, "zone": zone, "combined": combined}
