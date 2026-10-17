"""Run the complete evidence suite from a source checkout."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=Path("outputs/full"))
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
environment = os.environ.copy()
environment["PYTHONPATH"] = str(root/"src")
commands = []
for name in ["quick", "midair_touchpoint", "midair_sinusoidal", "midair_line", "midair_circle"]:
    commands.append(["run", "--config", str(root/"configs"/f"{name}.toml"),
                     "--output", str(output/name)])
for profile in ["original", "corrected"]:
    commands.append(["reproduce", "--profile", profile, "--output", str(output/profile)])
for normalization in ["fixed_sum_squared_velocity", "per_element"]:
    commands.append(["sweep", "--normalization", normalization, "--output", str(output/normalization)])
commands.append(["benchmark", "--output", str(output/"benchmark")])
for command in commands:
    print("Running:", " ".join(command), flush=True)
    run = subprocess.run([sys.executable, "-m", "pmut_haptics.cli", *command],
                         cwd=root, env=environment, capture_output=True, text=True)
    label = Path(command[-1]).name
    (output/f"{label}.log").write_text(run.stdout+"\n"+run.stderr, encoding="utf-8")
    if run.returncode:
        print(run.stdout, run.stderr)
        raise SystemExit(run.returncode)
    print("Finished:", label, flush=True)
subprocess.run([sys.executable, str(root/"scripts/validate_models.py"),
                "--output", str(output/"validation")], env=environment, cwd=root, check=True)
print("All evidence saved:", output)
