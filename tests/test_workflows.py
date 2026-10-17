import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from pmut_haptics.config import SimulationConfig, load_config
from pmut_haptics.export import save_result
from pmut_haptics.simulation import simulate


def quick_config():
    c = SimulationConfig()
    return replace(c, array=replace(c.array, nx=8, ny=8),
                   grid=replace(c.grid, nx=41, ny=41, nz=41))


def test_static_focus_determinism_and_export_roundtrip(tmp_path):
    c = quick_config()
    first, second = simulate(c), simulate(c)
    np.testing.assert_array_equal(first.arrays["pressure_xy_peak_pa"],
                                  second.arrays["pressure_xy_peak_pa"])
    assert first.metrics["target_lateral_error_m"] < .0011
    output = save_result(first, tmp_path/"run", plots=False)
    assert load_config(output/"config.toml") == c
    archive = np.load(output/"arrays.npz")
    np.testing.assert_array_equal(archive["pressure_xy_peak_pa"],
                                  first.arrays["pressure_xy_peak_pa"])
    manifest = json.loads((output/"manifest.json").read_text())
    for name, digest in manifest["files_sha256"].items():
        assert hashlib.sha256((output/name).read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        save_result(first, output, plots=False)


def test_zero_velocity_and_moving_focus():
    c = quick_config()
    zero = simulate(replace(c, element=replace(c.element, velocity_peak_m_s=0)))
    assert zero.metrics["spl_db_re_20uPa"] is None
    assert zero.metrics["pressure_x_minus6db"]["reason"] == "zero_signal"
    c = replace(c, trajectory=replace(c.trajectory, kind="circle", frames=25))
    result = simulate(c)
    frames = result.arrays["trajectory_radiation_pa"]
    for frame, target in zip(frames, result.arrays["trajectory_points_m"], strict=True):
        iy, ix = np.unravel_index(frame.argmax(), frame.shape)
        point = np.array([result.arrays["x_m"][ix], result.arrays["y_m"][iy]])
        assert np.linalg.norm(point-target[:2]) <= .0015


def test_cli_help_and_invalid_config_exit(tmp_path):
    help_run = subprocess.run([sys.executable, "-m", "pmut_haptics.cli", "--help"],
                              capture_output=True, text=True)
    assert help_run.returncode == 0
    assert "reproduce" in help_run.stdout
    bad = tmp_path/"bad.toml"
    bad.write_text("carrier_hz = -1\n")
    result = subprocess.run([sys.executable, "-m", "pmut_haptics.cli", "run",
                             "--config", str(bad), "--output", str(tmp_path/"bad-output")],
                             capture_output=True, text=True)
    assert result.returncode == 2
    assert not (tmp_path/"bad-output").exists()


def test_all_checked_in_presets_validate():
    for path in (Path(__file__).parents[1]/"configs").glob("*.toml"):
        load_config(path).validate()
