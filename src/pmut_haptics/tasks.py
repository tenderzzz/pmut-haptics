"""Portable batch tasks and diagnostic reports, independent of the interactive UI."""
import copy
import csv
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from .acoustics import array_positions, field_pressure, focus_point, focusing_weights, rayleigh_disk
from .config import Imperfections, SimulationConfig
from .export import environment, save_json
from .imperfections import generate_sample, validate_sample
from .simulation import simulate

MODEL_VERSION = "2.0"
METRICS = ("target_pressure_rms_pa", "pressure_rms_max_pa", "target_lateral_error_m",
           "pressure_x_minus6db_m", "sidelobe_x_db", "force_over_displayed_plane_n")
PARAMETERS = ("carrier_hz", "focus.z_m", "array.side", "array.pitch_m",
              "array.pitch_wavelengths", "element.velocity_peak_m_s")


def summary(metrics):
    return {k: metrics["pressure_x_minus6db"]["width_m"] if k == "pressure_x_minus6db_m"
            else metrics.get(k) for k in METRICS}


def task_config(data):
    c = SimulationConfig.from_dict(data)
    if c.trajectory.kind != "static":
        raise ValueError("Batch/quality tasks require an explicit static configuration copy")
    return c


def sweep_values(spec):
    if spec.get("parameter") not in PARAMETERS:
        raise ValueError("Unsupported sweep parameter")
    values = spec.get("values")
    if values is None:
        count = spec.get("count", 11)
        if isinstance(count, bool) or not isinstance(count, int) or not 2 <= count <= 10000:
            raise ValueError("Sweep count must be 2..10000")
        values = np.linspace(spec["start"], spec["stop"], count).tolist()
    if not isinstance(values, list) or not 1 <= len(values) <= 10000:
        raise ValueError("Sweep requires 1..10000 values")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v)
           for v in values):
        raise ValueError("Sweep values must be finite numbers")
    return values


def sweep_config(base, spec, value):
    data = base.to_dict()
    parameter = spec["parameter"]
    if parameter == "carrier_hz":
        # Sweep a fixed piece of hardware unless explicitly requested otherwise.
        mode = spec.get("frequency_pitch", "physical")
        if mode not in {"physical", "wavelength"}:
            raise ValueError("Unknown frequency pitch mode")
        if mode == "physical":
            data["array"].update(pitch_mode="physical", pitch_m=base.pitch_m)
        else:
            data["array"].update(pitch_mode="wavelength",
                                 pitch_wavelengths=base.pitch_m/base.wavelength_m)
        data["carrier_hz"] = value
    elif parameter == "array.side":
        if value != int(value):
            raise ValueError("Array side must be an integer")
        data["array"].update(nx=int(value), ny=int(value))
    else:
        section, key = parameter.split(".")
        data[section][key] = value
        if parameter.startswith("array.pitch"):
            data["array"]["pitch_mode"] = "physical" if key == "pitch_m" else "wavelength"
    normalization = spec.get("normalization", "fixed_sum_squared_velocity")
    if normalization not in {"fixed_sum_squared_velocity", "per_element"}:
        raise ValueError("Unknown normalization")
    if normalization == "fixed_sum_squared_velocity" and parameter == "array.side":
        n = data["array"]["nx"] * data["array"]["ny"]
        if n <= 0:
            raise ValueError("Array side must be positive")
        data["element"]["velocity_peak_m_s"] *= (base.array.nx * base.array.ny / n)**0.5
    return SimulationConfig.from_dict(data)


def aggregate(rows):
    output = {}
    for key in METRICS:
        values = [r["metrics"][key] for r in rows if r["status"] == "ok"
                  and r["metrics"].get(key) is not None]
        output[key] = {"valid": len(values), "missing": len(rows)-len(values),
                       "median": float(np.median(values)) if values else None,
                       "p5": float(np.percentile(values, 5)) if values else None,
                       "p95": float(np.percentile(values, 95)) if values else None}
    return output


def batch(task, on_row=lambda row: None, should_stop=lambda: False):
    if task.get("schema_version") != 1 or task.get("kind") not in {"sweep", "robustness"}:
        raise ValueError("Expected task schema_version=1 and sweep/robustness kind")
    base = task_config(task["config"])
    result = {"schema_version": 1, "model_version": MODEL_VERSION, "task": copy.deepcopy(task),
              "rows": [], "status": "running", "distribution_note": "sample quantiles, not confidence intervals"}
    kind = task["kind"]
    if kind == "sweep":
        values = sweep_values(task)
        jobs = [(i, value, None) for i, value in enumerate(values)]
    else:
        count = task.get("count", 30)
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 100000:
            raise ValueError("Robustness count must be 1..100000")
        variants = [0, 3, 4, 6, 8] if task.get("quantization_comparison", False) else [base.imperfections.phase_bits]
        jobs = [(i, None, bits) for i in range(count) for bits in variants]
        ideal = replace(base, array=replace(base.array, phase_error_std_deg=0),
                        imperfections=Imperfections())
        result["ideal"] = summary(simulate(ideal).metrics)
    try:
        for i, value, bits in jobs:
            if should_stop():
                result["status"] = "cancelled"
                break
            row = {"index": i, "value": value, "phase_bits": bits}
            try:
                if kind == "sweep":
                    c = sweep_config(base, task, value)
                    sample = generate_sample(c)
                else:
                    c = replace(base, seed=(base.seed+i) % 2**32,
                                imperfections=replace(base.imperfections, rng="portable-v1",
                                                      phase_bits=bits))
                    sample = generate_sample(c)
                row.update(config=c.to_dict(), sample=sample)
                r = simulate(c, sample)
                row.update(status="ok", metrics=summary(r.metrics), pitch_m=c.pitch_m,
                           sum_squared_velocity_m2_s2=r.metrics["sum_squared_velocity_m2_s2"])
            except (ValueError, OverflowError) as exc:
                row.update(status="invalid", reason=str(exc))
            result["rows"].append(row)
            on_row(row)
        else:
            result["status"] = "complete"
    except KeyboardInterrupt:
        result["status"] = "cancelled"
    if kind == "robustness":
        result["statistics"] = {str(b): aggregate([r for r in result["rows"] if r["phase_bits"] == b])
                                for b in variants}
    return result


def _change(before, after, threshold):
    if before is None or after is None or before == 0:
        return {"status": "unevaluable", "reason": "zero baseline or missing/clipped metric",
                "before": before, "after": after}
    change = abs(after-before) / abs(before)
    return {"status": "pass" if change <= threshold else "sensitive",
            "relative_change": change, "threshold": threshold, "before": before, "after": after}


def quality(config, grid_tolerance=.02, region_tolerance=.05, reference=False,
            max_plane_points=100000, max_interactions=35000000):
    config.validate()
    if config.trajectory.kind != "static":
        raise ValueError("Quality checks require an explicit static configuration copy")
    if not (0 < grid_tolerance <= 1 and 0 < region_tolerance <= 1):
        raise ValueError("Quality tolerances must be in (0,1]")
    sample = generate_sample(config)
    base = simulate(config, sample)
    report = {"schema_version": 1, "model_version": MODEL_VERSION, "config": config.to_dict(),
              "sample": sample, "checks": {},
              "model_note": "uniform piston, element far-field; normal-incidence force approximation",
              "input_note": "assumed velocity, not voltage calibrated; no perception validation"}
    g = config.grid
    variants = {
        "grid": replace(g, nx=2*g.nx-1, ny=2*g.ny-1, nz=2*g.nz-1),
        "region": replace(g, x_min_m=(3*g.x_min_m-g.x_max_m)/2,
                          x_max_m=(3*g.x_max_m-g.x_min_m)/2,
                          y_min_m=(3*g.y_min_m-g.y_max_m)/2,
                          y_max_m=(3*g.y_max_m-g.y_min_m)/2, nx=2*g.nx-1, ny=2*g.ny-1),
    }
    for name, grid in variants.items():
        if (max(grid.nx*grid.ny, grid.nx*grid.nz) > max_plane_points
                or grid.nx*(grid.ny+grid.nz)*config.array.nx*config.array.ny > max_interactions):
            report["checks"][name] = {"status": "unchecked", "reason": "diagnostic budget exceeded"}
            continue
        m = summary(simulate(replace(config, grid=grid), sample).metrics)
        previous = summary(base.metrics)
        keys = ["force_over_displayed_plane_n"] if name == "region" else [
            "pressure_rms_max_pa", "pressure_x_minus6db_m", "force_over_displayed_plane_n"]
        report["checks"][name] = {k: _change(previous[k], m[k],
                                           region_tolerance if name == "region" else grid_tolerance)
                                 for k in keys}
    for name in ("pressure_x_minus6db", "pressure_y_minus6db"):
        report["checks"][name] = base.metrics[name]
    report["checks"]["focus"] = {"lateral_error_m": base.metrics["target_lateral_error_m"],
                                  "scope": "sampled target plane only"}
    report["checks"]["reference"] = reference_check(config, sample) if reference else {
        "status": "unchecked", "reason": "Run quality --reference for independent disk integration"}
    return report


def reference_check(config, sample):
    if config.medium.attenuation_np_m != 0:
        return {"status": "unchecked", "reason": "Reference quadrature supports lossless medium only"}
    n = config.array.nx * config.array.ny
    if n * 9 * 48 * 96 > 100000000:
        return {"status": "unchecked", "reason": "reference integration budget exceeded"}
    nominal = array_positions(config)
    actual = validate_sample(sample, nominal, config.element.radius_m)
    weights = focusing_weights(nominal, focus_point(config), config, sample)
    f = focus_point(config)
    step = config.wavelength_m
    points = np.array([f + [x*step, y*step, 0] for y in (-1, 0, 1) for x in (-1, 0, 1)])
    def integrate(radial, angular):
        total = np.zeros(len(points), complex)
        for pos, weight in zip(actual, weights, strict=True):
            total += weight * rayleigh_disk(
                points, config.element.radius_m, config.carrier_hz,
                config.medium.density_kg_m3, config.medium.sound_speed_m_s,
                radial_order=radial, angular_order=angular, center=pos)
        return total
    low, high = integrate(24, 48), integrate(48, 96)
    denominator = np.linalg.norm(high)
    if denominator == 0:
        return {"status": "unevaluable", "reason": "zero reference field"}
    convergence = float(np.linalg.norm(high-low)/denominator)
    fast = field_pressure(points, actual, weights, config)
    error = float(np.linalg.norm(fast-high)/denominator)
    return {"status": "unchecked" if convergence > .001 else ("pass" if error <= .02 else "sensitive"),
            "reason": "reference not converged" if convergence > .001 else "nine target-plane points only",
            "quadrature_relative_change": convergence, "relative_l2_error": error,
            "quadrature_tolerance": .001, "model_tolerance": .02, "points_m": points.tolist()}


def save_task(task, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    save_json(output/"task.json", task)
    save_json(output/"environment.json", environment())
    # Completed rows survive interruption or a later unexpected failure.
    with (output/"rows.jsonl").open("w", encoding="utf-8") as stream:
        def checkpoint(row):
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n")
            stream.flush()
        result = batch(task, on_row=checkpoint)
    save_json(output/"results.json", result)
    with (output/"metrics.csv").open("w", encoding="utf-8", newline="") as stream:
        keys = ["index", "value", "phase_bits", "status", "reason", *METRICS]
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        for row in result["rows"]:
            writer.writerow({k: row.get(k, row.get("metrics", {}).get(k)) for k in keys})
    from .export import write_manifest
    write_manifest(output)
    return result
