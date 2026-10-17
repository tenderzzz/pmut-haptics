# 安装与复现

## 无需安装的 HTML

直接用浏览器打开根目录 pmut-haptics.html 即可进行空气触觉实验。详见 [HTML 指南](html.md)。以下环境用于完整 Python 工程和开发验证。

## 环境

本次实际验证：macOS 26.6.2 arm64、Python 3.12.14、uv 0.12.6。依赖版本固定在 uv.lock。完整性能基准使用 Unix 的 resource 模块，支持 macOS/Linux；Windows 的完整基准尚未适配或验证。

在终端进入项目根目录。已有 uv 时：

```sh
sh scripts/setup.sh
.venv/bin/python scripts/doctor.py
.venv/bin/pmut-haptics --version
```

setup.sh 会同步锁定依赖、安装界面和开发工具，并重新安装当前项目。第一次需要下载依赖，之后可复用缓存。遇到慢速网络可将 UV_HTTP_TIMEOUT 设置为 120、UV_CONCURRENT_DOWNLOADS 设置为 2 后重试同步，不需要删除结果目录。

没有 uv 时，可用 Python 3.12 的常规方式安装；这种方式不保证与 uv.lock 的依赖版本完全一致：

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install ".[demo]" pytest ruff build
```

Windows 可将解释器路径替换为 `.venv\Scripts\python.exe`，命令入口为 `.venv\Scripts\pmut-haptics.exe`。本次只实际验证了 macOS；CI 配置覆盖 Ubuntu/macOS，但未在远程平台执行。

### 为什么使用普通安装

本机 iCloud 目录会把可编辑安装用到的 .pth 文件标为隐藏；Python 3.12.14 的 site 加载过程会跳过隐藏 .pth，导致“安装成功但找不到模块”。因此 setup.sh 使用 `uv sync --no-editable`，不依赖该文件。

修改源码后，测试通过 pytest 的 pythonpath 使用 src 下的代码；已安装的命令行则需要重新运行 setup.sh 才更新。开发时也可在 macOS/Linux 使用：

```sh
PYTHONPATH=src .venv/bin/python -m pmut_haptics.cli run --config configs/quick.toml --output outputs/dev-check
```

不要用一个已安装的旧 CLI 验证刚改动但尚未重装的源码。

## 运行主场景

```sh
.venv/bin/pmut-haptics run --config configs/midair_touchpoint.toml --output outputs/touchpoint
.venv/bin/pmut-haptics run --config configs/midair_sinusoidal.toml --output outputs/sinusoidal
.venv/bin/pmut-haptics run --config configs/midair_line.toml --output outputs/line
.venv/bin/pmut-haptics run --config configs/midair_circle.toml --output outputs/circle
.venv/bin/pmut-haptics demo
```

界面默认绑定 127.0.0.1:8501。端口占用时使用 `demo --port 8502`。图像渲染、浏览器和文件写入不计入内核性能测试。界面改参数后保留上次结果，必须点击“运行仿真”才更新，提示条会明确指出这一点。

原始数组读法：

```python
import json
import numpy as np

arrays = np.load("outputs/touchpoint/arrays.npz", allow_pickle=False)
metrics = json.load(open("outputs/touchpoint/metrics.json", encoding="utf-8"))
print(arrays["pressure_xy_peak_pa"].shape)
print(metrics["pressure_x_minus6db"])
```

## 测试与模型校验

```sh
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest -q
.venv/bin/python scripts/validate_models.py --output outputs/model-check
```

独立模型校验要求：轴向积分相对误差 <1e−9，积分阶数收敛误差 <1e−6，指定三点的快速近似误差 <1%，相同物理核两种实现的相对误差 <1e−12。

测试覆盖基本物理性质、数值回归、边界输入、零振速、轨迹、序列化和界面切换。原 Python 工程包含 33 项用例，HTML 新增 10 项（需要 Node.js）；数量均是 pytest 展开后的用例数，不代表独立物理实验数量。没有 Node 时会跳过浏览器计算核对照，交付验证应确保没有此类跳过。

## 全部证据一次生成

```sh
.venv/bin/python scripts/reproduce_all.py --output outputs/full-run
```

它直接调用当前源码，依次生成 5 个空气场景、原始水中结果、修正水中结果、两种归一化方式各 9 个参数组合、三档性能测试，以及独立模型校验。各命令的输出保存为日志；失败时停止并显示原因。全套带图结果与 NPZ 会占用更多磁盘空间。

单独运行：

```sh
.venv/bin/pmut-haptics reproduce --profile original --output outputs/report-original
.venv/bin/pmut-haptics reproduce --profile corrected --output outputs/report-corrected
.venv/bin/pmut-haptics sweep --normalization fixed_sum_squared_velocity --output outputs/scan-fixed
.venv/bin/pmut-haptics sweep --normalization per_element --output outputs/scan-per-element
.venv/bin/pmut-haptics benchmark --repeats 5 --output outputs/bench
```

所有输出路径都应为**新目录**。原始文献和报告 PDF 不需要复制到安装环境；恢复代码随包提供，并在加载时检查哈希。

## 核验与预期差异

```sh
.venv/bin/python scripts/verify_artifacts.py outputs/full-run
.venv/bin/python scripts/verify_artifacts.py docs/results
```

该工具检查已有 manifest 中列出的文件哈希，不会声称所有工作流都产生同一格式的 manifest。主 run 场景包含逐文件 manifest；完整复现的历史结果、扫描和基准另保存 JSON/环境信息。本次精简快照也有独立 manifest。

固定配置、种子和后端时数组应在数值容差内一致；不同平台的 BLAS、库版本或浮点归约顺序可能带来极小差异。耗时、环境字符串、创建时间、压缩包元数据不会逐字节重现。不要用性能耗时是否完全相同作为数值正确性的判据。

## 构建与分发

```sh
.venv/bin/python scripts/build_html.py
uv build
.venv/bin/python scripts/package_project.py
```

dist 下产生 wheel 和源码包。wheel 只包含运行包与恢复代码；源码包还包括配置、测试、文档、精简证据、web 源码和独立 HTML。第三方论文、私人实习 PDF、虚拟环境和完整 outputs 均不打包。

核心运行只需 NumPy、SciPy、Matplotlib；交互界面使用 demo extra。可在一个全新环境安装 wheel，从项目目录之外运行 `pmut-haptics run` 和历史复现入口，以检验是否存在本机绝对路径依赖。具体执行结果见 [交付验证](verification.md)。
