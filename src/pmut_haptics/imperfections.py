"""Versioned deterministic samples; nominal geometry controls, actual geometry propagates."""
import math

import numpy as np


class PortableRandom:
    """xorshift32; open-interval uniforms, uncached Box-Muller normals."""
    def __init__(self, seed):
        self.state = (seed & 0xFFFFFFFF) or 0x6D2B79F5

    def uniform(self):
        x = self.state
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self.state = x & 0xFFFFFFFF
        return (self.state + 0.5) / 4294967296

    def normal(self):
        return math.sqrt(-2 * math.log(self.uniform())) * math.cos(2 * math.pi * self.uniform())


def generate_sample(config):
    n = config.array.nx * config.array.ny
    e = config.imperfections
    rng = PortableRandom(config.seed)
    sigma = math.sqrt(math.log1p(e.amplitude_cv**2))
    phase, gain, offsets, active = [], [], [], []
    for _ in range(n):
        phase.append(rng.normal() * math.radians(config.array.phase_error_std_deg))
        gain.append(math.exp(sigma * rng.normal() - sigma**2 / 2))
        offsets.append([rng.normal() * e.position_std_m, rng.normal() * e.position_std_m, 0.0])
        active.append(int(rng.uniform() >= e.failure_probability))
    if e.rng == "legacy":
        phase = np.random.default_rng(config.seed).normal(
            0, np.deg2rad(config.array.phase_error_std_deg), n).tolist()
    return {"version": e.rng, "seed": config.seed, "phase_rad": phase,
            "amplitude_gain": gain, "offsets_m": offsets, "active": active}


def validate_sample(sample, nominal, radius):
    n = len(nominal)
    for key in ("phase_rad", "amplitude_gain", "active"):
        a = np.asarray(sample[key], dtype=float)
        if a.shape != (n,) or not np.isfinite(a).all():
            raise ValueError("Invalid sample " + key)
    offsets = np.asarray(sample["offsets_m"], dtype=float)
    if offsets.shape != (n, 3) or not np.isfinite(offsets).all() or np.any(offsets[:, 2]):
        raise ValueError("Only finite planar position offsets are supported")
    if np.any(np.asarray(sample["amplitude_gain"]) < 0):
        raise ValueError("Amplitude gains must be nonnegative")
    if not np.isin(sample["active"], [0, 1]).all():
        raise ValueError("Active mask must contain only 0/1")
    actual = nominal + offsets
    # Pairwise check in strips avoids an N x N x 3 allocation.
    for i in range(n - 1):
        if np.any(np.linalg.norm(actual[i+1:] - actual[i], axis=1) < 2*radius*(1-1e-12)):
            raise ValueError("Invalid sample: displaced elements overlap")
    return actual
