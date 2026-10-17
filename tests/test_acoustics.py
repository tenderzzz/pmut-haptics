from dataclasses import replace

import numpy as np

from pmut_haptics.acoustics import (
    array_positions,
    axis_pressure,
    field_frames,
    field_pressure,
    focus_point,
    focusing_weights,
    piston_transfer,
    plate_frequency,
    rayleigh_disk,
    transfer_from_config,
)
from pmut_haptics.config import SimulationConfig


def test_phase_correction_preserves_amplitude_and_aligns_at_focus():
    c = SimulationConfig()
    positions = array_positions(c)
    weights = focusing_weights(positions, focus_point(c), c)
    np.testing.assert_allclose(abs(weights), c.element.velocity_peak_m_s, rtol=1e-14)
    contributions = transfer_from_config(focus_point(c)[None, :], positions, c)[0]*weights
    np.testing.assert_allclose(abs(contributions.sum()), abs(contributions).sum(), rtol=1e-13)


def test_polar_integral_matches_on_axis_solution_and_symmetry():
    z = np.geomspace(.0002, .05, 17)
    points = np.column_stack((np.zeros_like(z), np.zeros_like(z), z))
    numerical = rayleigh_disk(points, .001, 7550, 1000, 1480, radial_order=40, angular_order=96)
    exact = axis_pressure(z, .001, 7550, 1000, 1480)
    np.testing.assert_allclose(numerical, exact, rtol=1e-10, atol=1e-10)
    mirrored = np.array([[-.001, 0, .0005], [.001, 0, .0005], [0, .001, .0005]])
    value = rayleigh_disk(mirrored, .001, 7550, 1000, 1480, radial_order=40, angular_order=128)
    np.testing.assert_allclose(value, value[0], rtol=1e-10)


def test_far_field_approximation_has_quantified_error():
    points = np.array([[0, 0, .02], [.01, 0, .03], [0, -.01, .05]])
    exact = rayleigh_disk(points, .000415, 109400, 1.2, 343, radial_order=40, angular_order=96)
    fast = piston_transfer(points, np.zeros((1, 3)), 109400, .000415, 1.2, 343)[:, 0]
    assert np.linalg.norm(fast-exact)/np.linalg.norm(exact) < .01
    coarse = rayleigh_disk(points, .000415, 109400, 1.2, 343, radial_order=12, angular_order=24)
    assert np.linalg.norm(coarse-exact)/np.linalg.norm(exact) < 1e-6


def test_same_kernel_backends_and_reused_geometry_agree():
    c = SimulationConfig()
    c = replace(c, engine=replace(c.engine, chunk_points=11))
    pos = array_positions(c)
    rng = np.random.default_rng(1)
    pts = rng.uniform([-.01, -.01, .02], [.01, .01, .08], size=(41, 3))
    weights = focusing_weights(pos, focus_point(c), c)
    expected = field_pressure(pts, pos, weights, c, "reference")
    np.testing.assert_allclose(field_pressure(pts, pos, weights, c), expected, rtol=1e-12, atol=1e-12)
    shifted = focusing_weights(pos, np.array([.004, 0, .05]), c)
    frames = field_frames(pts, pos, np.column_stack((weights, shifted)), c)
    np.testing.assert_allclose(frames[:, 1], field_pressure(pts, pos, shifted, c), rtol=1e-12)


def test_apodization_preserves_velocity_norm_and_plate_scaling():
    c = SimulationConfig()
    pos = array_positions(c)
    c = replace(c, array=replace(c.array, apodization="hann"))
    weights = focusing_weights(pos, focus_point(c), c)
    np.testing.assert_allclose(np.sum(abs(weights)**2), len(pos), rtol=1e-14)
    f = plate_frequency(55e-6, .001, 70e9, .3, 7800)
    np.testing.assert_allclose(f, 81067.28016712772)
    np.testing.assert_allclose(plate_frequency(110e-6, .001, 70e9, .3, 7800), 2*f)
    np.testing.assert_allclose(plate_frequency(55e-6, .002, 70e9, .3, 7800), f/4)


def test_transfer_memory_budget_applies_to_static_and_moving_fields(monkeypatch):
    import pmut_haptics.acoustics as acoustics

    c = SimulationConfig()
    c = replace(c, engine=replace(c.engine, chunk_points=2048, max_transfer_mb=.03))
    pos = array_positions(c)
    weights = focusing_weights(pos, focus_point(c), c)
    points = np.column_stack((np.linspace(-.01, .01, 15), np.zeros(15), np.full(15, .05)))
    expected = field_pressure(points, pos, weights, c, "reference")
    calls = []
    original = acoustics.transfer_from_config

    def record_block(points, positions, config):
        calls.append(len(points))
        return original(points, positions, config)

    monkeypatch.setattr(acoustics, "transfer_from_config", record_block)
    actual = field_pressure(points, pos, weights, c)
    frames = field_frames(points, pos, weights[:, None], c)
    assert max(calls) <= 2
    np.testing.assert_allclose(actual, expected, rtol=1e-12)
    np.testing.assert_allclose(frames[:, 0], expected, rtol=1e-12)
