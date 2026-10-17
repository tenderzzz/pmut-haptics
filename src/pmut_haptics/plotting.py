"""Static scientific figures. English labels avoid machine-dependent CJK fonts."""
from pathlib import Path

import numpy as np

from .metrics import to_db


def configure_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10,
        "axes.spines.top": False, "axes.spines.right": False,
        "savefig.facecolor": "white", "axes.titleweight": "medium",
    })


def plot_result(result, output):
    configure_matplotlib()
    import matplotlib.pyplot as plt
    a, output = result.arrays, Path(output)
    x, y, z = a["x_m"]*1e3, a["y_m"]*1e3, a["z_m"]*1e3
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    maps = [
        (axes[0, 0], x, y, a["pressure_xy_rms_pa"], "Focal plane: RMS pressure", "Pa"),
        (axes[0, 1], x, z, to_db(a["pressure_xz_peak_pa"]), "Vertical section", "dB"),
        (axes[1, 0], x, y, a["radiation_xy_pa"], "Surface radiation pressure", "Pa"),
    ]
    for ax, xx, yy, data, title, units in maps:
        im = ax.pcolormesh(xx, yy, data, shading="auto", cmap="inferno")
        fig.colorbar(im, ax=ax, label=units)
        ax.set(title=title, xlabel="x (mm)", ylabel="z (mm)" if ax is axes[0, 1] else "y (mm)")
    axes[1, 1].plot(a["time_s"]*1e3, a["plane_force_time_n"]*1e6, color="#126d82")
    axes[1, 1].set(title="Force over displayed target plane", xlabel="Time (ms)",
                  ylabel="Force (uN)")
    axes[1, 1].grid(alpha=.2)
    fig.suptitle("pMUT airborne stimulus simulation | assumed surface velocity", fontsize=13)
    fig.savefig(output/"overview.png", dpi=160)
    plt.close(fig)

    iy, ix = np.unravel_index(a["pressure_xy_rms_pa"].argmax(), a["pressure_xy_rms_pa"].shape)
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.5), constrained_layout=True)
    for ax, xx, values, label in [
        (axes[0], x, a["pressure_xy_rms_pa"][iy], "x"),
        (axes[1], y, a["pressure_xy_rms_pa"][:, ix], "y"),
    ]:
        ax.plot(xx, to_db(values), color="#126d82")
        ax.axhline(-6, color="#df6b36", ls="--", label="-6 dB pressure")
        ax.set(xlabel=f"{label} (mm)", ylabel="Relative pressure (dB)", ylim=(-60, 1))
        ax.grid(alpha=.2)
        ax.legend()
    fig.savefig(output/"profiles.png", dpi=160)
    plt.close(fig)

    fig = plt.figure(figsize=(7, 5), constrained_layout=True)
    ax = fig.add_subplot(projection="3d")
    positions = a["element_positions_m"]*1e3
    ax.scatter(*positions.T, c=np.angle(a["velocity_weights_m_s"]), cmap="twilight", s=20)
    path = a["trajectory_points_m"]*1e3
    ax.plot(*path.T, color="#df6b36", marker=".", label="Commanded focus")
    ax.set(xlabel="x (mm)", ylabel="y (mm)", zlabel="z (mm)",
           title="Array layout and focal trajectory")
    ax.legend()
    fig.savefig(output/"geometry.png", dpi=160)
    plt.close(fig)

    if len(path) > 1:
        fig, ax = plt.subplots(figsize=(6, 5), constrained_layout=True)
        im = ax.pcolormesh(x, y, a["trajectory_mean_unmodulated_radiation_pa"],
                          shading="auto", cmap="inferno")
        ax.plot(path[:, 0], path[:, 1], color="#70d4ea", lw=1, label="Commanded path")
        ax.set(xlabel="x (mm)", ylabel="y (mm)",
               title="Motion-averaged radiation pressure (unmodulated)")
        fig.colorbar(im, ax=ax, label="Pa")
        ax.legend()
        fig.savefig(output/"trajectory.png", dpi=160)
        plt.close(fig)
