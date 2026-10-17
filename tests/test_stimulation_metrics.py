from dataclasses import replace

import numpy as np

from pmut_haptics.config import Modulation, SimulationConfig
from pmut_haptics.metrics import connected_width, plane_force, stimulus
from pmut_haptics.stimulation import focal_trajectory, waveform


def test_width_measures_connected_main_lobe_not_separate_satellite():
    x = np.linspace(-8, 8, 16001)
    signal = np.exp(-x*x/2) + .8*np.exp(-(x-5)**2/.08)
    result = connected_width(x, signal)
    expected = 2*np.sqrt(2*np.log(10**(6/20)))
    assert abs(result["width_m"]-expected) < .001
    assert not result["clipped"]
    assert connected_width(x, np.ones_like(x))["width_m"] is None
    assert connected_width(x, np.ones_like(x))["clipped"]
    assert connected_width(x, np.zeros_like(x))["reason"] == "zero_signal"


def test_radiation_scaling_and_finite_plane_integral():
    p = np.array([100.0+0j, 200.0+0j])
    rms, intensity, radiation = stimulus(p, 1.2, 343)
    np.testing.assert_allclose(rms, abs(p)/np.sqrt(2))
    np.testing.assert_allclose(radiation, abs(p)**2/(1.2*343**2))
    np.testing.assert_allclose(radiation[1]/radiation[0], 4)
    np.testing.assert_allclose(intensity, rms**2/(1.2*343))
    x = np.linspace(-.02, .02, 11)
    np.testing.assert_allclose(plane_force(np.full((11, 11), 2.), x, x), .0032)


def test_envelope_squared_has_correct_average_and_harmonic():
    t, m = waveform(Modulation())
    np.testing.assert_allclose(np.mean(m*m), .5, atol=1e-14)
    t, m = waveform(Modulation(kind="sinusoidal", frequency_hz=100, duration_s=.1))
    np.testing.assert_allclose(np.mean(m*m), .375, atol=1e-14)
    spectrum = abs(np.fft.rfft(m*m))/len(m)
    frequency = np.fft.rfftfreq(len(m), t[1]-t[0])
    first, second = np.argmin(abs(frequency-100)), np.argmin(abs(frequency-200))
    np.testing.assert_allclose(spectrum[second]/spectrum[first], .25, atol=1e-12)


def test_trajectory_is_periodic_and_within_requested_radius():
    c = SimulationConfig()
    c = replace(c, trajectory=replace(c.trajectory, kind="circle"))
    times, points = focal_trajectory(c)
    np.testing.assert_allclose(points[0], points[-1], atol=1e-15)
    np.testing.assert_allclose(np.linalg.norm(points[:, :2], axis=1), .005)
    assert times[-1] == 1
