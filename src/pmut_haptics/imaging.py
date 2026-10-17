"""Synthetic-aperture extension. This is a water-model experiment, not haptic validation."""
from dataclasses import dataclass

import numpy as np
from scipy.signal import hilbert


@dataclass
class EchoData:
    signals: np.ndarray
    time_s: np.ndarray
    sample_rate_hz: float
    pulse_center_s: float


def simulate_echoes(array_x, scatterers_xz, strengths, frequency_hz=22960.0,
                    sound_speed_m_s=1480.0, sample_rate_hz=1e6, cycles_fwhm=3.0,
                    velocity_scale=1e-6, roi_xz=None):
    array_x, scatterers = np.asarray(array_x), np.asarray(scatterers_xz)
    strengths = np.asarray(strengths)
    if scatterers.ndim != 2 or scatterers.shape[1] != 2 or strengths.shape != (len(scatterers),):
        raise ValueError("Scatterer coordinates and strengths have incompatible shapes")
    if np.any(scatterers[:, 1] <= 0) or sample_rate_hz < 10*frequency_hz:
        raise ValueError("Positive depth and >=10 samples per carrier period are required")
    sigma = cycles_fwhm/frequency_hz/(2*np.sqrt(2*np.log(2)))
    center = 4*sigma
    distance = np.hypot(array_x[:, None]-scatterers[:, 0], scatterers[:, 1])
    max_distance = distance.max()
    if roi_xz is not None:
        roi = np.asarray(roi_xz)
        max_distance = max(max_distance, np.hypot(
            array_x[:, None]-roi[:, 0], roi[:, 1]).max())
    time_end = 2*max_distance/sound_speed_m_s + center + 4*sigma
    times = np.arange(int(np.ceil(time_end*sample_rate_hz))+1)/sample_rate_hz
    rf = np.zeros((len(array_x), len(array_x), len(times)))
    for s, strength in enumerate(strengths):
        tx, rx = distance[:, s, None], distance[None, :, s]
        arrival = (tx+rx)/sound_speed_m_s + center
        relative = times[None, None, :]-arrival[:, :, None]
        pulse = np.exp(-0.5*(relative/sigma)**2)*np.sin(2*np.pi*frequency_hz*relative)
        rf += velocity_scale*strength/(tx*rx)[:, :, None]*pulse
    return EchoData(rf, times, sample_rate_hz, center)


def delay_and_sum(echo: EchoData, array_x, x_grid, z_grid, sound_speed_m_s=1480.0):
    """Fractional-delay interpolation of analytic RF, followed by coherent sum/envelope."""
    array_x = np.asarray(array_x)
    n = len(array_x)
    if echo.signals.shape[:2] != (n, n) or echo.signals.shape[-1] != len(echo.time_s):
        raise ValueError("RF shape must be (N,N,T)")
    if len(echo.time_s) < 2 or not np.allclose(
        np.diff(echo.time_s), 1/echo.sample_rate_hz, rtol=1e-10, atol=1e-14
    ):
        raise ValueError("Echo time axis must match its sample rate")
    analytic = hilbert(echo.signals, axis=-1).reshape(n*n, -1)
    xx, zz = np.meshgrid(x_grid, z_grid, indexing="xy")
    result = np.empty(xx.size)
    channels = np.arange(n*n)[None, :]
    for start in range(0, xx.size, 512):
        x, z = xx.ravel()[start:start+512], zz.ravel()[start:start+512]
        distance = np.hypot(x[:, None]-array_x, z[:, None])
        arrival = (distance[:, :, None]+distance[:, None, :])/sound_speed_m_s
        sample = (arrival.reshape(len(x), -1)+echo.pulse_center_s-echo.time_s[0])
        sample *= echo.sample_rate_hz
        lo = np.floor(sample).astype(int)
        fraction = sample-lo
        valid = (lo >= 0) & (lo+1 < len(echo.time_s))
        safe = np.clip(lo, 0, len(echo.time_s)-2)
        values = analytic[channels, safe]*(1-fraction) + analytic[channels, safe+1]*fraction
        result[start:start+len(x)] = np.abs(np.sum(np.where(valid, values, 0), axis=1))
    return result.reshape(len(z_grid), len(x_grid))
