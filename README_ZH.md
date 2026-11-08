# covtrace-kit

在插桩版 Blender 中采集函数调用、调用边、计时和行覆盖率，并翻译成可读的 JSON 与图表产物。


是这个`https://github.com/DaTingYeQing/Blender-ai-geometry-nodes`项目的扩展，此blender不可用来单独作为软件来使用。

## 目录结构

```text
covtrace-kit\
├─ CovTrace\                工具本体
│  ├─ engine.py             宿主入口（run / validate / translate）
│  ├─ bootstrap.py          Blender 内入口
│  ├─ directories.py        路径自动定位与环境变量
│  ├─ registry.py           闸门与翻译卡片注册
│  ├─ infra\                路径、run key、TARGET 解析、子进程与 manifest
│  ├─ gates\                数据采集闸门（calls、coverage）
│  ├─ cards\                翻译卡片（edge、disasm、timing、coverage、metrics 等）
│  ├─ frag\                 Blender 侧执行片段与校验脚本
│  ├─ tools\                dot 图与 SVG 查看工具
│  └─ docs\                 架构、卡片、日志、筛选说明
├─ changes\                 对 Blender 源码的 10 个改动文件参考副本
└─ docs\                    生成的仓库文档（repowiki / repowiki2）
```

## 运行目录约定

```text
blender-src\
├─ blender-4.5.0\              源码，covtrace-kit 在其中
├─ blender-4.5.0-trace-win64\  解压的运行时，blender.exe + blender_private.pdb
├─ llvm\                       LLVM 23.1.3，路径为 llvm\bin\llvm-cov.exe
└─ graphviz\                   可选，graphviz\bin\dot.exe
```

## 运行目录说明

- **源码**：`blender-4.5.0\` 是 Blender 源码根，本工具（`covtrace-kit\`）放在它内部；盘符和上层目录名不限。
- **运行时**：解压 Release 得到的 `blender-4.5.0-trace-win64\`。`blender.exe` 和 `blender_private.pdb` 必须同目录，PDB 不能改名。
- **LLVM**：必须是 23.1.3，解压后整理成 `llvm\bin\llvm-cov.exe` 的结构，不要保留 `clang+llvm-xxx` 这类外层目录。
- **Graphviz**：可选，只有生成 dot/SVG 图时需要；`dot.exe` 放在 `graphviz\` 下即可。
- **位置**：工具按上面的相对位置自动查找。任何一项放在别处或改了目录名，用对应的 `COVTRACE_*` 环境变量指定即可。

### 示例

假设统一根目录是 `D:\blender-src`，各组件应放成：

```text
D:\blender-src\
├─ blender-4.5.0\
│  └─ covtrace-kit\
├─ blender-4.5.0-trace-win64\
│  ├─ blender.exe
│  └─ blender_private.pdb
├─ llvm\
│  └─ bin\
│     ├─ llvm-cov.exe
│     └─ llvm-profdata.exe
└─ graphviz\
   └─ dot.exe
```

>源码、运行时、LLVM、Graphviz 必须全部放在同一个根目录（示例中的 `D:\blender-src`）里面，不能分散到不同盘符或不同父目录。根目录叫什么、放在哪个盘都可以。

详细说明见 `CovTrace\docs\架构.md`。
