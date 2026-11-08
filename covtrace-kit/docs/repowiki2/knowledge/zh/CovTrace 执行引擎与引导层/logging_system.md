## 1. 使用的系统/方法

仓库没有引入任何第三方日志框架（如 `logging`、`loguru`、`structlog`），也没有自定义 logger 模块。所有可观测性输出全部使用 Python 标准库的 `print()`，并遵循一个约定：普通信息输出到 stdout，错误/告警信息输出到 stderr。

- 成功/进度类消息以 `>> ` 前缀开头，例如 `print(">> boundary:", ...)`、`print(">> raw:", ...)`、`print(">> products:", ...)`。
- 失败/异常类消息以 `!! ` 前缀开头，并通过 `file=sys.stderr` 定向到标准错误流，例如 `print("!! " + message, file=sys.stderr)`、`print("!! coverage work dir kept:", temp_dir)`。

文档 `docs/日志.md` 实际记录的是产物与卡片流水线变更记录，并未定义日志规范；真正的行为由源码中重复出现的 `>>` / `!!` 模式体现。

## 2. 关键文件

- `engine.py`：核心入口，集中了大量 `print` 用于打印运行参数、缓存路径、gates/cards 列表、dry-run 提示、校验失败等。
- `bootstrap.py`：Blender 引导脚本，用 `print` 输出边界分析、touched 节点、raw JSON 摘要。
- `frag/backend.py`：求值后端，打印执行的 Blender 命令、缺失 eval、校验失败以及 measure 前后路径。
- `cards/coverage.py`：覆盖率卡片，在临时工作目录保留时通过 `print` 报告。
- `tools/dot_graph.py`、`tools/svg_viewer.py`：辅助工具，同样用 `print` 打印 dot/svg 生成结果和找不到输入的错误。
- `infra/paths.py`、`infra/blender.py`、`infra/runkey.py`：基础设施层也有少量 `print`，用于调试路径、Blender 调用、run key 计算。

## 3. 架构与约定

- **无分层**：不存在 logger 初始化、全局配置、日志级别管理或 sink 路由。每个模块直接调用 `print`。
- **统一前缀约定**：
  - `>>`：表示“正向流程/中间状态”，默认 stdout。
  - `!!`：表示“问题/告警”，显式写到 stderr。
- **结构化字段以 JSON 内联字符串形式出现**：部分 `print` 调用会先 `json.dumps(..., ensure_ascii=False)` 再拼接，例如 `bootstrap.py` 中的 `raw`、`touched`、`boundary` 片段，以及 `engine.py` 中的 `options`、`products`。这并非真正的结构化日志（没有独立字段解析），只是把 JSON 文本嵌入一行人类可读输出。
- **调试输出混入生产代码**：大量 `print` 语句散落在业务逻辑中（如 `engine.py` 末尾的 `node/eval/blend/object/modifier/node_tree/param/blender/pdb/run key/hash8/options/run dir/cache dir/gates/cards` 逐行打印），说明日志主要用于交互式 CLI 调试，而非持久化到文件或管道。

## 4. 观察到的约定与约束

- **描述性约定**：错误消息统一通过 `print("!! ...", file=sys.stderr)` 输出；成功/进度消息统一以 `>> ` 开头并写入 stdout。该模式在所有被检出的文件中一致出现，但未被 lint 或类型检查强制。
- **未实现的功能**：仓库中没有日志级别（debug/info/warning/error）、日志轮转、文件 sink、JSON 结构化字段提取器、trace ID 或上下文绑定——这些能力均不存在。
- **文档缺失**：`docs/日志.md` 是产物变更日志，不是日志规范文档；因此上述前缀约定属于代码级惯例，而非书面要求。
- **唯一可见的规则来源**：若未来要新增日志点，现有代码中反复出现的 `>>` / `!!` 前缀模式是唯一可依据的行为事实；除此之外没有任何配置文件、装饰器、基类或注册表来约束日志格式。

总结：这是一个极轻量的日志方案——纯 `print` + 两套文本前缀，适合交互式 Blender 工具链的即时反馈，但不提供结构化、可聚合、可配置的日志能力。