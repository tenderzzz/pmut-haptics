# 实验工作流（0.2.0）

新增“实验库、参数扫描、质量检查、鲁棒性”页签，保留单文件离线运行。建议先保存默认实验，再将振速改为 0.5 m/s，运行并保存第二条记录；选中两条记录比较。随后扫描焦距 30–70 mm，执行质量检查，再设置误差运行鲁棒性试验。

## 实验记录

保存最近一次计算的参数、静态场图、指标、模型版本、实际误差和匹配的质量报告。左侧尚未计算的改动不进入记录。支持打开快照、复制参数、编辑名称和备注、删除、备份恢复。

IndexedDB 与浏览器和文件位置有关，清理数据、移动 HTML 或隐私模式可能影响可用性；JSON 备份是跨环境迁移方式。恢复前验证记录，重复 ID 跳过，不覆盖已有记录。存储失败时保留本页记录并提示下载备份。

快照不含完整轨迹帧和波形；需要回放时重新运行，需要归档时单独导出全部数据。最多四条记录使用统一声压色标，只有 x/y 网格和焦平面高度相同时计算差值，不隐式重采样。可打印报告包含图、指标、检查结果、配置和实际误差；可在浏览器打印为 PDF。

## 任务接口和命令

独立任务 JSON 的 `schema_version` 为 1，`kind` 为 `sweep` 或 `robustness`，`config` 是完整仿真配置。任务要求显式静态配置；网页提供静态副本选项，不改动原实验。

```sh
.venv/bin/pmut-haptics sweep --task configs/sweep_focus.json --output outputs/focus-scan
.venv/bin/pmut-haptics robustness --task configs/robustness.json --output outputs/robustness
.venv/bin/pmut-haptics quality --config configs/laboratory_reference.toml --reference --output outputs/quality
```

| 任务字段 | 含义 |
| --- | --- |
| parameter | carrier_hz、focus.z_m、array.side、array.pitch_m、array.pitch_wavelengths、element.velocity_peak_m_s |
| values | 显式数值列表；若存在则优先于范围字段 |
| start / stop / count | 含端点等间距范围；鲁棒性使用 count 指定样本数 |
| normalization | fixed_sum_squared_velocity（默认）或 per_element |
| frequency_pitch | physical（默认）或 wavelength |
| quantization_comparison | 鲁棒性专用；true 比较连续相位及 3/4/6/8 位 |

JSON 一律采用 SI 单位，网页负责 kHz/mm 转换。阵列边长同时设置 nx/ny，非整数记为无效。扫频默认固定起始真实间距；wavelength 固定起始真实间距对应的波长倍数。阵元数变化时默认保持名义振速平方和，这不是等电功率；扫描振速时以指定值为准。

网页最多扫描 50 组、运行 100 个鲁棒性样本；量化比较计算量为五倍。Python 上限分别为 10000 组和 100000 个样本，输出内存和磁盘需求随规模增长。参数非法、阵元重叠或超出计算限制的行标为无效，保存原因，不重抽。

输出目录必须不存在。批量输出包含 task.json、逐条刷新的 rows.jsonl、results.json、metrics.csv、环境和 SHA256 清单。Ctrl-C 或网页取消保留已完成行。每行保存配置和实际误差，不默认保存完整声场。

Python API：`pmut_haptics.tasks.batch(task, on_row=callback, should_stop=cancel_callback)`；`quality(config, reference=True)` 返回质量报告。

## 数值质量检查

- 网格加密：区域不变，各轴从 n 点加至 2n−1 点，比较平面峰值、x 主瓣宽度和有限区域合力。
- 区域扩大：目标平面宽高翻倍、中心不变、采样间距不变，比较积分合力；不声称得到全空间总力。
- 默认相对变化阈值分别为 2% 和 5%，可调整，仅为工程参考。
- 诊断平面最多 100000 点，总场点×阵元数预算 35000000；网页诊断每轴最多 601 点。超预算显示未检查。
- 零基准、截断或缺失指标显示不可评价；独立显示主瓣截断和横向焦点误差。
- Python 独立积分在焦点及其 x/y ±1λ 的九个点叠加各圆盘积分。24×48 与 48×96 积分阶数的相对 L2 变化不超过 0.1% 后，才以 2% 参考阈值评价快速核误差。积分预算 100000000 项，仅支持无衰减介质。
- 在网页导出检查用 TOML，运行 `quality --reference`，再导入 quality.json；配置或模型版本不匹配时拒绝附加。

网格收敛、快速核误差和输入假设分别展示，不合成可信度分数。收敛不能证明圆活塞近似、法向辐射压或假设振速正确，不能证明人体可感知。

## 误差与随机约定

- 幅度为均值 1 的对数正态分布，以 CV 设置离散程度，sigma=sqrt(log(1+CV²))。
- 位置为 x/y 独立零均值高斯误差；相位为高斯误差；失效为独立伯努利变量。
- 名义位置决定控制相位，实际位置参与传播。先量化相位，再加入相位误差。幅度和失效后不重新归一化；误差在整条轨迹内保持固定。
- `portable-v1` 使用 xorshift32，零种子映射到 0x6D2B79F5，均匀数为 (state+0.5)/2^32。正态数采用无缓存 Box–Muller。
- 每阵元按相位、幅度、x、y 顺序抽四个正态数，再抽一个失效均匀数；零标准差不改变抽样顺序。
- 鲁棒性样本 i 的种子为 (base_seed+i) mod 2^32；不同量化位数复用相同样本。理想基准关闭误差和量化，保留驱动设置。
- 中位数、P5、P95 使用线性插值样本分位数，不是置信区间；无效和缺失单独计数，不补零。
- 无版本旧配置迁移为 schema 1 / legacy，保留原 NumPy 相位序列。非零 legacy 相位须在 Python 复现；切换 portable-v1 是新试验。

这些分布是仿真假设，不代表器件实测统计。

## 开发验证

```sh
.venv/bin/python scripts/build_html.py
.venv/bin/python -m pytest
.venv/bin/ruff check .
# 可选浏览器验收，需要 Playwright 和 Chromium
node tests/browser_laboratory.cjs
```

可用 `PMUT_PLAYWRIGHT_PATH` 指向已有 Playwright，`PMUT_PYTHON` 指定 Python。浏览器测试用隔离上下文和 file://，强制离线；证据存入 outputs/verification-v02/。测试涵盖保存恢复、对比、扫描、取消、检查报告、量化、窄屏和 Worker/存储降级。

本轮未加入硬件控制、电压标定或人体验证。
