"""Slow envelopes and commanded focal trajectories; no carrier time stepping."""
import numpy as np


def envelope_at(times_s, modulation):
    times_s = np.asarray(times_s)
    if modulation.kind == "cw":
        return np.ones_like(times_s)
    phase = np.mod(times_s * modulation.frequency_hz, 1.0)
    if modulation.kind == "burst":
        # Snap numerical roundoff at exact period boundaries.
        phase = np.where(np.isclose(phase, 1.0, atol=1e-12, rtol=0), 0.0, phase)
        phase = np.where(np.isclose(phase, modulation.duty_cycle, atol=1e-12, rtol=0),
                         modulation.duty_cycle, phase)
        return (1-modulation.depth) + modulation.depth*(phase < modulation.duty_cycle)
    if modulation.kind == "sinusoidal":
        return (1-modulation.depth) + modulation.depth*(1+np.sin(2*np.pi*phase))/2
    raise ValueError("Unknown modulation kind")


def waveform(modulation):
    count = int(np.ceil(modulation.duration_s * modulation.sample_rate_hz))
    times = np.arange(count) / modulation.sample_rate_hz
    return times, envelope_at(times, modulation)


def focal_trajectory(config):
    t = config.trajectory
    center = np.array([config.focus.x_m, config.focus.y_m, config.focus.z_m])
    if t.kind == "static":
        return np.array([0.0]), center[None, :]
    times = np.linspace(0, t.duration_s, t.frames)
    phase = 2*np.pi*t.loops*times/t.duration_s
    points = np.tile(center, (t.frames, 1))
    if t.kind == "circle":
        points[:, 0] += t.radius_m*np.cos(phase)
        points[:, 1] += t.radius_m*np.sin(phase)
    elif t.kind == "line":
        points[:, 0] += t.line_length_m/2*np.sin(phase)
    else:
        raise ValueError("Unknown trajectory kind")
    return times, points
