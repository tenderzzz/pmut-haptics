"""Portable run artifacts, without user-specific absolute paths."""
import hashlib
import json
import os
import platform
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from .config import to_toml


def environment():
    dependencies = {}
    for name in ["pmut-haptics", "numpy", "scipy", "matplotlib", "streamlit", "plotly"]:
        try:
            dependencies[name] = version(name)
        except PackageNotFoundError:
            pass
    return {"python": platform.python_version(), "platform": platform.platform(),
            "machine": platform.machine(), "logical_cpus": os.cpu_count(),
            "dependencies": dependencies,
            "thread_environment": {k: os.getenv(k) for k in
                ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                 "VECLIB_MAXIMUM_THREADS"]}}


def save_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+"\n",
                          encoding="utf-8")


def save_result(result, output, plots=True):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output/"config.toml").write_text(to_toml(result.config), encoding="utf-8")
    save_json(output/"metrics.json", result.metrics)
    save_json(output/"environment.json", environment())
    np.savez_compressed(output/"arrays.npz", **result.arrays)
    if plots:
        from .plotting import plot_result
        plot_result(result, output)
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(output.iterdir()) if p.is_file()}
    save_json(output/"manifest.json", {
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "schema_version": 1, "files_sha256": hashes,
    })
    return output
