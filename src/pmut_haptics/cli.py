"""Command-line entry point; all workflows are available without the demo extra."""
import argparse
import json
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

from .config import SimulationConfig, load_config, to_toml
from .export import save_result
from .simulation import simulate


def parser():
    root = argparse.ArgumentParser(prog="pmut-haptics", description="pMUT airborne stimulus simulator")
    root.add_argument("--version", action="version", version="pmut-haptics 0.1.0")
    sub = root.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Simulate a configured focal stimulus")
    run.add_argument("--config", type=Path)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--no-plots", action="store_true")
    scan = sub.add_parser("sweep", help="Compare array size and pitch")
    scan.add_argument("--config", type=Path)
    scan.add_argument("--output", type=Path, required=True)
    scan.add_argument("--normalization", choices=["fixed_sum_squared_velocity", "per_element"],
                      default="fixed_sum_squared_velocity")
    bench = sub.add_parser("benchmark", help="Measure reference and vectorized kernels")
    bench.add_argument("--output", type=Path, required=True)
    bench.add_argument("--repeats", type=int, default=5)
    reproduce = sub.add_parser("reproduce", help="Run report baseline or corrected water model")
    reproduce.add_argument("--profile", choices=["original", "corrected"], required=True)
    reproduce.add_argument("--output", type=Path, required=True)
    demo = sub.add_parser("demo", help="Start the local interactive application")
    demo.add_argument("--port", type=int, default=8501)
    init = sub.add_parser("config", help="Print a complete default TOML configuration")
    init.add_argument("--output", type=Path)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command in {"run", "sweep"}:
            config = load_config(args.config) if args.config else SimulationConfig()
            config.validate()
            if args.command == "run":
                result = simulate(config)
                path = save_result(result, args.output, plots=not args.no_plots)
                print(json.dumps({"output": str(path), "metrics": result.metrics},
                                 ensure_ascii=False, indent=2))
            else:
                from .experiments import sweep
                rows = sweep(config, args.output, args.normalization)
                print(f"Saved {len(rows)} experiments to {args.output}")
        elif args.command == "reproduce":
            from .reproduction import reproduce
            result = reproduce(args.profile, args.output)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "benchmark":
            from .experiments import benchmark
            benchmark(args.output, args.repeats)
            print(f"Saved benchmark to {args.output}")
        elif args.command == "config":
            text = to_toml(SimulationConfig())
            if args.output:
                with args.output.open("x", encoding="utf-8") as stream:
                    stream.write(text)
            else:
                print(text, end="")
        elif args.command == "demo":
            import importlib.util
            if importlib.util.find_spec("streamlit") is None:
                raise ValueError("Install the demo extra: uv sync --no-editable --extra demo")
            app = files("pmut_haptics").joinpath("demo.py")
            return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app),
                                    "--server.address=127.0.0.1", f"--server.port={args.port}",
                                    "--server.headless=true", "--browser.gatherUsageStats=false",
                                    "--theme.base=light", "--theme.primaryColor=#176b87",
                                    "--theme.backgroundColor=#f6f8fb",
                                    "--theme.secondaryBackgroundColor=#e9f0f6",
                                    "--theme.textColor=#19364b"])
        return 0
    except (ValueError, FileExistsError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
