"""Linear baffled-piston acoustics; exp(+i*omega*t) time convention."""
from __future__ import annotations

import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.special import j1

from .config import SimulationConfig


def array_positions(config: SimulationConfig) -> np.ndarray:
    x = (np.arange(config.array.nx) - (config.array.nx - 1) / 2) * config.pitch_m
    y = (np.arange(config.array.ny) - (config.array.ny - 1) / 2) * config.pitch_m
    xx, yy = np.meshgrid(x, y, indexing="xy")
    return np.column_stack((xx.ravel(), yy.ravel(), np.zeros(xx.size)))


def focus_point(config: SimulationConfig) -> np.ndarray:
    return np.array([config.focus.x_m, config.focus.y_m, config.focus.z_m])


def jinc(value: np.ndarray) -> np.ndarray:
    value = np.asarray(value, dtype=float)
    out = np.ones_like(value)
    np.divide(2 * j1(value), value, out=out, where=np.abs(value) > 1e-12)
    return out


def focusing_weights(positions, target, config: SimulationConfig, sample=None) -> np.ndarray:
    """Peak surface velocity phasors. Apodization keeps sum(|u|^2) unchanged."""
    positions = np.asarray(positions, dtype=float)
    target = np.asarray(target, dtype=float)
    distance = np.linalg.norm(positions - target, axis=1)
    phase = 2 * np.pi / config.wavelength_m * (distance - distance.min())
    amplitude = np.ones(len(positions))
    if config.array.apodization == "hann":
        def window(n):
            return np.hanning(n) if n >= 3 else np.ones(n)
        amplitude = np.outer(window(config.array.ny), window(config.array.nx)).ravel()
        amplitude *= np.sqrt(len(amplitude) / np.sum(amplitude**2))
    from .imperfections import generate_sample
    if sample is None:
        sample = generate_sample(config)
    bits = config.imperfections.phase_bits
    if bits:
        step = 2 * np.pi / (2**bits)
        phase = np.floor(phase / step + 0.5) * step
    phase += np.asarray(sample["phase_rad"])
    amplitude *= np.asarray(sample["amplitude_gain"]) * np.asarray(sample["active"])

    return config.element.velocity_peak_m_s * amplitude * np.exp(1j * phase)


def piston_transfer(points, positions, frequency_hz, radius_m, density_kg_m3,
                    sound_speed_m_s, attenuation_np_m=0.0) -> np.ndarray:
    """M x N transfer matrix in Pa/(m/s); element normals are +z."""
    points = np.asarray(points, dtype=float)
    positions = np.asarray(positions, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("points must have shape (M,3)")
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError("positions must have shape (N,3)")
    if not np.isfinite(points).all() or not np.isfinite(positions).all():
        raise ValueError("Coordinates must be finite")
    dx = points[:, None, 0] - positions[None, :, 0]
    dy = points[:, None, 1] - positions[None, :, 1]
    dz = points[:, None, 2] - positions[None, :, 2]
    if np.any(dz <= 0):
        raise ValueError("Field points must be in front of every piston")
    radius = np.sqrt(dx * dx + dy * dy + dz * dz)
    k = 2 * np.pi * frequency_hz / sound_speed_m_s
    direction = jinc(k * radius_m * np.sqrt(dx * dx + dy * dy) / radius)
    coefficient = 1j * density_kg_m3 * sound_speed_m_s * k * radius_m**2 / 2
    return coefficient * direction * np.exp((-1j * k - attenuation_np_m) * radius) / radius


def transfer_from_config(points, positions, config):
    return piston_transfer(points, positions, config.carrier_hz, config.element.radius_m,
                           config.medium.density_kg_m3, config.medium.sound_speed_m_s,
                           config.medium.attenuation_np_m)


def _block_points(config, element_count):
    # Estimate geometry and complex-kernel temporaries; this is not a process RSS limit.
    by_memory = max(1, int(config.engine.max_transfer_mb * 1024**2 / (80 * element_count)))
    return min(config.engine.chunk_points, by_memory)


def field_pressure(points, positions, weights, config, backend="vectorized") -> np.ndarray:
    """Return complex peak pressure (Pa), with identical physics in both backends."""
    points = np.asarray(points, dtype=float)
    weights = np.asarray(weights, dtype=complex)
    if weights.shape != (len(positions),):
        raise ValueError("One velocity phasor is required per element")
    if backend == "reference":
        return np.array([transfer_from_config(p[None, :], positions, config)[0] @ weights
                         for p in points])
    if backend != "vectorized":
        raise ValueError("Unknown backend")
    out = np.empty(len(points), dtype=complex)
    block = _block_points(config, len(positions))
    for start in range(0, len(points), block):
        stop = start + block
        out[start:stop] = transfer_from_config(points[start:stop], positions, config) @ weights
    return out


def field_frames(points, positions, weights, config) -> np.ndarray:
    """M x T pressure, reusing each geometry block for all trajectory frames."""
    points = np.asarray(points)
    weights = np.asarray(weights)
    if weights.ndim != 2 or weights.shape[0] != len(positions):
        raise ValueError("weights must have shape (N,T)")
    # Bound the main matrix and temporaries; never allocate a full 3-D volume.
    block = _block_points(config, len(positions))
    out = np.empty((len(points), weights.shape[1]), dtype=complex)
    for start in range(0, len(points), block):
        out[start:start+block] = transfer_from_config(points[start:start+block], positions,
                                                     config) @ weights
    return out


def rayleigh_disk(points, radius_m, frequency_hz, density_kg_m3, sound_speed_m_s,
                  velocity_peak_m_s=1.0, radial_order=32, angular_order=64,
                  center=(0.0, 0.0, 0.0)) -> np.ndarray:
    """Full polar surface quadrature for a uniform, lossless baffled circular piston."""
    points = np.asarray(points, dtype=float) - np.asarray(center)
    if points.ndim != 2 or points.shape[1] != 3 or np.any(points[:, 2] <= 0):
        raise ValueError("Quadrature points must be above the piston")
    if radial_order < 2 or angular_order < 4:
        raise ValueError("Insufficient quadrature order")
    roots, quadrature_weights = leggauss(radial_order)
    r = (roots + 1) * radius_m / 2
    wr = quadrature_weights * radius_m / 2
    phi = np.arange(angular_order) * 2 * np.pi / angular_order
    sx = (r[:, None] * np.cos(phi)).ravel()
    sy = (r[:, None] * np.sin(phi)).ravel()
    area_weights = np.broadcast_to((wr*r)[:, None] * (2*np.pi/angular_order),
                                   (radial_order, angular_order)).ravel()
    k = 2 * np.pi * frequency_hz / sound_speed_m_s
    coefficient = 1j * density_kg_m3 * sound_speed_m_s * k / (2*np.pi)
    result = np.empty(len(points), dtype=complex)
    for start in range(0, len(points), 64):
        p = points[start:start+64]
        distance = np.sqrt((p[:, None, 0]-sx)**2 + (p[:, None, 1]-sy)**2
                           + p[:, None, 2]**2)
        result[start:start+64] = coefficient * velocity_peak_m_s * (
            np.exp(-1j*k*distance) / distance @ area_weights
        )
    return result


def axis_pressure(z_m, radius_m, frequency_hz, density_kg_m3, sound_speed_m_s,
                  velocity_peak_m_s=1.0):
    z = np.asarray(z_m, dtype=float)
    if np.any(z <= 0):
        raise ValueError("z must be positive")
    k = 2*np.pi*frequency_hz/sound_speed_m_s
    difference = radius_m**2 / (np.sqrt(z*z + radius_m**2) + z)
    return (density_kg_m3 * sound_speed_m_s * velocity_peak_m_s
            * np.exp(-1j*k*z) * -np.expm1(-1j*k*difference))


def bending_stiffness(thickness_m, young_modulus_pa, poisson_ratio):
    if thickness_m <= 0 or young_modulus_pa <= 0 or not -1 < poisson_ratio < 0.5:
        raise ValueError("Invalid homogeneous plate properties")
    return young_modulus_pa * thickness_m**3 / (12 * (1 - poisson_ratio**2))


def plate_frequency(thickness_m, radius_m, young_modulus_pa, poisson_ratio, density_kg_m3):
    if radius_m <= 0 or density_kg_m3 <= 0:
        raise ValueError("Invalid plate radius or density")
    stiffness = bending_stiffness(thickness_m, young_modulus_pa, poisson_ratio)
    return 10.2158 / (2*np.pi*radius_m**2) * np.sqrt(stiffness/(density_kg_m3*thickness_m))
