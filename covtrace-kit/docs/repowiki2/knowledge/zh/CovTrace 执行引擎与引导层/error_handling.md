## 1. 总体方式

该仓库没有统一的异常体系或错误码枚举，而是采用两种风格并存：

- **Blender 侧（`frag/`）**：定义一个业务异常类 `TargetError`，所有针对 Blender 目标文件、节点树、测量节点的校验失败都通过它表达。
- **宿主侧（`cards/`、`engine.py`、`bootstrap.py`、`tools/`）**：大量直接 `raise RuntimeError(...)`，并配合 Python 内置异常 `KeyError`、`ValueError`、`TypeError`。没有自定义异常基类，也没有全局错误处理器、中间件或日志统一入口。

因此，本仓库的错误处理是**零配置、无框架**的：靠调用方 `try/except` 和顶层 `fail()` 函数把异常转成退出码。

## 2. 关键文件

| 文件 | 角色 |
|---|---|
| `frag/targeting.py` | 唯一自定义异常 `TargetError(Exception)` 的定义处，以及所有 Blender 端校验逻辑 |
| `engine.py` | 顶层编排器；捕获 `targetfile.TargetError` 后转调 `fail(str(exc))` |
| `cards/base.py` | 卡片上下文；对缺失 raw / unregistered product 抛 `RuntimeError` |
| `cards/disasm.py`、`cards/timing.py`、`cards/diff.py`、`cards/symbols.py` | 各卡片解析二进制产物时直接 `raise RuntimeError(...)` |
| `bootstrap.py` | 启动参数与 socket 绑定校验，抛出 `RuntimeError` |
| `frag/backend.py`、`frag/validate.py` | Blender 侧求值脚本包装层，用 `try/except Exception` 兜底并把异常字符串传回宿主 |

## 3. 架构与约定

### 3.1 Blender 侧异常通道

`frag/targeting.py` 定义：

```python
class TargetError(Exception):
    pass
```

随后所有目标解析失败（缺少测量节点、节点名不唯一、Group Output 个数不对、phase 未知等）均 `raise TargetError("...中文消息...")`。这类异常在 `engine.py` 中被显式捕获：

```python
except targetfile.TargetError as exc:
    return fail(str(exc))
```

即：**Blender 端的业务错误被序列化进 `str(exc)` 后交给宿主的 `fail()` 输出**。

### 3.2 宿主侧错误

宿主侧（`cards/`、`engine.py`、`bootstrap.py`）几乎全部使用 `RuntimeError`，例如：

- `cards/base.py:raw()` — raw 文件不存在
- `cards/base.py:product()` — 未注册的产品键
- `cards/disasm.py` — PE 头校验失败
- `cards/timing.py` — timings.bin magic/version 校验失败
- `cards/symbols.py` — PDB 加载失败
- `bootstrap.py` — 参数校验失败（如 `--phase` 取值、socket 映射缺失、`evaluate(ctx)` 签名不匹配等）

这些 `RuntimeError` 通常不会被更上层的 `try/except` 捕获，会沿调用栈冒泡到 `main()` 所在的最外层，由 Python 解释器打印 traceback 并返回非零退出码。

### 3.3 Blender 侧容错边界

`frag/backend.py` 与 `frag/validate.py` 在 Blender 进程内执行用户脚本时，使用 `try/except Exception` 包裹整个执行体，并把异常对象以某种形式（字符串）传回宿主；这样即使用户代码抛任意异常也不会导致 Blender 进程崩溃，而是被记录为评估结果的一部分。

### 3.4 卡片流水线中的错误传播

`cards/base.py` 中 `TranslationCard.build()` 是一个抽象方法，默认 `raise NotImplementedError`，强制子类实现；其他卡片若遇到不可恢复数据（如 raw 缺失、产品未注册），则抛 `RuntimeError`，让上层调度器感知失败。

## 4. 观察到的约定与约束

- **Blender 端业务错误统一使用 `TargetError`**：所有位于 `frag/targeting.py` 的校验分支都以 `raise TargetError(...)` 结束，这是该模块内的稳定约定。
- **宿主端错误使用裸 `RuntimeError`**：除 `TargetError` 外未见其它自定义异常类；所有“输入非法”“资源缺失”“格式不支持”均以 `RuntimeError` 表达。
- **没有全局错误处理器**：未发现 `sys.excepthook` 重写、logging 级别配置或错误上报中间件。
- **异常消息使用中文**：`TargetError` 与多数 `RuntimeError` 的消息均为中文（如“暂不支持包含 Repeat/Foreach/Simulation 区域”“timings.bin magic mismatch”），便于终端用户阅读。
- **部分异常链被刻意断开**：`cards/base.py` 中 `product()` 使用 `from None` 丢弃原始 `KeyError` 的 cause，只暴露最终 `RuntimeError`。
- **用户脚本异常被隔离**：`frag/backend.py` 与 `frag/validate.py` 用 `except Exception` 捕获用户代码抛出的任何异常，防止 Blender 子进程崩溃。

## 5. 缺口

- 没有统一的错误类型基类或错误码表；不同模块各自 `raise RuntimeError(...)`。
- 没有结构化错误对象（仅字符串消息）。
- 没有日志级别或统一 logger 接入（日志主题由另一个文档覆盖）。
- `except Exception` 的使用范围较广，有些只是兜底而非语义化捕获。