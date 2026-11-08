# covtrace-kit

Collects function calls, call edges, timings, and line coverage from an instrumented Blender build, then translates them into readable JSON and graph artifacts.


This is an extension of the https://github.com/DaTingYeQing/Blender-ai-geometry-nodes project. This Blender build cannot be used standalone as software.

## Layout

```text
covtrace-kit\
├─ CovTrace\                Tool source
│  ├─ engine.py             Host entry (run / validate / translate)
│  ├─ bootstrap.py          Blender-side entry
│  ├─ directories.py        Path auto-detection and environment overrides
│  ├─ registry.py           Gate and translation-card registry
│  ├─ infra\                Paths, run key, TARGET parsing, subprocess, manifest
│  ├─ gates\                Data collection gates (calls, coverage)
│  ├─ cards\                Translation cards (edge, disasm, timing, coverage, metrics, ...)
│  ├─ frag\                 Blender-side fragments and validation script
│  ├─ tools\                dot graph and SVG viewer tools
│  └─ docs\                 Architecture, card, log, and filtering notes
├─ changes\                 Reference copies of the 10 modified Blender source files
└─ docs\                    Generated repository documentation (repowiki / repowiki2)
```

## Runtime layout

```text
blender-src\
├─ blender-4.5.0\              Source tree, with covtrace-kit inside
├─ blender-4.5.0-trace-win64\  Extracted runtime, blender.exe + blender_private.pdb
├─ llvm\                       LLVM 23.1.3, llvm\bin\llvm-cov.exe
└─ graphviz\                   Optional, graphviz\bin\dot.exe
```

## Runtime layout notes

- **Source**: `blender-4.5.0\` is the Blender source root, with `covtrace-kit\` inside it. The drive and parent directory names are unrestricted.
- **Runtime**: the extracted release folder `blender-4.5.0-trace-win64\`. `blender.exe` and `blender_private.pdb` must stay in the same directory, and the PDB must keep its name.
- **LLVM**: version 23.1.3 exactly. Arrange it as `llvm\bin\llvm-cov.exe` without an extra `clang+llvm-xxx` directory level.
- **Graphviz**: optional; needed only for dot/SVG output. Place `dot.exe` under `graphviz\`.
- **Location**: the tool finds everything automatically from the relative layout above. If an item lives elsewhere or uses a different folder name, set the matching `COVTRACE_*` environment variable.

### Example

If the common root is `D:\blender-src`, arrange the components as follows:

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

> the source tree, runtime, LLVM, and Graphviz must all be placed inside the same root directory (the `D:\blender-src` folder in this example). Do not spread them across different drives or parent directories. The root directory can have any name and live on any drive.

See `CovTrace\docs\架构.md` for details.
