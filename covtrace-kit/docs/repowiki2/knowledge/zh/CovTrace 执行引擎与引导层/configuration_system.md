## 概述

CovTrace 没有使用任何外部配置框架（无 `configparser`/`pydantic-settings`/`toml`/`.env`），而是采用**三层组合**的方式组装运行时配置：

1. **评估脚本中的 TARGET/NODE 字面量**（通过 AST 静态解析，不执行脚本）——声明 Blender 工程目标。
2. **命令行参数**（`argparse`，在 `bootstrap.py` / `engine.py` 中定义）——覆盖或补充 TARGET。
3. **Python 模块内的硬编码常量**（`directories.py`、`registry.py`）——工具路径、产物名、Card/Gate 注册表。

不存在集中式 schema 文件；所有约束以 Python 代码校验的形式存在。

## 关键文件与职责

| 文件 | 职责 |
|---|---|
| `infra/target.py` | 从 eval 脚本 AST 中提取 `TARGET = {...}` 与可选 `NODE = "..."`，提供 `merge()` 和 `validate()` |
| `bootstrap.py` | CLI 入口，解析 `--eval/--work/--node/--blend/--obj/--mod/--param/--phase/--measure-node`，调用 `targetfile.merge` |
| `engine.py` | 编排入口，接受 `run_key`、`options` 等并写入 `run.json` manifest |
| `infra/runkey.py` | 基于 eval 内容 + node + blender/pdb 指纹计算不可变 `run_key` |
| `infra/manifest.py` | `run.json` 的读写与 `new/duplicate/conflict/incomplete` 分类 |
| `infra/paths.py` | `norm()` / `safe_name()` / `file_fingerprint()` / `pdb_for()` |
| `directories.py` | 硬编码的外部工具路径 (`BLENDER_BIN_DIR`, `LLVM_BIN_DIR`, `GRAPHVIZ_BIN_DIR`) 与项目目录常量 |
| `registry.py` | Card/Gates 注册表与产物映射 `PRODUCTS` |

## 架构约定

### TARGET 配置模型
`infra/target.py` 定义了一个最小字典结构，强制字段为 `("blend", "object", "modifier")`，可选字段包括 `node_tree`、`param`。`validate()` 要求 `blend` 必须是一个存在的文件路径，`node_tree` 若给出则必须是字符串。

TARGET 的提取方式是**安全且严格的**：用 `ast.parse` + `ast.literal_eval` 只允许 Python 字面量字典，不允许任意表达式；缺失 `TARGET` 时抛出 `TargetError("求值脚本缺少 TARGET = {...}")`。

### 参数合并顺序
`targetfile.merge(target, blend="", obj="", mod="", param="")` 的行为是：**仅当 CLI 传入非空字符串时才覆盖对应字段**。因此优先级为：CLI > eval 脚本中的 TARGET。这个行为由 `merge()` 的 `if value:` 条件显式实现。

### 运行身份与缓存键
`infra/runkey.run_key(eval_path, node, blender, pdb, target=None, options=None)` 使用 SHA-256 把以下输入按固定版本头 `covtrace-runkey-v1\0` 拼接：
- eval 脚本全文
- node 名称
- blender.exe 与 pdb 的 `file_fingerprint`（路径:size:mtime_ns）
- target JSON（排序 key）
- options JSON（排序 key）

这保证了同一份 eval + 同一套 Blender/PDB 构建产物可命中缓存；不同构建产物会生成不同 run_key。

### Manifest 与生命周期
`infra/manifest.base()` 构造的 `run.json` 包含 `schema=1`、`run_key`、`hash8`、`node`、归一化后的 `eval/blend/blender/pdb`、`options`、时间戳以及空的 `gates/cards/counts` 容器。`classify()` 根据 `run_key` 是否相等判断 `duplicate` 或 `conflict`，不存在目录则为 `new`，存在但无 manifest 则为 `incomplete`。

### 外部工具路径：硬编码
`directories.py` 直接写死 Windows 绝对路径：
```
BLENDER_BIN_DIR = r"D:\blender-src\build_windows_x64_ClangCovTrace\bin"
LLVM_BIN_DIR = r"D:\tools\llvm\bin"
GRAPHVIZ_BIN_DIR = r"D:\qcachegrind074-x87"
SOURCE_DIR = os.path.normpath(os.path.join(ROOT, os.pardir, "blender-4.5.0"))
```
这些路径被编译成 `BLENDER_EXE` / `LLVM_COV_EXE` / `DOT_EXE` 等常量，后续通过 `subprocess` 调用。该设计使项目在另一台机器上需要修改 `directories.py` 才能运行。

### Card/Gates 注册表
`registry.py` 以 frozen dataclass 暴露 `Product`、`CardRegistration`，并维护全局 `PRODUCTS` 映射与 `CARDS` 列表。这是运行时“产品”配置的唯一来源，而非 YAML/TOML。

## 观察到的约定与约束

- eval 脚本必须定义顶层 `TARGET = {…}` 字典；缺失或类型不对时抛 `TargetError`（`infra/target.py:load`）。
- TARGET 的值必须是 `ast.literal_eval` 能解析的字面量，不允许函数调用或变量引用（`infra/target.py:load`）。
- `blend`、`object`、`modifier` 三个字段必填；`blend` 必须指向已存在的文件（`infra/target.py:validate`）。
- 通过 `--blend/--obj/--mod/--param` 传入的 CLI 参数仅覆盖非空值，不会清空 eval 中已有的字段（`infra/target.py:merge`）。
- 运行目录标识由 `run_key` 唯一决定；相同 key 会被标记为 `duplicate`，冲突 key 标记为 `conflict`（`infra/manifest.py:classify`）。
- 失败运行的原始产出会重命名为 `<hash8>.failed-<timestamp>` 并按 `keep` 参数保留最近若干项（`engine.py:_prune_cache` / `_keep_failed`）。
- 输出目录结构受 `directories.OUT_DIR` / `CACHE_DIR` / `INTERNAL_DIR` 控制，产物内部目录名为 `_internal`。
- 外部二进制路径（Blender、llvm-cov、dot）全部来自 `directories.py` 的硬编码常量，没有环境变量或配置文件覆盖机制。
- 没有发现 `.env`、`.yaml`、`.toml`、`.ini` 等独立配置文件；也没有对 `os.environ` 的系统级读取逻辑作为配置入口。

## 结论

CovTrace 的配置系统是**代码即配置**风格：TARGET 作为 eval 脚本内的 Python 字面量被 AST 解析，CLI 参数做有限覆盖，外部工具路径硬编码在 `directories.py`，运行身份通过 SHA-256 派生。它简单直接，适合单仓库内固定环境使用，但不支持多环境切换或外部配置注入。