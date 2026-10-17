"""Explicit main-lobe widths and physical stimulus quantities."""
from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks


def to_db(amplitude, floor_db=-80.0):
    amplitude = np.abs(np.asarray(amplitude))
    peak = amplitude.max(initial=0)
    if peak == 0:
        return np.full(amplitude.shape, floor_db)
    return 20*np.log10(np.maximum(amplitude/peak, 10**(floor_db/20)))


def connected_width(axis, values, fraction=10**(-6/20), peak_index=None) -> dict:
    """Width of the connected peak lobe; missing crossings are explicitly censored."""
    axis, values = np.asarray(axis, float), np.asarray(values, float)
    if axis.ndim != 1 or axis.shape != values.shape or len(axis) < 3:
        raise ValueError("Width requires matching one-dimensional arrays with >=3 points")
    if np.any(np.diff(axis) <= 0) or not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError("Axis must increase; profile must be finite and nonnegative")
    if not 0 < fraction < 1:
        raise ValueError("fraction must lie in (0,1)")
    peak = int(np.argmax(values)) if peak_index is None else int(peak_index)
    if not 0 <= peak < len(axis):
        raise ValueError("peak_index outside axis")
    if values[peak] <= 0:
        return {"width_m": None, "clipped": False, "reason": "zero_signal",
                "left_m": None, "right_m": None, "peak_index": peak}
    threshold = values[peak] * fraction
    left = right = peak
    while left > 0 and values[left-1] >= threshold:
        left -= 1
    while right < len(axis)-1 and values[right+1] >= threshold:
        right += 1
    clipped = left == 0 or right == len(axis)-1
    def crossing(i, j):
        return float(axis[i] + (threshold-values[i]) * (axis[j]-axis[i])
                     / (values[j]-values[i]))
    xl = None if left == 0 else crossing(left-1, left)
    xr = None if right == len(axis)-1 else crossing(right, right+1)
    return {"width_m": None if clipped else xr-xl, "clipped": clipped,
            "reason": "boundary" if clipped else "ok", "left_m": xl, "right_m": xr,
            "peak_index": peak}


def sidelobe_level_db(values):
    """Largest interior local maximum outside the first minima surrounding the main peak."""
    values = np.asarray(values, float)
    if values.max(initial=0) <= 0:
        return None
    peak = int(np.argmax(values))
    minima, _ = find_peaks(-values)
    left, right = minima[minima < peak], minima[minima > peak]
    if not len(left) or not len(right):
        return None
    maxima, _ = find_peaks(values)
    outside = maxima[(maxima < left[-1]) | (maxima > right[0])]
    if not len(outside):
        return None
    ratio = values[outside].max() / values[peak]
    return float(20*np.log10(ratio)) if ratio > 0 else None


def stimulus(pressure_peak, density_kg_m3, sound_speed_m_s, reflection_factor=2.0):
    """Approximate normal-incidence progressive-wave conversion, before reflection."""
    if density_kg_m3 <= 0 or sound_speed_m_s <= 0 or not 1 <= reflection_factor <= 2:
        raise ValueError("Invalid medium or reflection factor")
    pressure_rms = np.abs(pressure_peak) / np.sqrt(2)
    intensity = pressure_rms**2 / (density_kg_m3 * sound_speed_m_s)
    radiation = reflection_factor * intensity / sound_speed_m_s
    return pressure_rms, intensity, radiation


def plane_force(radiation_pressure, x_m, y_m):
    """Integrate a sampled finite target plane (last axes y,x) to force in N."""
    return np.trapezoid(np.trapezoid(radiation_pressure, x=x_m, axis=-1), x=y_m, axis=-1)


def plane_metrics(pressure, x_m, y_m, config):
    rms, intensity, radiation = stimulus(
        pressure, config.medium.density_kg_m3, config.medium.sound_speed_m_s,
        config.reflection_factor,
    )
    iy, ix = np.unravel_index(np.argmax(rms), rms.shape)
    peak = float(rms[iy, ix])
    zero = peak == 0
    return {
        "pressure_peak_pa": peak*np.sqrt(2),
        "pressure_rms_max_pa": peak,
        "spl_db_re_20uPa": float(20*np.log10(peak/20e-6)) if peak > 0 else None,
        "intensity_max_w_m2": float(intensity.max()),
        "radiation_pressure_max_pa": float(radiation.max()),
        "force_over_displayed_plane_n": float(plane_force(radiation, x_m, y_m)),
        "peak_x_m": None if zero else float(x_m[ix]),
        "peak_y_m": None if zero else float(y_m[iy]),
        "target_lateral_error_m": None if zero else float(np.hypot(
            x_m[ix]-config.focus.x_m, y_m[iy]-config.focus.y_m)),
        "pressure_x_minus6db": connected_width(x_m, rms[iy]),
        "pressure_y_minus6db": connected_width(y_m, rms[:, ix]),
        "radiation_x_fwhm": connected_width(x_m, radiation[iy], fraction=0.5),
        "radiation_y_fwhm": connected_width(y_m, radiation[:, ix], fraction=0.5),
        "sidelobe_x_db": sidelobe_level_db(rms[iy]),
        "sidelobe_y_db": sidelobe_level_db(rms[:, ix]),
        "plane_area_m2": float((x_m[-1]-x_m[0])*(y_m[-1]-y_m[0])),
    }
