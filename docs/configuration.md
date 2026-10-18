# 参数与数据字典

TOML 和 Python API 共用不可变的 SimulationConfig。未提供的字段使用默认值；未知字段、错误类型、非有限数值和基本物理非法输入直接报错。生成完整模板：`pmut-haptics config --output experiment.toml`。

## 主参数

| 位置 | 默认值 | 解释 |
| --- | ---: | --- |
| carrier_hz | 109400 | 载波频率 Hz，空气主线至少 20 kHz |
| reflection_factor | 2 | 辐射压系数 κ，范围 [1,2] |
| seed | 42 | 阵元固定相位误差的随机种子 |
| medium.sound_speed_m_s | 343 | 声速 m/s |
| medium.density_kg_m3 | 1.2 | 密度 kg/m³ |
| medium.attenuation_np_m | 0 | 声压幅度衰减系数 Np/m |
| element.radius_m | 0.000415 | 圆活塞半径 m |
| element.velocity_peak_m_s | 1 | 峰值法向表面振速 m/s，未与电压标定 |
| array.nx / ny | 12 / 12 | 两方向阵元数，总数 1–4096 |
| array.pitch_wavelengths | 0.5 | 阵元间距 / 波长；间距必须至少等于直径 |
| array.apodization | uniform | uniform / hann，按振速平方和归一化 |
| array.phase_error_std_deg | 0 | 固定阵元相位误差标准差，单位度 |
| focus.x_m / y_m / z_m | 0 / 0 / 0.05 | 中心目标点，必须位于显示体积内 |

## 网格、调制与轨迹

| 位置 | 默认值 | 解释 |
| --- | ---: | --- |
| grid.x_min_m / x_max_m | −0.02 / 0.02 | 目标平面 x 范围 |
| grid.y_min_m / y_max_m | −0.02 / 0.02 | 目标平面 y 范围 |
| grid.z_min_m / z_max_m | 0.01 / 0.08 | 竖直截面的 z 范围 |
| grid.nx / ny / nz | 101 / 101 / 121 | 含端点的线性网格数，每轴至少 3 |
| modulation.kind | burst | cw / burst / sinusoidal |
| modulation.frequency_hz | 100 | 包络频率，非载波频率 |
| modulation.duty_cycle | 0.5 | 脉冲占空比，(0,1] |
| modulation.depth | 1 | 幅度调制深度，[0,1] |
| modulation.duration_s | 0.05 | 输出波形时长；移动预设为 1 秒 |
| modulation.sample_rate_hz | 20000 | 包络采样率，至少 20 倍调制频率 |
| trajectory.kind | static | static / line / circle |
| trajectory.radius_m | 0.005 | 圆半径，单位 m |
| trajectory.line_length_m | 0.015 | 往复直线全长，单位 m |
| trajectory.duration_s | 1 | 完成 loops 次路径的时间 |
| trajectory.frames | 61 | 含重复端点的轨迹采样数，3–501 |
| trajectory.loops | 1 | 周期数；每周期至少 12 个间隔 |
| engine.chunk_points | 2048 | 单块最多场点数，1–65536 |
| engine.max_transfer_mb | 128 | 传递矩阵及临时数组的估算预算 MiB，非整个进程硬上限 |

每个静态平面最多 100 万点，轨迹输出最多 1000 万个平面采样值，包络最多 200 万点。超出边界会要求减小配置。整个运动轨迹必须留在目标平面范围内。

修改载波会同时改变波长和以波长定义的阵元间距。固定真实间距可选择 array.pitch_mode="physical" 并设置 array.pitch_m。旧配置仍按波长倍数解释。主界面使用较快的 81×81 目标网格；命令行默认预设为 101×101，指标微小差异来自采样。

## 预设

| 文件 | 用途 |
| --- | --- |
| quick.toml | 快速安装验证 |
| midair_touchpoint.toml | 默认静态触点与 100 Hz 脉冲 |
| midair_sinusoidal.toml | 正弦幅度调制 |
| midair_line.toml | 15 mm 往复直线 |
| midair_circle.toml | 半径 5 mm 圆形路径 |

## 输出格式

一次 `run` 保存 config.toml、metrics.json、environment.json、arrays.npz、图片和 manifest.json。图片绘图使用英文轴标题与 SI 派生单位，避免跨平台中文字体缺失。

NPZ 的主要字段：

| 字段 | 形状 / 单位 |
| --- | --- |
| element_positions_m | (N,3)，阵元位置 m |
| velocity_weights_m_s | (N,)，复峰值振速 m/s |
| x_m / y_m / z_m | 一维坐标，m |
| pressure_xy_peak_pa | (ny,nx)，复峰值声压 Pa |
| pressure_xz_peak_pa | (nz,nx)，复峰值声压 Pa |
| pressure_xy_rms_pa | (ny,nx)，RMS 声压 Pa |
| intensity_xy_w_m2 | (ny,nx)，近似声强 W/m² |
| radiation_xy_pa | (ny,nx)，载波平均、未调制辐射压 Pa |
| time_s / envelope | (S,)，包络时间与无量纲幅度 |
| commanded_focus_radiation_pa | (S,)，移动指令点的已调制辐射压 Pa |
| plane_force_time_n | (S,)，目标平面内已调制合力 N |
| trajectory_time_s | (T,)，慢变轨迹时刻 s |
| trajectory_points_m | (T,3)，指令焦点 m |
| trajectory_radiation_pa | (T,ny,nx)，未调制辐射压帧 |
| trajectory_mean_unmodulated_radiation_pa | (ny,nx)，整段路径时间平均、未调制图 |

静态场景 T=1。width_m=null 表示不存在可报告的完整宽度，结合 reason 区分零信号和边界截断。JSON 禁止 NaN/Infinity，保持可读性和跨语言兼容。NPZ 可以用 `numpy.load(path, allow_pickle=False)` 读取。

## 0.2.0 配置扩展

schema_version 默认为 2；无版本旧配置迁移为 1，保留旧随机算法。原字段与单位不变。

| 字段 | 默认值 | 含义 |
| --- | --- | --- |
| array.pitch_mode | wavelength | wavelength / physical |
| array.pitch_m | 0.0015676416819012796 | physical 模式实际间距 m |
| imperfections.amplitude_cv | 0 | 幅度 CV，0–2；非负对数正态响应 |
| imperfections.position_std_m | 0 | x/y 位置标准差 m |
| imperfections.failure_probability | 0 | 每阵元失效概率，0–1 |
| imperfections.phase_bits | 0 | 0 连续；1–16 量化位数 |
| imperfections.rng | portable-v1 | 新算法；旧配置为 legacy |

NPZ 新增 nominal_positions_m、error_phase_rad、error_amplitude_gain、error_offsets_m、error_active；element_positions_m 表示实际位置。metrics 新增 model_version、sample_rng、sample_seed、target_pressure_rms_pa。理想配置下几何不变。

任务字段和输出见 [实验工作流指南](laboratory.md)。
