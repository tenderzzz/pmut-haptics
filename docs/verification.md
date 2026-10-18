# 交付验证记录

**当前本地 0.2.0 验证见 [新版记录](verification-v02.md)。以下为 0.1.0 的历史记录，保留原日期和证据。**

最近发布核验：**2026-10-17**（Asia/Shanghai）；原交付检查为 2026-10-15。数值场景和性能测量在 2026-10-14 完成，随后修正了 Streamlit 界面的主题对比度与坐标显示比例，并新增独立 HTML。Python 计算核未再改变，HTML 使用独立实现并与之对照。

## 已实际通过

| 项目 | 证据 |
| --- | --- |
| 静态检查 | Ruff：All checks passed |
| 自动测试 | **43 passed**；原 33 项加 HTML 10 项，包括 6 场景逐点数值对照，无跳过 |
| 主场景文件校验 | 5 组实验，共 37 个文件 SHA256 通过 |
| 数值验证 | 轴向解析解、圆盘积分收敛、指定空气场点近似误差、双后端一致性全部达标 |
| 完整复现 | 5 个空气预设、原始/修正水中模型、两种归一化共 18 组扫描、三档基准均运行成功 |
| 浏览器检查 | 正式安装入口启动，RMS 声压 142.72 Pa、辐射压 0.2885 Pa、区域合力 19.26 μN、宽度 10.26 mm 正常显示；主题和声场坐标比例已复查 |
| 独立安装 | 构建 wheel，安装到独立环境，从源码目录外运行，移除 PYTHONPATH；不装 Streamlit 仍能运行默认声场和历史回归 |
| 核心结果一致性 | 独立环境最大 RMS 声压 142.7178514608478 Pa，与核验快照一致 |
| 包内资源 | 恢复附录代码与 source_manifest 均包含在 wheel 内；没有打包私人 PDF |

最新完整测试输出见 [HTML 增补测试日志](results/html/test-report.txt)，原 33 项记录保留在 [test-report.txt](results/test-report.txt)；安装检查见 [package-smoke.json](results/package-smoke.json)。精简快照的完整性可通过 scripts/verify_artifacts.py 检查。原始完整日志位于 outputs/release-check-20261015/。

## GitHub 发布核验（2026-10-17）

- 本地完整测试：43 passed，无跳过；包含离线 HTML 与维护源码一致性、浏览器/Python 数值对照。
- 静态检查：Ruff，All checks passed。
- SHA256 再次通过校验：20 个文档快照文件，以及 5 组本地实验中的 37 个文件。
- 仓库：[tenderzzz/pmut-haptics](https://github.com/tenderzzz/pmut-haptics)，包含源码、配置、测试、文档、验证快照和独立 HTML。
- 发布入口：[在线实验台](https://tenderzzz.github.io/pmut-haptics/)与 [Release 下载](https://github.com/tenderzzz/pmut-haptics/releases/latest)。网站首页与离线 HTML 使用相同构建内容，GitHub 源码预览不作为运行入口。
- 虚拟环境、缓存、outputs 和 dist 按忽略规则保留在本地；原实习报告与第三方论文全文位于工程目录之外。

## 独立 HTML 增补

已验证默认计算、振速缩放、轨迹回放、逐帧查看、配置导入、基准对比、五种导出和取消计算。确认预览端口无监听后，已加载的页面仍能改变参数并重新计算。宽屏与 390×844 窄屏布局已检查。HTML 现已补回三维阵列与目标位置，验证了参数联动、旋转缩放、视角切换、重算保留视角和 PNG 导出。浏览器自动化不支持 file://，因此本地文件协议和各品牌浏览器兼容性未列为实测。详见 [HTML 验证记录](html-verification.md)。

## 远程与平台验证范围

2026-10-17，首次提交 1dbc622 的 [GitHub Actions 验证](https://github.com/tenderzzz/pmut-haptics/actions/runs/39011404415) 已通过：Ubuntu 与 macOS 均完成依赖安装、Ruff、完整测试、离线 HTML 构建、Python 包构建和快速场景运行。后续提交状态见 [仓库 Actions](https://github.com/tenderzzz/pmut-haptics/actions)。Windows 的完整基准未适配；其他平台安装与数值行为尚未实际检验。

仿真并不等于器件实测。电压到振速标定、皮肤受力/位移、人体感知和硬件闭环都不在本次交付的验证范围内。

## 交付文件

- pmut-haptics.html：独立 HTML 实验台，可直接复制或转发；dist 下提供相同副本。
- web：浏览器计算、交互、样式和模板的维护源码。
- README 与 docs：安装、模型、参数、来源审计、实验结果、性能和面试演示。
- src、tests、configs、scripts：可继续开发的完整源码与验证流程。
- dist/pmut_haptics-0.1.0-py3-none-any.whl：独立安装包。
- dist/pmut_haptics-0.1.0.tar.gz：标准源码分发包。
- dist/pmut-haptics-0.1.0-project.zip：便于打开浏览的项目压缩包。
- dist/checksums.sha256：交付包校验和。

压缩包不包含虚拟环境、第三方论文全文、私人实习 PDF 或 outputs 下的大型数组。项目仍保留全部本地完整实验结果。
