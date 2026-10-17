"""Shared application layer used by both the CLI and the interactive app."""
from dataclasses import dataclass
from time import perf_counter

import numpy as np

from .acoustics import (
    array_positions,
    field_frames,
    field_pressure,
    focus_point,
    focusing_weights,
    transfer_from_config,
)
from .config import SimulationConfig
from .metrics import plane_force, plane_metrics, stimulus
from .stimulation import focal_trajectory, waveform


@dataclass
class SimulationResult:
    config: SimulationConfig
    arrays: dict[str, np.ndarray]
    metrics: dict


def simulate(config: SimulationConfig) -> SimulationResult:
    config.validate()
    started = perf_counter()
    positions = array_positions(config)
    weights = focusing_weights(positions, focus_point(config), config)
    g = config.grid
    xs = np.linspace(g.x_min_m, g.x_max_m, g.nx)
    ys = np.linspace(g.y_min_m, g.y_max_m, g.ny)
    zs = np.linspace(g.z_min_m, g.z_max_m, g.nz)
    xx, yy = np.meshgrid(xs, ys, indexing="xy")
    surface = np.column_stack((xx.ravel(), yy.ravel(), np.full(xx.size, config.focus.z_m)))
    xz_x, xz_z = np.meshgrid(xs, zs, indexing="xy")
    section = np.column_stack((xz_x.ravel(), np.full(xz_x.size, config.focus.y_m),
                               xz_z.ravel()))
    pressure = field_pressure(surface, positions, weights, config).reshape(g.ny, g.nx)
    pressure_xz = field_pressure(section, positions, weights, config).reshape(g.nz, g.nx)
    metrics = plane_metrics(pressure, xs, ys, config)
    rms, intensity, radiation = stimulus(pressure, config.medium.density_kg_m3,
                                        config.medium.sound_speed_m_s, config.reflection_factor)
    times, envelope = waveform(config.modulation)
    path_times, path = focal_trajectory(config)
    frame_weights = np.column_stack([focusing_weights(positions, p, config) for p in path])
    if len(path) == 1:
        frames_radiation = radiation[None, ...]
    else:
        frame_pressure = field_frames(surface, positions, frame_weights, config)
        frames_radiation = stimulus(frame_pressure, config.medium.density_kg_m3,
                                    config.medium.sound_speed_m_s, config.reflection_factor)[2]
        frames_radiation = frames_radiation.T.reshape(len(path), g.ny, g.nx)
    commanded_pressure = np.einsum(
        "ij,ji->i", transfer_from_config(path, positions, config), frame_weights
    )
    commanded_radiation = stimulus(commanded_pressure, config.medium.density_kg_m3,
                                   config.medium.sound_speed_m_s, config.reflection_factor)[2]
    frame_force = plane_force(frames_radiation, xs, ys)
    if len(path) > 1:
        # Periodic trajectory; interpolate only slow geometry response.
        motion_time = times % config.trajectory.duration_s
        focal_baseline = np.interp(motion_time, path_times, commanded_radiation)
        force_baseline = np.interp(motion_time, path_times, frame_force)
        mean_motion = np.trapezoid(frames_radiation, x=path_times, axis=0) / path_times[-1]
    else:
        focal_baseline = np.full_like(times, commanded_radiation[0])
        force_baseline = np.full_like(times, frame_force[0])
        mean_motion = radiation
    arrays = {
        "element_positions_m": positions, "velocity_weights_m_s": weights,
        "x_m": xs, "y_m": ys, "z_m": zs,
        "pressure_xy_peak_pa": pressure, "pressure_xz_peak_pa": pressure_xz,
        "pressure_xy_rms_pa": rms, "intensity_xy_w_m2": intensity,
        "radiation_xy_pa": radiation,
        "time_s": times, "envelope": envelope,
        "commanded_focus_radiation_pa": focal_baseline*envelope**2,
        "plane_force_time_n": force_baseline*envelope**2,
        "trajectory_time_s": path_times, "trajectory_points_m": path,
        "trajectory_radiation_pa": frames_radiation,
        "trajectory_mean_unmodulated_radiation_pa": mean_motion,
    }
    metrics.update({
        "element_count": len(positions), "pitch_m": config.pitch_m,
        "wavelength_m": config.wavelength_m,
        "sum_squared_velocity_m2_s2": float(np.sum(abs(weights)**2)),
        "envelope_mean_square": float(np.mean(envelope**2)),
        "commanded_focus_radiation_time_peak_pa": float(np.max(focal_baseline*envelope**2)),
        "plane_force_time_mean_n": float(np.mean(force_baseline*envelope**2)),
        "simulation_seconds": perf_counter()-started,
        "model": "uniform baffled piston; element far-field approximation; normal-incidence force",
        "amplitude_basis": "assumed peak surface velocity; not voltage calibrated",
        "motion_map_basis": "carrier averaged, unmodulated; separate waveform applies envelope squared",
    })
    return SimulationResult(config, arrays, metrics)
