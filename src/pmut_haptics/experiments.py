"""Parameter scans and same-model performance comparisons."""
import csv
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from .config import Trajectory
from .export import environment, save_json
from .simulation import simulate


def sweep(config, output, normalization="fixed_sum_squared_velocity"):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    reference_count = config.array.nx*config.array.ny
    for side in [8, 12, 16]:
        for ratio in [.35, .5, .8]:
            velocity = config.element.velocity_peak_m_s
            if normalization == "fixed_sum_squared_velocity":
                velocity *= (reference_count/(side*side))**.5
            elif normalization != "per_element":
                raise ValueError("Unknown normalization")
            current = replace(
                config, array=replace(config.array, nx=side, ny=side, pitch_wavelengths=ratio),
                element=replace(config.element, velocity_peak_m_s=velocity),
                grid=replace(config.grid, nx=81, ny=81, nz=81),
                trajectory=Trajectory(),
            )
            current.validate()
            metrics = simulate(current).metrics
            row = {
                "nx": side, "ny": side, "pitch_wavelengths": ratio,
                "normalization": normalization, "velocity_peak_m_s": velocity,
                "sum_squared_velocity_m2_s2": metrics["sum_squared_velocity_m2_s2"],
                "pressure_rms_max_pa": metrics["pressure_rms_max_pa"],
                "radiation_pressure_max_pa": metrics["radiation_pressure_max_pa"],
                "force_over_displayed_plane_n": metrics["force_over_displayed_plane_n"],
                "pressure_x_minus6db_m": metrics["pressure_x_minus6db"]["width_m"],
                "pressure_x_width_clipped": metrics["pressure_x_minus6db"]["clipped"],
                "radiation_x_fwhm_m": metrics["radiation_x_fwhm"]["width_m"],
                "sidelobe_x_db": metrics["sidelobe_x_db"],
            }
            rows.append(row)
    with (output/"scan.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    save_json(output/"scan.json", {"base_config": config.to_dict(), "rows": rows,
                                  "normalization_note": "sum squared surface velocity is a proxy, not electrical power"})
    save_json(output/"environment.json", environment())
    return rows


def benchmark(output, repeats=5):
    if repeats < 5:
        raise ValueError("At least five measured repetitions are required")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    env = os.environ.copy()
    for key in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"]:
        env[key] = "1"
    for side, grid in [(8, 32), (12, 64), (16, 96)]:
        pair = {}
        for backend in ["reference", "vectorized"]:
            print(f"Benchmark {side}x{side} elements, {grid}x{grid} points: {backend}", flush=True)
            run = subprocess.run(
                [sys.executable, "-m", "pmut_haptics.benchmark_worker", str(side), str(grid),
                 backend, str(repeats)], check=True, capture_output=True, text=True, env=env,
                timeout=180,
            )
            pair[backend] = json.loads(run.stdout)
        row = {"array_side": side, "grid_side": grid, **pair,
               "speedup_median": pair["reference"]["median_seconds"]/pair["vectorized"]["median_seconds"]}
        rows.append(row)
    result = {"environment": environment(), "requested_threads_per_worker": 1,
              "warmup_runs": 1, "repeats": repeats, "cases": rows,
              "scope": "Same analytic piston kernel, float64/complex128; excludes plots and file I/O",
              "memory_scope": "Fresh worker process peak RSS, includes interpreter and imported libraries"}
    save_json(output/"benchmark.json", result)
    lines = ["# 性能测试", "", "相同物理模型、相同精度，独立进程设置线程环境为 1；一次预热后重复测量。",
             "", "| 阵列 | 网格 | 参考中位耗时 ms | 分块中位耗时 ms | 加速比 | 分块峰值 RSS MiB |",
             "| --- | --- | ---: | ---: | ---: | ---: |"]
    for row in rows:
        r, v = row["reference"], row["vectorized"]
        lines.append(f'| {row["array_side"]}×{row["array_side"]} | {row["grid_side"]}×{row["grid_side"]} '
                     f'| {r["median_seconds"]*1000:.3f} | {v["median_seconds"]*1000:.3f} '
                     f'| {row["speedup_median"]:.2f} | {v["peak_rss_bytes"]/1024**2:.1f} |')
    lines += ["", "峰值内存包含 Python 和依赖库；加速比仅代表这台机器及这些测试规模。",
              "全部重复样本、误差与环境见同目录 benchmark.json。", ""]
    (output/"benchmark.md").write_text("\n".join(lines), encoding="utf-8")
    return result
