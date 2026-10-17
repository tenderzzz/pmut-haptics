"""Local Streamlit workbench. No simulation equations are duplicated here."""
import io
import json
import zipfile
from dataclasses import replace

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from pmut_haptics.config import SimulationConfig, to_toml
from pmut_haptics.metrics import to_db
from pmut_haptics.simulation import simulate

st.set_page_config(page_title="pMUT 触觉实验台", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
.stApp { background: #f6f8fb; color: #19364b; font-family: "PingFang SC", "Noto Sans CJK SC", Arial, sans-serif; }
h1, h2, h3 { color: #163b54; }
section[data-testid="stSidebar"] { background: #e9f0f6; }
.stButton > button[kind="primary"] { background: #176b87; border-color: #176b87; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(max_entries=6, show_spinner=False)
def compute(configuration):
    return simulate(SimulationConfig.from_dict(configuration))


def bundle(result):
    arrays = io.BytesIO()
    np.savez_compressed(arrays, **result.arrays)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("config.toml", to_toml(result.config))
        archive.writestr("metrics.json", json.dumps(result.metrics, ensure_ascii=False, indent=2))
        archive.writestr("arrays.npz", arrays.getvalue())
    return stream.getvalue()


def heatmap(x, y, values, title, unit, xname="x", yname="y"):
    fig = go.Figure(go.Heatmap(x=x*1000, y=y*1000, z=values,
                              colorscale="Inferno", colorbar={"title": unit}))
    fig.update_layout(title=title, xaxis_title=f"{xname} (mm)", yaxis_title=f"{yname} (mm)",
                      height=410, margin=dict(l=35, r=20, t=45, b=35),
                      paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#19364b"),
                      yaxis=dict(scaleanchor="x", scaleratio=1))
    return fig


with st.sidebar:
    st.header("实验参数")
    st.caption("空气介质 · 二维圆活塞阵列")
    scene = st.selectbox("触点运动", ["静态触点", "往复直线", "圆形轨迹"])
    side = st.select_slider("阵列每边阵元数", options=[4, 8, 12, 16, 24, 32], value=12)
    frequency = st.number_input("载波频率 (kHz)", min_value=20.0, max_value=600.0,
                                value=109.4, step=1.0)
    radius = st.number_input("阵元半径 (μm)", min_value=25.0, max_value=2000.0,
                             value=415.0, step=5.0)
    pitch = st.slider("阵元间距 / 波长", min_value=0.3, max_value=1.0, value=0.5, step=0.05)
    velocity = st.number_input("峰值表面振速 (m/s)", min_value=0.0, max_value=10.0,
                               value=1.0, step=0.1)
    focus_z = st.slider("目标平面高度 (mm)", 20, 80, 50)
    focus_x = st.slider("焦点 x (mm)", -10, 10, 0)
    focus_y = st.slider("焦点 y (mm)", -10, 10, 0)
    apod = st.selectbox("阵元幅度分布", ["均匀", "Hann"])
    st.caption("加权比较保持振速平方和相同。")
    modulation = st.selectbox("调制方式", ["脉冲", "正弦幅度调制", "连续波"])
    mod_freq = st.slider("调制频率 (Hz)", 20, 400, 100, step=10)
    duty = st.slider("脉冲占空比", 0.1, 1.0, 0.5, step=0.05)
    with st.expander("采样与误差"):
        grid_side = st.select_slider("目标平面网格", options=[51, 81, 101, 151], value=81)
        phase_error = st.slider("阵元相位误差标准差 (°)", 0, 60, 0)
        attenuation = st.number_input("振幅衰减系数 (Np/m)", min_value=0.0, value=0.0, step=0.1)
    run_clicked = st.button("运行仿真", type="primary", width="stretch")

base = SimulationConfig()
kind = {"静态触点": "static", "往复直线": "line", "圆形轨迹": "circle"}[scene]
current = replace(
    base, carrier_hz=frequency*1000, title=scene,
    medium=replace(base.medium, attenuation_np_m=attenuation),
    element=replace(base.element, radius_m=radius*1e-6, velocity_peak_m_s=velocity),
    array=replace(base.array, nx=side, ny=side, pitch_wavelengths=pitch,
                  apodization="hann" if apod == "Hann" else "uniform",
                  phase_error_std_deg=float(phase_error)),
    focus=replace(base.focus, x_m=focus_x*1e-3, y_m=focus_y*1e-3, z_m=focus_z*1e-3),
    grid=replace(base.grid, nx=grid_side, ny=grid_side, nz=101),
    modulation=replace(base.modulation, kind={"脉冲": "burst", "正弦幅度调制": "sinusoidal",
                                             "连续波": "cw"}[modulation],
                       frequency_hz=float(mod_freq), duty_cycle=duty,
                       duration_s=.05 if kind == "static" else 1.0),
    trajectory=replace(base.trajectory, kind=kind, frames=41),
)

st.title("pMUT 空中触觉实验台")
st.write("展开左侧参数栏，调整阵列与驱动，观察聚焦声场如何转化为表面触觉刺激。")
st.caption("相控阵 → 空气声场 → 低频调制 → 表面辐射力。输入振速为仿真假设，尚未由驱动电压标定。")

if run_clicked or "result" not in st.session_state:
    try:
        current.validate()
        with st.spinner("计算声场、表面刺激与轨迹…"):
            st.session_state.result = compute(current.to_dict())
    except ValueError as exc:
        st.error(str(exc))

if "result" not in st.session_state:
    st.stop()
result = st.session_state.result
if result.config.to_dict() != current.to_dict():
    st.info("参数已改变。当前显示上一次结果，点击“运行仿真”更新。")
a, m = result.arrays, result.metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("目标平面最大 RMS 声压", f'{m["pressure_rms_max_pa"]:.2f} Pa')
c2.metric("最大辐射压", f'{m["radiation_pressure_max_pa"]:.4f} Pa')
c3.metric("显示区域内合力", f'{m["force_over_displayed_plane_n"]*1e6:.2f} μN')
width = m["pressure_x_minus6db"]["width_m"]
missing_width = "无有效信号" if m["pressure_x_minus6db"]["reason"] == "zero_signal" else "超出视野"
c4.metric("x 方向声压 −6 dB 宽度", missing_width if width is None else f"{width*1000:.2f} mm")

tabs = st.tabs(["声场与触点", "调制与移动", "实验对比", "模型与导出"])
with tabs[0]:
    left, right = st.columns(2)
    left.plotly_chart(heatmap(a["x_m"], a["y_m"], a["pressure_xy_rms_pa"],
                              "目标平面声压", "Pa RMS"), width="stretch")
    right.plotly_chart(heatmap(a["x_m"], a["z_m"], to_db(a["pressure_xz_peak_pa"]),
                               "穿过焦点的竖直截面", "dB", yname="z"), width="stretch")
    left.plotly_chart(heatmap(a["x_m"], a["y_m"], a["radiation_xy_pa"],
                              "目标平面辐射压", "Pa"), width="stretch")
    pos, path = a["element_positions_m"]*1000, a["trajectory_points_m"]*1000
    geometry = go.Figure(go.Scatter3d(x=pos[:, 0], y=pos[:, 1], z=pos[:, 2], mode="markers",
                                     marker=dict(size=3, color=np.angle(a["velocity_weights_m_s"]),
                                                 colorscale="Twilight"), name="阵元"))
    geometry.add_trace(go.Scatter3d(x=path[:, 0], y=path[:, 1], z=path[:, 2],
                                    mode="lines+markers", marker=dict(size=3),
                                    line=dict(color="#df6b36"), name="目标轨迹"))
    geometry.update_layout(title="阵列几何与目标位置", height=410, margin=dict(l=0, r=0, t=45, b=0),
                           scene=dict(xaxis_title="x (mm)", yaxis_title="y (mm)", zaxis_title="z (mm)"))
    right.plotly_chart(geometry, width="stretch")

with tabs[1]:
    fig = go.Figure(go.Scatter(x=a["time_s"]*1000, y=a["plane_force_time_n"]*1e6,
                               name="区域合力", line=dict(color="#176b87")))
    fig.update_layout(title="调制后的表面合力", xaxis_title="时间 (ms)", yaxis_title="合力 (μN)",
                       height=320)
    st.plotly_chart(fig, width="stretch")
    st.caption("辐射力随驱动幅度包络的平方变化；图中已按载波周期平均。")
    if len(a["trajectory_points_m"]) > 1:
        frames = a["trajectory_radiation_pa"]
        max_value = float(frames.max())
        movie = go.Figure(data=[go.Heatmap(x=a["x_m"]*1000, y=a["y_m"]*1000, z=frames[0],
                                         colorscale="Inferno", zmin=0, zmax=max_value,
                                         colorbar=dict(title="Pa"))],
                          frames=[go.Frame(data=[go.Heatmap(z=frame)], name=str(i))
                                  for i, frame in enumerate(frames)])
        movie.update_layout(
            title="移动触点回放（未叠加低频闪烁）", height=450,
            xaxis_title="x (mm)", yaxis_title="y (mm)",
            yaxis=dict(scaleanchor="x", scaleratio=1),
            updatemenus=[dict(type="buttons", buttons=[
                dict(label="播放", method="animate", args=[None, {"frame": {"duration": 60},
                     "transition": {"duration": 0}, "fromcurrent": True}]),
                dict(label="暂停", method="animate", args=[[None], {"mode": "immediate",
                     "frame": {"duration": 0}, "transition": {"duration": 0}}]),
            ])],
        )
        st.plotly_chart(movie, width="stretch")
        st.caption("回放速度用于观察轨迹；实际指令时刻保存在下载数据中。")
    else:
        st.write("选择往复直线或圆形轨迹后，可以回放移动触点。")

with tabs[2]:
    if st.button("保存当前结果用于对比"):
        st.session_state.comparison = result
    previous = st.session_state.get("comparison")
    if previous is None:
        st.write("保存一个结果，再调整参数并运行，可比较声压、辐射力和主瓣宽度。")
    else:
        rows = []
        for label, item in [("已保存实验", previous), ("当前实验", result)]:
            item_m = item.metrics
            w = item_m["pressure_x_minus6db"]["width_m"]
            rows.append({"实验": label, "阵元数": item_m["element_count"],
                         "频率 kHz": item.config.carrier_hz/1000,
                         "最大 RMS 声压 Pa": item_m["pressure_rms_max_pa"],
                         "区域合力 μN": item_m["force_over_displayed_plane_n"]*1e6,
                         "主瓣宽度 mm": None if w is None else w*1000,
                         "振速平方和": item_m["sum_squared_velocity_m2_s2"]})
        st.dataframe(rows, width="stretch", hide_index=True)
        st.caption("比较阵元数量时请同时检查振速平方和；它不等于电功率。")

with tabs[3]:
    st.write("模型使用均匀介质中的障板圆活塞近似，并按近似法向入射估算表面辐射压。")
    st.write("峰值表面振速是输入假设，尚未由驱动电压标定。图中的刺激强度用于设计比较，人体可感知性需要实测。")
    st.write("默认载波、阵元数量与半径参考 Pala 等人的非接触 pMUT 研究；间距、焦距及振速为示例设置。")
    st.markdown("[原始研究](https://bsac.berkeley.edu/node/328) · "
                "[辐射压模型](https://hapislab.org/public/hiroyuki_shinoda/research/pdf/08Eurohaptics_iwamoto.pdf)")
    st.download_button("下载配置、指标和原始数据", bundle(result),
                        file_name="pmut-experiment.zip", mime="application/zip")
    st.download_button("下载 TOML 配置", to_toml(result.config),
                        file_name="experiment.toml", mime="text/plain")
    st.json(m, expanded=False)
