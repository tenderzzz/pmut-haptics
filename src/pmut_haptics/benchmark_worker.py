"""Fresh process benchmark worker; used by pmut-haptics benchmark."""
import json
import resource
import statistics
import sys
from dataclasses import replace
from time import perf_counter

import numpy as np

from .acoustics import array_positions, field_pressure, focus_point, focusing_weights
from .config import SimulationConfig


def main():
    side, grid, backend, repeats = sys.argv[1:]
    side, grid, repeats = int(side), int(grid), int(repeats)
    base = SimulationConfig()
    config = replace(base, array=replace(base.array, nx=side, ny=side))
    positions = array_positions(config)
    weights = focusing_weights(positions, focus_point(config), config)
    axis = np.linspace(-.02, .02, grid)
    x, y = np.meshgrid(axis, axis)
    points = np.column_stack((x.ravel(), y.ravel(), np.full(x.size, .05)))
    result = field_pressure(points, positions, weights, config, backend)
    samples = []
    for _ in range(repeats):
        start = perf_counter()
        result = field_pressure(points, positions, weights, config, backend)
        samples.append(perf_counter()-start)
    # A sparse, identical-model check is excluded from timed work.
    check = field_pressure(points[::max(1, len(points)//31)], positions, weights, config, "reference")
    actual = result[::max(1, len(points)//31)]
    error = float(np.linalg.norm(actual-check)/max(np.linalg.norm(check), 1e-300))
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform != "darwin":
        rss *= 1024
    print(json.dumps({"samples_seconds": samples, "median_seconds": statistics.median(samples),
                      "min_seconds": min(samples), "max_seconds": max(samples),
                      "peak_rss_bytes": rss, "relative_l2_error": error,
                      "output_shape": list(result.shape)}))


if __name__ == "__main__":
    main()
