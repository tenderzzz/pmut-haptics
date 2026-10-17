"""Independent browser-kernel checks against the existing Python implementation."""
import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from scipy.special import j1

from pmut_haptics.config import SimulationConfig, to_toml
from pmut_haptics.simulation import simulate

ROOT = Path(__file__).parents[1]
NODE = shutil.which("node")


def browser(request):
    if NODE is None:
        pytest.skip("Node is required for browser-kernel parity tests")
    run = subprocess.run(
        [NODE, str(ROOT / "tests/browser_probe.cjs")],
        input=json.dumps(request), capture_output=True, text=True, check=True,
    )
    return json.loads(run.stdout)


@pytest.mark.parametrize("scenario", ["default", "hann_offaxis", "zero", "sinusoidal", "line", "circle"])
def test_browser_matches_python_physics(scenario):
    c = SimulationConfig()
    c = replace(c, grid=replace(c.grid, nx=31, ny=31, nz=35),
                array=replace(c.array, nx=8, ny=8))
    if scenario == "hann_offaxis":
        c = replace(c, focus=replace(c.focus, x_m=.004, y_m=-.003),
                    array=replace(c.array, apodization="hann"),
                    medium=replace(c.medium, attenuation_np_m=.3))
    elif scenario == "zero":
        c = replace(c, element=replace(c.element, velocity_peak_m_s=0))
    elif scenario == "sinusoidal":
        c = replace(c, modulation=replace(c.modulation, kind="sinusoidal", depth=.7))
    elif scenario in {"line", "circle"}:
        c = replace(c, trajectory=replace(c.trajectory, kind=scenario, frames=25),
                    modulation=replace(c.modulation, duration_s=1))
    expected = simulate(c)
    actual = browser({"operation": "simulate", "config": c.to_dict()})
    f, a = actual["field"], expected.arrays
    complex_pressure = np.array(f["re"]) + 1j * np.array(f["im"])
    np.testing.assert_allclose(complex_pressure.reshape(c.grid.ny, c.grid.nx),
                               a["pressure_xy_peak_pa"], rtol=1e-10, atol=1e-10)
    np.testing.assert_allclose(np.array(f["xzRms"]).reshape(c.grid.nz, c.grid.nx),
                               abs(a["pressure_xz_peak_pa"])/np.sqrt(2), rtol=1e-10, atol=1e-10)
    for name, expected_name in [("rms", "pressure_xy_rms_pa"), ("radiation", "radiation_xy_pa")]:
        np.testing.assert_allclose(np.array(f[name]).reshape(c.grid.ny, c.grid.nx),
                                   a[expected_name], rtol=1e-10, atol=1e-12)
    frames = np.array(actual["trajectory"]["frames"]).reshape(a["trajectory_radiation_pa"].shape)
    np.testing.assert_allclose(frames, a["trajectory_radiation_pa"], rtol=1e-10, atol=1e-12)
    np.testing.assert_allclose(actual["wave"]["force"], a["plane_force_time_n"], rtol=1e-10, atol=1e-14)
    np.testing.assert_allclose(actual["wave"]["focusRadiation"], a["commanded_focus_radiation_pa"],
                               rtol=1e-10, atol=1e-12)
    for key in ["pressure_rms_max_pa", "radiation_pressure_max_pa", "force_over_displayed_plane_n",
                "envelope_mean_square", "plane_force_time_mean_n", "sidelobe_x_db", "sidelobe_y_db"]:
        if expected.metrics[key] is None:
            assert actual["metrics"][key] is None
        else:
            np.testing.assert_allclose(actual["metrics"][key], expected.metrics[key], rtol=1e-10, atol=1e-12)
    for key in ["pressure_x_minus6db", "pressure_y_minus6db", "radiation_x_fwhm"]:
        e, v = expected.metrics[key], actual["metrics"][key]
        assert e["reason"] == v["reason"]
        if e["width_m"] is not None:
            np.testing.assert_allclose(v["width_m"], e["width_m"], atol=1e-12)


def test_browser_jinc_series_against_scipy():
    x = np.linspace(0, np.pi, 1001)
    expected = np.ones_like(x)
    expected[1:] = 2*j1(x[1:])/x[1:]
    actual = browser({"operation": "jinc", "points": x.tolist()})
    np.testing.assert_allclose(actual, expected, rtol=1e-14, atol=1e-14)


def test_python_toml_import_and_invalid_configuration():
    c = SimulationConfig()
    parsed = browser({"operation": "parse", "text": to_toml(c)})
    assert parsed == c.to_dict()
    failures = browser({"operation": "validate", "cases": [
        {"carrier_hz": -1}, {"array": {"nx": 0}}, {"element": {"radius_m": .1}},
        {"array": {"phase_error_std_deg": 10}}, {"trajectory": {"kind": "circle", "radius_m": .1}},
        {"__proto__": {"polluted": True}}, {"grid": {"nx": 5000}}, {"carrier_hz": "100000"},
    ]})
    assert all(failures)


def test_single_html_is_self_contained_and_current():
    from html.parser import HTMLParser

    class AssetParser(HTMLParser):
        resources = []

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag in {"script", "img", "iframe", "audio", "video"} and "src" in values:
                self.resources.append(values["src"])
            if tag == "link" and values.get("rel") == "stylesheet":
                self.resources.append(values.get("href"))

    html = (ROOT/"pmut-haptics.html").read_text()
    assets = AssetParser()
    assets.feed(html)
    assert not assets.resources
    app_source = (ROOT/"web/core.js").read_text() + (ROOT/"web/ui.js").read_text()
    assert "fetch(" not in app_source and "XMLHttpRequest" not in app_source
    assert "connect-src 'none'" in html
    # The embedded Plotly distribution includes unused network-capable chart types.
    # Application code uses only local Scatter3d; CSP denies all network connections.
    assert "Permission is hereby granted, free of charge" in html
    template = (ROOT/"web/template.html").read_text()
    for marker, file in [("/*__STYLE__*/", "style.css"),
                         ("/*__PLOTLY_LICENSE__*/", "vendor/LICENSE-plotly.txt"),
                         ("/*__PLOTLY__*/", "vendor/plotly.min.js"),
                         ("/*__CORE__*/", "core.js"),
                         ("/*__UI__*/", "ui.js")]:
        template = template.replace(marker, (ROOT/"web"/file).read_text())
    assert html == template

def test_default_html_numbers_satisfy_native_input_constraints():
    from decimal import Decimal
    from html.parser import HTMLParser

    class Inputs(HTMLParser):
        fields = []

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag == "input" and values.get("type") == "number" and "value" in values:
                self.fields.append(values)

    parsed = Inputs()
    parsed.feed((ROOT / "web/template.html").read_text())
    for field in parsed.fields:
        value = Decimal(field["value"])
        if "min" in field:
            assert value >= Decimal(field["min"]), field["id"]
        if "max" in field:
            assert value <= Decimal(field["max"]), field["id"]
        if field.get("step", "1") != "any":
            base = Decimal(field.get("min", field["value"]))
            assert (value-base) % Decimal(field.get("step", "1")) == 0, field["id"]
