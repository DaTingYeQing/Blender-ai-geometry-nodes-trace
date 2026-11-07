# 关于 Card

## 原始数据

| raw key | 文件 | 产生者 | 内容 |
|---|---|---|---|
| `raw:functions` | `functions.bin` | `gates/calls.py` | `u64` 数组，每项是 **函数 RVA + 1** |
| `raw:edges` | `edges.bin` | `gates/calls.py` | `u64` 打包边：高 32 位 caller RVA，低 32 位 callee RVA |
| `raw:timings` | `timings.bin` | `gates/calls.py` | `BTIM` 头 + 记录：`key(rva+1) / count / self ticks / inclusive ticks` |
| `raw:coverage` | `window.profraw` | `gates/coverage.py` | LLVM coverage profile |

另外还有两个不是 raw key、但所有相关卡片都能拿到的输入：

- `ctx.blender`：插桩后的 `blender.exe`，提供机器码；
- `ctx.pdb`：对应 PDB，提供 `name / file / line / size`。

> 注意 RVA 口径：`functions.bin` 和 `timings.bin` 存的是 `rva+1`；
> `edges.bin` 是原始 RVA。

## 每张卡翻译什么

| 卡片 | 输入 | 输出 | 翻译内容 |
|---|---|---|---|
| `edge` | `raw:functions`、`raw:edges`、exe/PDB | `edge.json` | 把函数 RVA 解析成 `name/file/line/module/rva/va`；把边解析成 `caller/callee` 下标和 `caller_rva/callee_rva`；按 RVA 去重 |
| `disasm` | `raw:functions`、exe/PDB | `_internal/disasm.json`（`--test` 发布） | 按 PDB `Size` 取代码字节，用 Capstone 反汇编；统计指令数、调用、跳转、return、栈帧、全局引用、FP/SIMD 等；识别并扣除 `__cyg_profile_func_*` 钩子调用 |
| `coverage` | `raw:coverage`、exe/PDB、LLVM 工具 | `coverage.json` | `llvm-profdata merge` → `llvm-cov show` 取执行行区间；`llvm-cov export lcov` 取函数计数；默认只保留 `source/` + `intern/` |
| `timing` | `raw:timings`、exe/PDB | `_internal/timing.json`（`--test` 发布） | 解析 `BTIM` 记录，把 ticks 换成 ns，解析 RVA 到函数名，输出 `rva/count/total_*/mean_*/self_share` |
| `metrics` | `disasm.json`、`timing.json`、`raw:edges` | `functions.jsonl` | 按 RVA 合并三份数据；从 `edges.bin` 算每个 caller 的不同 callee 数作为 `out_degree`；保留源字段，派生字段不落盘 |
| `filter` | `functions.jsonl` | `filter.json` | 占位卡片：当前保留全部函数，输出 rva 决策列表 |
| `diff` | `raw:functions`、`raw:edges`、自动写入的 `options.diff_against` | `diff.json` | eval 含 `NODE` 时，普通 run 自动执行 before/after，并在 after 中与 before cache 做边集合差；节点取边差两端；无 `NODE` 时跳过 |

## 卡片之间的依赖

```text
edge ──> (metrics 用 raw:edges)
disasm ──────────────┐
timing ──────────────┴─> metrics ──> filter ──> diff（可选，最后）
coverage（独立）
```

`diff` 是最后一张卡：读当前 run 的 `functions.bin/edges.bin`（或已生成的 `edge.json`），
再读 `options.diff_against` 指向的 before 目录里的 `functions.bin/edges.bin`（或 `edge.json`），
按 RVA 求边差，节点取边差两端（另加没有任何边的增减函数兜底），写 `diff.json`。

- `metrics` 不依赖 PDB，也不依赖 `edge.json`，出度直接读 `edges.bin`；
- `filter` 只读 `functions.jsonl`，输出 rva 决策列表。

## 公开 / 内部产物

默认公开：

```text
edge.json
coverage.json
functions.jsonl
filter.json
run.json（manifest）
```

eval 含 `NODE` 时，after 运行还会公开 `diff.json`。

默认内部、卡片跑完后删除：

```text
disasm.json
timing.json
```

`--test` 会把这两个内部 JSON 发布到顶层。内部文件在运行期间仍然会写到
`_internal/`，因为 `metrics` 需要读它们。
