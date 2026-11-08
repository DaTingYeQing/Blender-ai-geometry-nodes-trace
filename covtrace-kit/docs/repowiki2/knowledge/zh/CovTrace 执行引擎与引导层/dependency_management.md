## 概述

本仓库是一个面向 Blender Geometry Nodes 的 Python 工具链（执行引擎、引导层、卡片流水线等），但**未使用任何 Python 包管理器或依赖清单**。仓库根目录及子模块中不存在 `requirements.txt`、`pyproject.toml`、`setup.py`、`Pipfile`、`poetry.lock`、`Pipfile.lock`、`setup.cfg` 等任何依赖声明或锁定文件。因此无法通过常规方式重建可复现环境。

## 已识别的外部依赖

通过扫描全部 `.py` 文件的 `import`/`from ... import`，仅发现以下非标准库依赖：

- **`bpy`** — Blender 官方 Python API（由宿主 Blender 提供，非 pip 安装）
- **`capstone`** — 反汇编库，被 `cards/disasm.py` 用于 x86_64 指令解码（`Cs, CS_ARCH_X86, CS_GRP_JUMP, CS_MODE_64, x86` 以及 `capstone.x86.X86_INS_CALL` 等符号）

其余所有导入均为 Python 标准库（`os`, `json`, `subprocess`, `argparse`, `concurrent.futures`, `collections`, `re`, `struct`, `shutil`, `tempfile`, `glob`, `traceback`, `runpy`, `time` 等）和本仓库内部包（`directories`, `registry`, `cards.*`, `gates.*`, `infra.*`, `tools.*`）。

## 关键观察

1. **无依赖版本约束**：`capstone` 的版本完全由运行环境的安装决定，仓库不记录其版本号，也不进行校验。
2. **无私有源/代理配置**：未发现 `pip.conf`、`~/.config/pip/pip.conf`、`PYPI_URL` 环境变量或类似机制。
3. **无 vendoring**：没有 `vendor/`、`third_party/` 或内嵌源码。
4. **无 CI/构建钩子**：仓库根目录无 Makefile、CI YAML、Dockerfile 等自动化依赖安装流程；`bootstrap.py` 仅负责解析命令行参数并通过 `runpy.run_path` 启动目标脚本，不处理依赖检查。
5. **运行时容错策略缺失**：代码中对 `bpy` 和 `capstone` 均直接 `import`，未做 try/except 降级或友好报错，缺少依赖可用性探测逻辑。

## 结论

该仓库对依赖管理的现状是“零声明、零锁定、零校验”。唯一第三方库 `capstone` 与宿主 Blender 提供的 `bpy` 均以隐式假设的方式被消费，版本一致性和可复现性由外部流程（例如用户手动安装）保证。此模式在简单工具脚本中常见，但不具备工程化的依赖管理能力。