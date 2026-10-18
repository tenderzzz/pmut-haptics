import json
import subprocess
from dataclasses import replace

import numpy as np
import pytest
from test_html import browser

from pmut_haptics.acoustics import array_positions, field_pressure, focusing_weights
from pmut_haptics.config import SimulationConfig
from pmut_haptics.imperfections import PortableRandom, generate_sample
from pmut_haptics.simulation import simulate
from pmut_haptics.tasks import aggregate, batch, quality, reference_check, save_task, sweep_config


def small(**kwargs):
    c = SimulationConfig()
    return replace(c, array=replace(c.array, nx=4, ny=4),
                   grid=replace(c.grid, nx=21, ny=21, nz=23), **kwargs)


def test_portable_rng_known_vector_and_cross_language():
    random = PortableRandom(42)
    values = [random.uniform() for _ in range(8)]
    assert values[0] == (11355432 + .5)/4294967296
    assert values == browser({"operation": "random", "seed": 42})


@pytest.mark.parametrize("seed", [0, 42, 4294967295])
def test_samples_and_nonideal_fields_match_browser(seed):
    c = small()
    c = replace(c, seed=seed, array=replace(c.array, phase_error_std_deg=12, apodization="hann",
                                         pitch_mode="physical", pitch_m=.0018),
                focus=replace(c.focus, x_m=.003, y_m=-.002),
                imperfections=replace(c.imperfections, amplitude_cv=.15, position_std_m=15e-6,
                                      failure_probability=.2, phase_bits=4))
    sample = generate_sample(c)
    js = browser({"operation": "sample", "config": c.to_dict()})
    for key in ("phase_rad", "amplitude_gain", "offsets_m", "active"):
        np.testing.assert_allclose(js[key], sample[key], rtol=2e-13, atol=1e-15)
    result = simulate(c, sample)
    actual = browser({"operation": "simulate", "config": c.to_dict(), "sample": sample})
    field = np.array(actual["field"]["re"]) + 1j*np.array(actual["field"]["im"])
    np.testing.assert_allclose(field.reshape(c.grid.ny, c.grid.nx),
                               result.arrays["pressure_xy_peak_pa"], rtol=1e-10, atol=1e-10)
    np.testing.assert_allclose(actual["metrics"]["target_pressure_rms_pa"],
                               result.metrics["target_pressure_rms_pa"], rtol=1e-10)
    np.testing.assert_allclose(actual["metrics"]["sum_squared_velocity_m2_s2"],
                               result.metrics["sum_squared_velocity_m2_s2"], rtol=1e-12)


def test_old_configs_preserve_legacy_phase_samples():
    c = SimulationConfig.from_dict({"array": {"nx": 3, "ny": 3, "phase_error_std_deg": 10}})
    assert c.schema_version == 1 and c.imperfections.rng == "legacy"
    np.testing.assert_array_equal(generate_sample(c)["phase_rad"],
                                  np.random.default_rng(42).normal(0, np.deg2rad(10), 9))


def test_quantization_bound_and_no_position_compensation():
    c = small()
    p = array_positions(c)
    ideal = focusing_weights(p, [.002, .001, .05], c)
    for bits in (3, 4, 6, 8):
        q = replace(c, imperfections=replace(c.imperfections, phase_bits=bits))
        actual = focusing_weights(p, [.002, .001, .05], q)
        assert np.max(abs(np.angle(actual/ideal))) <= np.pi/(2**bits)+1e-12
    e = replace(c, imperfections=replace(c.imperfections, position_std_m=30e-6))
    sample = generate_sample(e)
    result = simulate(e, sample)
    # The weights are computed using the nominal geometry, never actual positions.
    np.testing.assert_allclose(result.arrays["velocity_weights_m_s"],
                               focusing_weights(p, [0, 0, .05], e, sample))
    actual_positions = result.arrays["element_positions_m"]
    expected = field_pressure(np.array([[0, 0, .05]]), actual_positions,
                             result.arrays["velocity_weights_m_s"], e)
    assert result.metrics["target_pressure_rms_pa"] == pytest.approx(abs(expected[0])/np.sqrt(2))


def test_failure_and_overlap_are_explicit():
    c = small()
    dead = replace(c, imperfections=replace(c.imperfections, failure_probability=1))
    result = simulate(dead)
    assert not np.any(result.arrays["pressure_xy_peak_pa"])
    assert result.metrics["target_lateral_error_m"] is None
    sample = generate_sample(c)
    sample["offsets_m"][1] = [-c.pitch_m, 0, 0]
    with pytest.raises(ValueError, match="overlap"):
        simulate(c, sample)


def test_sweep_pitch_normalization_invalid_rows_and_cancel():
    c = small()
    spec = {"parameter": "carrier_hz"}
    for frequency in (80000, 120000):
        q = sweep_config(c, spec, frequency)
        assert q.pitch_m == c.pitch_m and q.array.pitch_mode == "physical"
    q = sweep_config(c, {"parameter": "array.side"}, 8)
    assert q.element.velocity_peak_m_s**2*64 == pytest.approx(c.element.velocity_peak_m_s**2*16)
    task = {"schema_version": 1, "kind": "sweep", "config": c.to_dict(),
            "parameter": "array.side", "values": [3, -1, 5]}
    result = batch(task)
    assert [r["status"] for r in result["rows"]] == ["ok", "invalid", "ok"]
    js = browser({"operation": "batch", "task": task})
    assert [r["status"] for r in js["rows"]] == ["ok", "invalid", "ok"]
    seen = []
    partial = batch(task, on_row=seen.append, should_stop=lambda: bool(seen))
    assert len(partial["rows"]) == 1 and partial["status"] == "cancelled"


def test_wavelength_sweep_from_physical_base():
    c = small()
    c = replace(c, array=replace(c.array, pitch_mode="physical", pitch_m=.0018))
    task = {"schema_version": 1, "kind": "sweep", "config": c.to_dict(),
            "parameter": "carrier_hz", "frequency_pitch": "wavelength", "values": [80000]}
    expected = c.pitch_m * c.carrier_hz / 80000
    assert sweep_config(c, task, 80000).pitch_m == pytest.approx(expected)
    js = browser({"operation": "batch", "task": task})
    assert js["rows"][0]["pitch_m"] == pytest.approx(expected)


def test_paired_robustness_statistics_and_export(tmp_path):
    c = small()
    c = replace(c, imperfections=replace(c.imperfections, amplitude_cv=.1, failure_probability=.1))
    task = {"schema_version": 1, "kind": "robustness", "config": c.to_dict(),
            "count": 3, "quantization_comparison": True}
    result = save_task(task, tmp_path/"runs")
    assert len(result["rows"]) == 15
    assert all(r["sample"] == result["rows"][0]["sample"] for r in result["rows"][:5])
    js = browser({"operation": "batch", "task": task})
    for bits in result["statistics"]:
        for key in result["statistics"][bits]:
            a, b = result["statistics"][bits][key], js["statistics"][bits][key]
            assert a["missing"] == b["missing"]
            for quantile in ("median", "p5", "p95"):
                if a[quantile] is None:
                    assert b[quantile] is None
                else:
                    assert b[quantile] == pytest.approx(a[quantile], rel=1e-9, abs=1e-12)
    assert len((tmp_path/"runs"/"rows.jsonl").read_text().splitlines()) == 15
    assert (tmp_path/"runs"/"manifest.json").exists()
    missing = aggregate([{"status": "invalid"}, {"status": "ok", "metrics": {}}])
    assert all(v["valid"] == 0 and v["median"] is None for v in missing.values())


def test_quality_budgets_zero_clipping_reference_and_browser():
    c = small()
    report = quality(c, reference=True)
    assert report["checks"]["reference"]["status"] == "pass"
    js = browser({"operation": "quality", "config": c.to_dict()})
    for group in ("grid", "region"):
        for key in report["checks"][group]:
            assert js["checks"][group][key]["status"] == report["checks"][group][key]["status"]
    skipped = quality(c, max_plane_points=10)
    assert skipped["checks"]["grid"]["status"] == "unchecked"
    assert skipped["checks"]["region"]["status"] == "unchecked"
    zero = quality(replace(c, element=replace(c.element, velocity_peak_m_s=0)), reference=True)
    assert zero["checks"]["grid"]["pressure_rms_max_pa"]["status"] == "unevaluable"
    assert zero["checks"]["reference"]["status"] == "unevaluable"
    narrow = replace(c, grid=replace(c.grid, x_min_m=-.0001, x_max_m=.0001))
    assert quality(narrow)["checks"]["pressure_x_minus6db"]["clipped"]
    lossy = replace(c, medium=replace(c.medium, attenuation_np_m=.1))
    assert reference_check(lossy, generate_sample(lossy))["status"] == "unchecked"


def test_unconverged_reference_not_reported_as_pass(monkeypatch):
    import pmut_haptics.tasks as tasks
    c = small()
    original = tasks.rayleigh_disk
    def inconsistent(*args, **kwargs):
        return original(*args, **kwargs)*(1 if kwargs["radial_order"] == 48 else .8)
    monkeypatch.setattr(tasks, "rayleigh_disk", inconsistent)
    r = reference_check(c, generate_sample(c))
    assert r["status"] == "unchecked" and r["reason"] == "reference not converged"


def test_experiment_backup_contains_computed_config_and_no_trajectory_frames():
    c = small()
    result = browser({"operation": "library", "config": c.to_dict()})
    assert result["restored"] == 1 and result["duplicates"] == 0
    record = result["record"]
    assert record["snapshot"]["config"] == c.to_dict()
    assert "frames" not in record["snapshot"]["trajectory"]
    assert "wave" not in record["snapshot"]
    assert "sample" in record["snapshot"]


@pytest.mark.parametrize("kind", ["sweep", "robustness"])
def test_cli_task_output(kind, tmp_path):
    task = {"schema_version": 1, "kind": kind, "config": small().to_dict(),
            "parameter": "element.velocity_peak_m_s", "values": [.5, 1], "count": 2}
    source = tmp_path/"task.json"
    source.write_text(json.dumps(task))
    import os
    import sys
    env = dict(os.environ, PYTHONPATH="src")
    run = subprocess.run([sys.executable, "-m", "pmut_haptics.cli", kind, "--task", str(source),
                          "--output", str(tmp_path/"out")], env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads((tmp_path/"out"/"results.json").read_text())["status"] == "complete"
