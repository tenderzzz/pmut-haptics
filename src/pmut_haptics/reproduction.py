"""Historical reproduction and independently corrected water extension."""
import csv
from pathlib import Path

import numpy as np

from .acoustics import axis_pressure, jinc, piston_transfer, rayleigh_disk
from .export import environment, save_json
from .imaging import delay_and_sum, simulate_echoes
from .legacy import original_results
from .metrics import connected_width, to_db


def corrected_results():
    c, rho, f, a = 1480.0, 1000.0, 22960.0, 1e-3
    wave, k = c/f, 2*np.pi*f/c
    ax = (np.arange(8)-3.5)*0.5*wave
    positions = np.column_stack((ax, np.zeros(8), np.zeros(8)))
    distance = np.hypot(ax, .05)
    weights = 1e-6*np.exp(1j*k*(distance-distance.min()))
    x, z = np.linspace(-.06, .06, 241), np.linspace(.01, .1, 241)
    xx, zz = np.meshgrid(x, z, indexing="xy")
    points = np.column_stack((xx.ravel(), np.zeros(xx.size), zz.ravel()))
    pressure = (piston_transfer(points, positions, f, a, rho, c)@weights).reshape(xx.shape)
    focal = piston_transfer(np.column_stack((x, np.zeros(len(x)), np.full(len(x), .05))),
                            positions, f, a, rho, c)@weights
    scatterers = np.array([[0, .045], [-.015, .04], [.015, .04], [-.008, .055], [.008, .055]])
    xi, zi = np.linspace(-.05, .05, 81), np.linspace(.02, .08, 81)
    roi = np.array([[-.05, .02], [-.05, .08], [.05, .02], [.05, .08]])
    echo = simulate_echoes(ax, scatterers, np.ones(5), roi_xz=roi)
    image = delay_and_sum(echo, ax, xi, zi)
    widths = []
    for xs, zs in scatterers:
        single = simulate_echoes(ax, np.array([[xs, zs]]), np.ones(1), roi_xz=roi)
        psf = delay_and_sum(single, ax, xi, zi)
        iz, ix = np.unravel_index(psf.argmax(), psf.shape)
        widths.append({"x_mm": float(xs*1e3), "z_mm": float(zs*1e3),
                       "peak_x_mm": float(xi[ix]*1e3), "peak_z_mm": float(zi[iz]*1e3),
                       "lateral": connected_width(xi, psf[iz]),
                       "axial": connected_width(zi, psf[:, ix])})
    symmetric = rayleigh_disk(np.array([[-.001, 0, .0005], [.001, 0, .0005]]),
                               a, 7550, rho, c, 1e-6, 40, 128)
    metrics = {
        "profile": "report_corrected",
        "status": "corrected simplified water model; not a haptic hardware validation",
        "focus_pressure_minus6db": connected_width(x, abs(focal)),
        "isolated_psf_widths": widths,
        "symmetric_point_pressure_ratio": float(abs(symmetric[1])/abs(symmetric[0])),
        "rf_shape": list(echo.signals.shape),
        "pulse_fwhm_cycles": 3.0, "pulse_center_s": echo.pulse_center_s,
        "record_end_s": float(echo.time_s[-1]),
        "psf_method": "Each scatterer simulated separately; widths through reconstructed global peak",
    }
    arrays = {"x_m": x, "z_m": z, "pressure_xz_peak_pa": pressure,
              "image_x_m": xi, "image_z_m": zi, "image_envelope": image,
              "scatterers_xz_m": scatterers, "rf_data": echo.signals, "rf_time_s": echo.time_s}
    single_x = np.linspace(-.008, .008, 101)
    single_z = np.linspace(.0005, .015, 101)
    sx, sz = np.meshgrid(single_x, single_z, indexing="xy")
    pts = np.column_stack((sx.ravel(), np.zeros(sx.size), sz.ravel()))
    axis_z = np.linspace(.0001, .03, 500)
    theta = np.linspace(-np.pi/2, np.pi/2, 500)
    arrays.update({
        "single_x_m": single_x, "single_z_m": single_z,
        "single_pressure_pa": rayleigh_disk(pts, a, 7550, rho, c, 1e-6).reshape(sx.shape),
        "axis_z_m": axis_z,
        "axis_pressure_pa": abs(axis_pressure(axis_z, a, 7550, rho, c, 1e-6)),
        "theta_rad": theta, "directivity": abs(jinc(2*np.pi*7550/c*a*np.sin(theta))),
    })
    scans = []
    for count in [4, 8, 16, 32]:
        for ratio in [.3, .5, .8]:
            line = (np.arange(count)-(count-1)/2)*ratio*wave
            pp = np.column_stack((line, np.zeros(count), np.zeros(count)))
            d = np.hypot(line, .05)
            ww = 1e-6*np.exp(1j*k*(d-d.min()))
            xp = np.linspace(-.08, .08, 801)
            pt = np.column_stack((xp, np.zeros(len(xp)), np.full(len(xp), .05)))
            value = piston_transfer(pt, pp, f, a, rho, c)@ww
            width = connected_width(xp, abs(value))
            scans.append({"elements": count, "pitch_wavelengths": ratio,
                          "corrected_width_mm": None if width["width_m"] is None else width["width_m"]*1000,
                          "clipped": width["clipped"]})
    metrics["parameter_scan"] = scans
    return metrics, arrays


def reproduce(profile, output):
    from .plotting import configure_matplotlib
    configure_matplotlib()
    import matplotlib.pyplot as plt
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    metrics, arrays = original_results() if profile == "original" else corrected_results()
    save_json(output/"metrics.json", metrics)
    save_json(output/"environment.json", environment())
    np.savez_compressed(output/"arrays.npz", **arrays)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    axes[0].pcolormesh(arrays["x_m"]*1e3, arrays["z_m"]*1e3,
                       to_db(arrays["pressure_xz_peak_pa"]), vmin=-40, vmax=0,
                       shading="auto", cmap="inferno")
    axes[0].set(xlabel="x (mm)", ylabel="z (mm)", title="Array field (relative pressure dB)")
    axes[1].pcolormesh(arrays["image_x_m"]*1e3, arrays["image_z_m"]*1e3,
                       to_db(arrays["image_envelope"]), vmin=-40, vmax=0,
                       shading="auto", cmap="gray")
    axes[1].scatter(*arrays["scatterers_xz_m"].T*1e3, facecolors="none",
                     edgecolors="#e45756", label="True scatterers")
    axes[1].set(xlabel="x (mm)", ylabel="z (mm)", title="Synthetic aperture image (dB)")
    axes[1].legend()
    fig.savefig(output/"reproduction.png", dpi=160)
    plt.close(fig)
    plot_stages(metrics, arrays, output, profile)
    if profile == "original":
        with (output/"legacy_parameter_scan.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=metrics["parameter_scan"][0].keys())
            writer.writeheader()
            writer.writerows(metrics["parameter_scan"])
    return metrics


def plot_stages(metrics, arrays, output, profile):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    axes[0].plot(arrays["axis_z_m"]*1000, arrays["axis_pressure_pa"])
    axes[0].set(xlabel="z (mm)", ylabel="Pressure amplitude (Pa)",
                title="Single piston on-axis analytical solution")
    image = axes[1].pcolormesh(arrays["single_x_m"]*1000, arrays["single_z_m"]*1000,
                               to_db(arrays["single_pressure_pa"]), cmap="inferno",
                               vmin=-40, vmax=0, shading="auto")
    fig.colorbar(image, ax=axes[1], label="Relative pressure (dB)")
    axes[1].set(xlabel="x (mm)", ylabel="z (mm)", title=f"Single-piston field: {profile}")
    fig.savefig(output/"single_element.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 3.5), constrained_layout=True)
    ax.plot(np.degrees(arrays["theta_rad"]), to_db(arrays["directivity"]))
    ax.set(xlabel="Angle (degrees)", ylabel="Relative pressure (dB)",
           title="Piston directivity: 7.55 kHz in water")
    ax.grid(alpha=.2)
    fig.savefig(output/"directivity.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4), constrained_layout=True)
    for ratio in [.3, .5, .8]:
        rows = [r for r in metrics["parameter_scan"] if r["pitch_wavelengths"] == ratio]
        key = "legacy_width_mm" if profile == "original" else "corrected_width_mm"
        ax.plot([r["elements"] for r in rows],
                [np.nan if r[key] is None else r[key] for r in rows], "o-", label=f"pitch={ratio} lambda")
    ax.set(xlabel="Element count", ylabel="Pressure -6 dB width (mm)",
           title=f"Water array parameter sweep: {profile}")
    ax.legend()
    ax.grid(alpha=.2)
    fig.savefig(output/"parameter_scan.png", dpi=160)
    plt.close(fig)

    img = arrays["image_envelope"]
    ix = np.argmin(abs(arrays["image_x_m"]))
    iz = np.argmin(abs(arrays["image_z_m"]-.045))
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.5), constrained_layout=True)
    axes[0].plot(arrays["image_x_m"]*1000, to_db(img[iz]))
    axes[1].plot(arrays["image_z_m"]*1000, to_db(img[:, ix]))
    for ax, label in zip(axes, ["x", "z"], strict=True):
        ax.axhline(-6, ls="--", color="#df6b36")
        ax.set(xlabel=f"{label} (mm)", ylabel="Relative envelope (dB)",
               title="Multi-scatterer section (not isolated PSF)")
    fig.savefig(output/"image_sections.png", dpi=160)
    plt.close(fig)
    if profile == "original":
        frequencies = np.asarray(metrics["plate_frequency_hz"])/1000
        calculated = frequencies[[0, 1, 0, 1]]
        literature = np.array([22960, 23610, 7550, 4900])/1000
        fig, ax = plt.subplots(figsize=(8, 4), constrained_layout=True)
        x = np.arange(4)
        ax.bar(x-.2, calculated, .4, label="Legacy homogeneous plate")
        ax.bar(x+.2, literature, .4, label="Literature: different device conditions")
        ax.set_xticks(x, ["55 um open", "75 um open", "55 um + rubber", "75 um + rubber"])
        ax.set(ylabel="Frequency (kHz)", title="Historical comparison; material assumptions differ")
        ax.legend()
        fig.savefig(output/"plate_frequency.png", dpi=160)
        plt.close(fig)
