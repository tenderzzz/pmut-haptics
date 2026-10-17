"""Run only numerical functions from the verbatim restored appendix."""
import ast
import hashlib
import json
from importlib.resources import files

import numpy as np
from scipy import special


def source_namespace():
    source = files("pmut_haptics").joinpath("data/legacy_simulation.py.txt").read_text("utf-8")
    manifest = json.loads(files("pmut_haptics").joinpath("data/source_manifest.json").read_text())
    if hashlib.sha256(source.encode()).hexdigest() != manifest["restored_code_sha256"]:
        raise ValueError("Legacy source checksum mismatch")
    tree = ast.parse(source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    namespace = {"np": np, "special": special, "rho0": 1000.0, "c0": 1480.0,
                 "fs": 1e6, "scatterer_strength": np.ones(5)}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "<restored-appendix>", "exec"),
         namespace)
    return namespace


def original_results():
    ns = source_namespace()
    a, c, frequency = 1e-3, 1480.0, 22960.0
    wave = c/frequency
    k = 2*np.pi/wave
    positions = (np.arange(8)-3.5)*0.5*wave
    delays = ns["focusing_delays"](positions, 0.05, c)
    x = np.linspace(-0.06, 0.06, 240)
    z = np.linspace(0.01, 0.1, 240)
    xx, zz = np.meshgrid(x, z, indexing="ij")
    pressure = ns["array_piston_field"](xx, zz, k, a, positions, delays)
    profile = abs(pressure[:, np.argmin(abs(z-0.05))])
    idx = np.flatnonzero(20*np.log10(profile/profile.max()+1e-12) >= -6)
    widths = []
    for count in [4, 8, 16, 32]:
        for ratio in [0.3, 0.5, 0.8]:
            ax = (np.arange(count)-(count-1)/2)*ratio*wave
            sx = np.linspace(-0.08, 0.08, 200)
            p = ns["array_piston_field"](sx[:, None], np.full((200, 1), 0.05),
                                         k, a, ax, ns["focusing_delays"](ax, 0.05, c))
            p = abs(p[:, 0])
            indices = np.flatnonzero(20*np.log10(p/p.max()+1e-12) >= -6)
            widths.append({"elements": count, "pitch_wavelengths": ratio,
                           "legacy_width_mm": float((sx[indices[-1]]-sx[indices[0]])*1e3)})
    scatterers = np.array([[0, .045], [-.015, .04], [.015, .04], [-.008, .055], [.008, .055]])
    tmax = 2*np.hypot(.06, .04)/c+50e-6
    times = np.arange(0, tmax, 1e-6)
    rf = ns["simulate_synthetic_aperture"](positions, scatterers, k, c, times, 1e6)
    xi, zi = np.linspace(-.05, .05, 80), np.linspace(.02, .08, 80)
    image = ns["delay_and_sum_beamform"](rf, positions, times, c, xi, zi)
    db = 20*np.log10(image/image.max()+1e-6)
    image_widths = []
    for xs, zs in scatterers:
        ix, iz = np.argmin(abs(xi-xs)), np.argmin(abs(zi-zs))
        lat, axi = db[:, iz], db[ix, :]
        li, ai = np.flatnonzero(lat-lat.max() >= -6), np.flatnonzero(axi-axi.max() >= -6)
        image_widths.append({"x_mm": float(xs*1e3), "z_mm": float(zs*1e3),
                             "lateral_mm": float((xi[li[-1]]-xi[li[0]])*1e3),
                             "axial_mm": float((zi[ai[-1]]-zi[ai[0]])*1e3)})
    thin_frequencies = [
        ns["clamped_plate_fundamental"](ns["bending_stiffness"](h, 70e9, .3), 7800, h, a)
        for h in [55e-6, 75e-6]
    ]
    d = np.hypot(positions[:, None]-scatterers[:, 0], scatterers[:, 1])
    arrivals = (d[:, None, :]+d[None, :, :])/c
    asymmetry = ns["rayleigh_2d"](np.array([-.001, .001]), np.full(2, .0005),
                                  2*np.pi*7550/c, a, 1000, c)
    metrics = {
        "profile": "report_original", "status": "historical reproduction; known defects retained",
        "plate_frequency_hz": thin_frequencies,
        "legacy_focus_width_mm": float((x[idx[-1]]-x[idx[0]])*1e3),
        "parameter_scan": widths, "image_widths": image_widths,
        "rf_shape": list(rf.shape),
        "diagnostics": {
            "outer_element_weight_magnitude": float(abs(np.exp(1j*(1j*k*c*delays[0])))),
            "symmetric_point_pressure_ratio": float(abs(asymmetry[1])/abs(asymmetry[0])),
            "echo_centers_after_record": int(np.sum(arrivals >= tmax)),
            "echo_path_count": int(arrivals.size),
            "last_echo_center_us": float(arrivals.max()*1e6),
            "record_end_us": float(tmax*1e6),
        },
    }
    reference_pressure = 20e-6
    target_pressure = reference_pressure*10**(124/20)
    original_pressure = ns["rayleigh_axis"](.001, 2*np.pi*7550/c, a)
    inferred_velocity = 1e-6*target_pressure/original_pressure
    metrics["historical_spl_scaling"] = {
        "target_db_re_20uPa": 124, "target_pressure_pa": float(target_pressure),
        "inferred_velocity_m_s": float(inferred_velocity),
        "inferred_displacement_m": float(inferred_velocity/(2*np.pi*7550)),
        "status": "historical arithmetic only; air/water and measurement conditions differ",
    }
    arrays = {"x_m": x, "z_m": z, "pressure_xz_peak_pa": pressure.T,
              "image_x_m": xi, "image_z_m": zi, "image_envelope": image.T,
              "scatterers_xz_m": scatterers, "rf_data": rf, "rf_time_s": times}
    single_x = np.linspace(-.008, .008, 200)
    single_z = np.linspace(.0005, .015, 200)
    sx, sz = np.meshgrid(single_x, single_z, indexing="xy")
    single_k = 2*np.pi*7550/c
    axis_z = np.linspace(.0001, .03, 500)
    theta = np.linspace(-np.pi/2, np.pi/2, 500)
    arrays.update({
        "single_x_m": single_x, "single_z_m": single_z,
        "single_pressure_pa": ns["rayleigh_2d"](sx, sz, single_k, a, 1000, c),
        "axis_z_m": axis_z, "axis_pressure_pa": ns["rayleigh_axis"](axis_z, single_k, a),
        "theta_rad": theta, "directivity": ns["far_field_dir"](theta, single_k, a),
    })
    return metrics, arrays
