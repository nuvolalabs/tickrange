"""Synthetic tick source (regime-switching OU range / trend).
Swap for a real feed adapter later; the rest of the pipeline is unchanged."""
import math
import random


def gauss():
    u = random.random() or 1e-9
    v = random.random()
    return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)


class Simulator:
    def __init__(self, start=100.0, regime_len=20000):
        self.price = start
        self.anchor = start
        self.regime = "range"
        self.count = 0
        self.regime_len = regime_len

    def step(self):
        self.count += 1
        if self.count % self.regime_len == 0:
            self.regime = "trend" if self.regime == "range" else "range"
            if self.regime == "range":
                self.anchor = self.price
        drift = -0.06 * (self.price - self.anchor) if self.regime == "range" else 0.0004
        self.price += drift + gauss() * 0.02
        return round(self.price, 3)

    def batch(self, k):
        return [self.step() for _ in range(k)]
