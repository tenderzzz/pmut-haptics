import tomllib
from dataclasses import replace

import pytest

from pmut_haptics.config import SimulationConfig, to_toml


def test_toml_roundtrip_and_unknown_keys():
    config = SimulationConfig()
    assert SimulationConfig.from_dict(tomllib.loads(to_toml(config))) == config
    with pytest.raises(ValueError, match="Unknown"):
        SimulationConfig.from_dict({"carrier_hzz": 100000})


@pytest.mark.parametrize("update", [
    {"carrier_hz": float("nan")}, {"carrier_hz": True},
    {"carrier_hz": 1000}, {"array": {"nx": 0}}, {"array": {"nx": 2.5}},
    {"element": {"radius_m": .01}}, {"focus": {"z_m": 0}},
    {"grid": {"x_min_m": .1}}, {"medium": {"density_kg_m3": -1}},
    {"modulation": {"sample_rate_hz": 10}}, {"reflection_factor": 3},
    {"trajectory": {"kind": "circle", "radius_m": .1}},
])
def test_invalid_physical_inputs_rejected(update):
    with pytest.raises(ValueError):
        SimulationConfig.from_dict(update)


def test_modulation_and_trajectory_bounds():
    base = SimulationConfig()
    with pytest.raises(ValueError):
        replace(base, trajectory=replace(base.trajectory, kind="circle", loops=10)).validate()


def test_large_trajectory_is_rejected_before_allocation():
    with pytest.raises(ValueError, match="ten million"):
        SimulationConfig.from_dict({
            "grid": {"nx": 501, "ny": 501},
            "trajectory": {"kind": "circle", "frames": 501},
        })
