"""Read-only environment diagnosis, including iCloud-hidden path files."""
import importlib.util
import site
import stat
import sys
from pathlib import Path

print("Python:", sys.version.split()[0])
for package in ["pmut_haptics", "numpy", "scipy", "matplotlib", "streamlit"]:
    print(package, "available" if importlib.util.find_spec(package) else "missing")
for directory in site.getsitepackages():
    for path in Path(directory).glob("*.pth"):
        if getattr(path.stat(), "st_flags", 0) & getattr(stat, "UF_HIDDEN", 0):
            print("Hidden path file:", path.name)
            print("If imports fail, use: uv sync --no-editable --extra demo --group dev")
