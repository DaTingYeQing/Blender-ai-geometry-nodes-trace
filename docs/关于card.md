# 关于 Card

## 原始数据

| raw key | 文件 | 产生者 | 内容 |
|---|---|---|---|
| `raw:functions` | `functions.bin` | `gates/calls.py` | `u64` 数组，每项是 **函数 RVA + 1** |
| `raw:edges` | `edges.bin` | `gates/calls.py` | `u64` 打包边：高 32 位 caller RVA，低 32 位 callee RVA |
| `raw:returns` | `returns.bin` | `gates/calls.py` | `u64` 打包返回边：高 32 位 **callee** RVA，低 32 位 **caller** RVA（和 edges 相反） |
| `raw:timings` | `timings.bin` | `gates/calls.py` | `BTIM` 头 + 记录：`key(rva+1) / count / self ticks / inclusive ticks` |
| `raw:coverage` | `window.profraw` | `gates/coverage.py` | LLVM coverage profile |

另外还有两个不是 raw key、但所有相关卡片都能拿到的输入：

- `ctx.blender`：插桩后的 `blender.exe`，提供机器码；
- `ctx.pdb`：对应 PDB，提供 `name / file / line / size`。

> 注意 RVA 口径：`functions.bin` 和 `timings.bin` 存的是 `rva+1`；
> `edges.bin` 和 `returns.bin` 是原始 RVA。

## 每张卡翻译什么

| 卡片 | 输入 | 输出 | 翻译内容 |
|---|---|---|---|
| `edge` | `raw:functions`、`raw:edges`、exe/PDB | `edge.json` | 把函数 RVA 解析成 `name/file/line/module/rva/va`；把边解析成 `caller/callee` 下标和 `caller_rva/callee_rva`；按 RVA 去重 |
| `disasm` | `raw:functions`、exe/PDB | `_internal/disasm.json`（`--test` 发布） | 按 PDB `Size` 取代码字节，用 Capstone 反汇编；统计指令数、调用、跳转、return、栈帧、全局引用、FP/SIMD 等；识别并扣除 `__cyg_profile_func_*` 钩子调用 |
| `return` | `edge.json`、`raw:returns` | `_internal/return.json`（`--test` 发布） | 把 `returns.bin` 的 callee/caller RVA 直接映射到 edge 函数索引，生成每个函数的 `returns_to`；不再查 PDB |
| `between` | `edge.json`、`return.json`、`--node` | `between.json` + `boundary.json` | 解析 node 入口，算 Start/Finally（直接 return 关系），再在调用图上做向下闭包 ∩ 反向向上闭包；全部按 RVA 遍历 |
| `coverage` | `raw:coverage`、exe/PDB、LLVM 工具 | `coverage.json` | `llvm-profdata merge` → `llvm-cov show` 取执行行区间；`llvm-cov export lcov` 取函数计数；默认只保留 `source/` + `intern/` |
| `timing` | `raw:timings`、exe/PDB | `_internal/timing.json`（`--test` 发布） | 解析 `BTIM` 记录，把 ticks 换成 ns，解析 RVA 到函数名，输出 `rva/count/total_*/mean_*/self_share` |
| `metrics` | `disasm.json`、`timing.json`、`raw:edges` | `functions.jsonl` | 按 RVA 合并三份数据；从 `edges.bin` 算每个 caller 的不同 callee 数作为 `out_degree`；保留源字段，派生字段不落盘 |

## 卡片之间的依赖

```text
edge ─┬─> return ──> between
      └─> (metrics 用 raw:edges)
disasm ──────────────┐
timing ──────────────┴─> metrics
coverage（独立）
```

- `between` 只依赖 `edge.json + return.json`，不读原始二进制；
- `metrics` 不依赖 PDB，也不依赖 `edge.json`，出度直接读 `edges.bin`；
- `return` 现在只依赖 `edge.json + returns.bin`，不再做名字匹配。

## 公开 / 内部产物

默认公开：

```text
edge.json
boundary.json
between.json
coverage.json
functions.jsonl
run.json（manifest）
```

默认内部、卡片跑完后删除：

```text
disasm.json
return.json
timing.json
```

`--test` 会把这三个内部 JSON 发布到顶层。内部文件在运行期间仍然会写到
`_internal/`，因为 `between` 和 `metrics` 需要读它们。
