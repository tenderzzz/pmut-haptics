"""Explicit, immutable configuration; no numerical module reads global settings."""
from __future__ import annotations

import json
import math
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass(frozen=True)
class Medium:
    sound_speed_m_s: float = 343.0
    density_kg_m3: float = 1.2
    attenuation_np_m: float = 0.0


@dataclass(frozen=True)
class Element:
    radius_m: float = 415e-6
    velocity_peak_m_s: float = 1.0


@dataclass(frozen=True)
class Array:
    nx: int = 12
    ny: int = 12
    pitch_wavelengths: float = 0.5
    apodization: str = "uniform"
    phase_error_std_deg: float = 0.0
    pitch_mode: str = "wavelength"
    pitch_m: float = 0.0015676416819012796


@dataclass(frozen=True)
class Imperfections:
    amplitude_cv: float = 0.0
    position_std_m: float = 0.0
    failure_probability: float = 0.0
    phase_bits: int = 0
    rng: str = "portable-v1"


@dataclass(frozen=True)
class Focus:
    x_m: float = 0.0
    y_m: float = 0.0
    z_m: float = 0.05


@dataclass(frozen=True)
class Grid:
    x_min_m: float = -0.02
    x_max_m: float = 0.02
    y_min_m: float = -0.02
    y_max_m: float = 0.02
    z_min_m: float = 0.01
    z_max_m: float = 0.08
    nx: int = 101
    ny: int = 101
    nz: int = 121


@dataclass(frozen=True)
class Modulation:
    kind: str = "burst"
    frequency_hz: float = 100.0
    duty_cycle: float = 0.5
    depth: float = 1.0
    duration_s: float = 0.05
    sample_rate_hz: float = 20000.0


@dataclass(frozen=True)
class Trajectory:
    kind: str = "static"
    radius_m: float = 0.005
    line_length_m: float = 0.015
    duration_s: float = 1.0
    frames: int = 61
    loops: int = 1


@dataclass(frozen=True)
class Engine:
    chunk_points: int = 2048
    max_transfer_mb: float = 128.0


@dataclass(frozen=True)
class SimulationConfig:
    schema_version: int = 2
    title: str = "空中静态触点"
    carrier_hz: float = 109400.0
    reflection_factor: float = 2.0
    seed: int = 42
    medium: Medium = field(default_factory=Medium)
    element: Element = field(default_factory=Element)
    array: Array = field(default_factory=Array)
    imperfections: Imperfections = field(default_factory=Imperfections)
    focus: Focus = field(default_factory=Focus)
    grid: Grid = field(default_factory=Grid)
    modulation: Modulation = field(default_factory=Modulation)
    trajectory: Trajectory = field(default_factory=Trajectory)
    engine: Engine = field(default_factory=Engine)

    @property
    def wavelength_m(self) -> float:
        return self.medium.sound_speed_m_s / self.carrier_hz

    @property
    def pitch_m(self) -> float:
        return (self.array.pitch_m if self.array.pitch_mode == "physical"
                else self.array.pitch_wavelengths * self.wavelength_m)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> SimulationConfig:
        if not isinstance(data, dict):
            raise ValueError("Configuration must be a mapping")
        nested = {
            "medium": Medium, "element": Element, "array": Array, "focus": Focus,
            "grid": Grid, "modulation": Modulation, "trajectory": Trajectory, "engine": Engine,
            "imperfections": Imperfections,
        }
        try:
            unknown = set(data) - {f.name for f in fields(cls)}
            if unknown:
                raise ValueError(f"Unknown configuration keys: {sorted(unknown)}")
            values = dict(data)
            if "schema_version" not in values:
                values["schema_version"] = 1
                values.setdefault("imperfections", {"rng": "legacy"})
            for name, kind in nested.items():
                if name in values:
                    if not isinstance(values[name], dict):
                        raise ValueError(f"{name} must be a table")
                    values[name] = kind(**values[name])
            result = cls(**values)
            result.validate()
            return result
        except (TypeError, OverflowError) as exc:
            raise ValueError(f"Invalid configuration: {exc}") from exc

    def validate(self) -> None:
        def check_types(obj):
            for f in fields(obj):
                value = getattr(obj, f.name)
                if hasattr(value, "__dataclass_fields__"):
                    check_types(value)
                elif f.type == "str":
                    if not isinstance(value, str):
                        raise ValueError(f"{f.name} must be a string")
                elif f.type == "int":
                    if isinstance(value, bool) or not isinstance(value, int):
                        raise ValueError(f"{f.name} must be an integer")
                elif f.type == "float":
                    if isinstance(value, bool) or not isinstance(value, (float, int)):
                        raise ValueError(f"{f.name} must be a number")
                    if not math.isfinite(value):
                        raise ValueError(f"{f.name} must be finite")
        check_types(self)
        e = self.imperfections
        if self.schema_version not in {1, 2}:
            raise ValueError("Unsupported configuration schema version")
        if self.array.pitch_mode not in {"wavelength", "physical"} or self.array.pitch_m <= 0:
            raise ValueError("Invalid pitch mode or physical pitch")
        if e.amplitude_cv < 0 or e.amplitude_cv > 2 or e.position_std_m < 0:
            raise ValueError("Amplitude CV must be in [0,2]; position std must be nonnegative")
        if not 0 <= e.failure_probability <= 1 or not 0 <= e.phase_bits <= 16:
            raise ValueError("Failure probability must be in [0,1]; phase bits in 0..16")
        if e.rng not in {"legacy", "portable-v1"}:
            raise ValueError("Unsupported random algorithm")
        positive = {
            "carrier_hz": self.carrier_hz,
            "sound_speed_m_s": self.medium.sound_speed_m_s,
            "density_kg_m3": self.medium.density_kg_m3,
            "radius_m": self.element.radius_m,
            "pitch_wavelengths": self.array.pitch_wavelengths,
            "focus.z_m": self.focus.z_m,
            "frequency_hz": self.modulation.frequency_hz,
            "duration_s": self.modulation.duration_s,
            "sample_rate_hz": self.modulation.sample_rate_hz,
            "trajectory.duration_s": self.trajectory.duration_s,
            "max_transfer_mb": self.engine.max_transfer_mb,
        }
        for key, value in positive.items():
            if value <= 0:
                raise ValueError(f"{key} must be positive")
        if self.carrier_hz < 20000:
            raise ValueError("Airborne haptic carrier must be at least 20 kHz")
        if self.medium.attenuation_np_m < 0 or self.element.velocity_peak_m_s < 0:
            raise ValueError("Attenuation and velocity must be nonnegative")
        if self.array.phase_error_std_deg < 0 or self.seed < 0:
            raise ValueError("Phase error and seed must be nonnegative")
        if not 1 <= self.reflection_factor <= 2:
            raise ValueError("reflection_factor must lie in [1, 2]")
        if self.array.apodization not in {"uniform", "hann"}:
            raise ValueError("apodization must be uniform or hann")
        if min(self.array.nx, self.array.ny) < 1 or self.array.nx * self.array.ny > 4096:
            raise ValueError("Array must contain between 1 and 4096 elements")
        if self.pitch_m < 2 * self.element.radius_m:
            raise ValueError("Element diameter exceeds array pitch")
        if min(self.grid.nx, self.grid.ny, self.grid.nz) < 3:
            raise ValueError("Each grid axis needs at least 3 samples")
        if max(self.grid.nx * self.grid.ny, self.grid.nx * self.grid.nz) > 1_000_000:
            raise ValueError("Each evaluated plane is limited to one million points")
        g = self.grid
        if not (g.x_min_m < g.x_max_m and g.y_min_m < g.y_max_m
                and 0 < g.z_min_m < g.z_max_m):
            raise ValueError("Grid bounds must increase and z must be positive")
        if not (g.x_min_m <= self.focus.x_m <= g.x_max_m
                and g.y_min_m <= self.focus.y_m <= g.y_max_m
                and g.z_min_m <= self.focus.z_m <= g.z_max_m):
            raise ValueError("Focus must lie within the displayed volume")
        m = self.modulation
        if m.kind not in {"cw", "burst", "sinusoidal"}:
            raise ValueError("Modulation kind must be cw, burst or sinusoidal")
        if not 0 < m.duty_cycle <= 1 or not 0 <= m.depth <= 1:
            raise ValueError("Duty cycle must be in (0,1]; depth in [0,1]")
        if m.sample_rate_hz < 20 * m.frequency_hz:
            raise ValueError("Envelope sampling needs >=20 samples per modulation period")
        if m.duration_s * m.sample_rate_hz > 2_000_000:
            raise ValueError("Envelope waveform exceeds two million samples")
        t = self.trajectory
        if t.kind not in {"static", "line", "circle"}:
            raise ValueError("Trajectory kind must be static, line or circle")
        if t.frames < 3 or t.frames > 501 or t.loops < 1:
            raise ValueError("Trajectory needs 3..501 frames and positive loops")
        if min(t.radius_m, t.line_length_m) < 0:
            raise ValueError("Trajectory dimensions must be nonnegative")
        if t.kind != "static":
            reach_x = t.radius_m if t.kind == "circle" else t.line_length_m / 2
            reach_y = t.radius_m if t.kind == "circle" else 0.0
            if not (g.x_min_m <= self.focus.x_m - reach_x
                    and self.focus.x_m + reach_x <= g.x_max_m
                    and g.y_min_m <= self.focus.y_m - reach_y
                    and self.focus.y_m + reach_y <= g.y_max_m):
                raise ValueError("Entire trajectory must fit within the target plane")
            if t.frames < 12 * t.loops + 1:
                raise ValueError("Trajectory requires >=12 frames per loop")
        active_frames = 1 if t.kind == "static" else t.frames
        if g.nx * g.ny * active_frames > 10_000_000:
            raise ValueError("Trajectory output exceeds ten million plane samples; reduce grid or frames")
        if not 1 <= self.engine.chunk_points <= 65536:
            raise ValueError("chunk_points must lie in 1..65536")


def load_config(path: str | Path) -> SimulationConfig:
    with Path(path).open("rb") as stream:
        return SimulationConfig.from_dict(tomllib.load(stream))


def to_toml(config: SimulationConfig) -> str:
    data = config.to_dict()
    lines = []
    def encode(value):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    for key, value in data.items():
        if not isinstance(value, dict):
            lines.append(f"{key} = {encode(value)}")
    for key, value in data.items():
        if isinstance(value, dict):
            lines.extend(["", f"[{key}]"])
            lines.extend(f"{k} = {encode(v)}" for k, v in value.items())
    return "\n".join(lines) + "\n"
