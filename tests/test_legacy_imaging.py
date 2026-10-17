import numpy as np

from pmut_haptics.imaging import EchoData, delay_and_sum, simulate_echoes
from pmut_haptics.legacy import original_results


def test_historical_table_is_reproduced_and_known_defects_are_identified():
    metrics, arrays = original_results()
    expected = [[54.43037974683544, 50.88607594936709],
                [29.113924050632907, 40.25316455696203],
                [29.113924050632907, 40.25316455696203],
                [49.36708860759494, 38.734177215189874],
                [49.36708860759494, 38.734177215189874]]
    actual = [[r["lateral_mm"], r["axial_mm"]] for r in metrics["image_widths"]]
    np.testing.assert_allclose(actual, expected, atol=1e-10)
    assert arrays["rf_data"].shape == (8, 8, 148)
    assert metrics["diagnostics"]["echo_centers_after_record"] == 34
    assert metrics["diagnostics"]["outer_element_weight_magnitude"] < .001
    assert metrics["diagnostics"]["symmetric_point_pressure_ratio"] > 2.8


def test_echo_window_covers_geometry_and_is_reciprocal():
    ax = np.linspace(-.1, .1, 8)
    scatterers = np.array([[.015, .06]])
    echo = simulate_echoes(ax, scatterers, [1.])
    max_path = 2*np.hypot(ax-scatterers[0, 0], scatterers[0, 1]).max()/1480
    assert echo.time_s[-1] > max_path + 2*echo.pulse_center_s
    np.testing.assert_allclose(echo.signals, echo.signals.swapaxes(0, 1))


def test_analytic_das_nonzero_at_echo_center_and_time_origin_invariant():
    ax = np.linspace(-.015, .015, 8)
    echo = simulate_echoes(ax, np.array([[0, .04]]), [1.], cycles_fwhm=1)
    x, z = np.linspace(-.006, .006, 31), np.linspace(.036, .044, 41)
    image = delay_and_sum(echo, ax, x, z)
    assert image[20, 15] > .8*image.max()
    shift = .002
    shifted = EchoData(echo.signals, echo.time_s+shift, echo.sample_rate_hz,
                       echo.pulse_center_s+shift)
    np.testing.assert_allclose(delay_and_sum(shifted, ax, x, z), image, rtol=1e-11, atol=1e-12)
