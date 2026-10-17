"""Generate independently checkable numerical validation evidence."""
import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from pmut_haptics.acoustics import (
    array_positions,
    axis_pressure,
    field_pressure,
    focus_point,
    focusing_weights,
    piston_transfer,
    rayleigh_disk,
)
from pmut_haptics.config import SimulationConfig
from pmut_haptics.export import environment

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)

def relative(a, b):
    return float(np.linalg.norm(a-b)/np.linalg.norm(b))

z = np.geomspace(.0002, .05, 31)
points = np.column_stack((np.zeros_like(z), np.zeros_like(z), z))
exact = axis_pressure(z, .001, 7550, 1000, 1480)
numeric = rayleigh_disk(points, .001, 7550, 1000, 1480, radial_order=40, angular_order=96)
air_points = np.array([[0, 0, .02], [.01, 0, .03], [0, -.01, .05]])
air_exact = rayleigh_disk(air_points, .000415, 109400, 1.2, 343, radial_order=40, angular_order=96)
air_coarse = rayleigh_disk(air_points, .000415, 109400, 1.2, 343, radial_order=12, angular_order=24)
air_fast = piston_transfer(air_points, np.zeros((1, 3)), 109400, .000415, 1.2, 343)[:, 0]
config = SimulationConfig()
config = replace(config, engine=replace(config.engine, chunk_points=7))
positions = array_positions(config)
weights = focusing_weights(positions, focus_point(config), config)
rng = np.random.default_rng(42)
sample = rng.uniform([-.02, -.02, .02], [.02, .02, .08], size=(100, 3))
reference = field_pressure(sample, positions, weights, config, "reference")
optimized = field_pressure(sample, positions, weights, config)
report = {
    "axis_quadrature_relative_l2_error": relative(numeric, exact),
    "air_quadrature_convergence_relative_l2_error": relative(air_coarse, air_exact),
    "air_far_field_approximation_relative_l2_error": relative(air_fast, air_exact),
    "same_model_backend_relative_l2_error": relative(optimized, reference),
    "validation_points_m": air_points.tolist(),
    "quadrature_orders": {"coarse": [12, 24], "reference": [40, 96]},
    "limits": {"axis": 1e-9, "quadrature_convergence": 1e-6,
               "air_approximation": .01, "same_model": 1e-12},
    "environment": environment(),
}
assert report["axis_quadrature_relative_l2_error"] < 1e-9
assert report["air_quadrature_convergence_relative_l2_error"] < 1e-6
assert report["air_far_field_approximation_relative_l2_error"] < .01
assert report["same_model_backend_relative_l2_error"] < 1e-12
report["passed"] = True
(args.output/"validation.json").write_text(json.dumps(report, indent=2)+"\n")
print(json.dumps({k: v for k, v in report.items() if k.endswith("error")}, indent=2))
