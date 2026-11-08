## Scope

This repository is the top-level CMake entry point for Blender's build system. The only error-handling surface here is at **build-time**, not runtime: it validates configuration, toolchain versions, feature flags, and dependency availability, then fails fast with `message(FATAL_ERROR ...)`. There is no application code in this snapshot — no sentinel errors, panic/recover, or middleware.

## Approach

1. **Fail-fast validation** — every invariant check (in-source builds disallowed, minimum CMake/MSVC/GCC versions, incompatible `WITH_*` option combinations, missing system-wide gflags/glog) uses `message(FATAL_ERROR ...)` to abort configuration immediately rather than continue with a broken setup.
2. **Compiler warnings promoted to errors** — the root `CMakeLists.txt` enables `-Werror`-style flags:
   - `C_WARN_ERROR_IMPLICIT_FUNCTION_DECLARATION -Werror=implicit-function-declaration`
   - `C_WARN_ERROR_RETURN_TYPE -Werror=return-type`
   - `C_WARN_ERROR_VLA -Werror=vla`
   - `CXX_WARN_ERROR_RETURN_TYPE -Werror=return-type`
   Several are explicitly toggled off where they are noisy (`-no-error=unused-but-set-variable`).
3. **Policy-driven error behavior** — policies like `CMP0010` (syntax problems are errors), `CMP0014` (input directories must have CMakeLists.txt), and `CMP0074` (`find_package()` uses `<PackageName>_ROOT`) are set to `NEW` to make CMake itself treat problematic constructs as hard failures.

## Key Files

- `CMakeLists.txt` — the single source of build-time error handling: early checks (lines ~13–80), policy enforcement (lines ~60–90), option consistency checks (e.g. `WITH_GHOST_SDL requires WITH_SDL`, `WITH_PYTHON_MODULE requires WITH_PYTHON_INSTALL` around lines 1318–1337), dependency existence checks (gflags/glog around lines 1739/1757), and compiler warning-to-error flag assembly (lines ~1912–1999).
- `source/CMakeLists.txt` and `source/creator/CMakeLists.txt` — referenced by grep but contain no additional error-handling patterns beyond standard CMake directives.

## Conventions Observed

- Configuration invariants use `message(FATAL_ERROR "...")` rather than `message(WARNING ...)` followed by a conditional disable; the comment at line 1313 states the intent explicitly: *"When requirements for a build option are not met, error instead of disabling the option."*
- In-source builds are rejected outright unless `WITH_IN_SOURCE_BUILD` is explicitly defined, reinforcing the out-of-source-build rule.
- Toolchain version requirements (CMake ≥ 3.10, MSVC ≥ 2019 16.9.16, GCC version checks) are enforced via `FATAL_ERROR` so that misconfigured environments fail before any compilation begins.
- Warning-to-error conversion is centralized in the root `CMakeLists.txt` via named cache variables (`C_WARN_ERROR_*`, `CXX_WARN_ERROR_*`) that expand to `-Werror=...` flags passed to the compilers.

## Rules Enforced by the Build System

- In-source generation is forbidden unless `WITH_IN_SOURCE_BUILD` is defined (enforced at `CMakeLists.txt` line 13).
- Syntax errors in CMake scripts are treated as fatal via `cmake_policy(CMP0010 NEW)` (line 67).
- Missing required dependencies (system-wide gflags, glog) abort configuration via `FATAL_ERROR` (lines 1739, 1757).
- Incompatible `WITH_*` option combinations abort configuration via `FATAL_ERROR` (lines 1332, 1337).
- Compiler warnings flagged by `-Werror=implicit-function-declaration`, `-Werror=return-type`, and `-Werror=vla` cause the build to fail (lines 1912–1918, 1980).

## What Is Not Present

There is no application-layer error type hierarchy, no sentinel/error-code constants, no `panic`/`recover` equivalents, and no middleware pipeline — those concepts do not apply to this CMake-only snapshot of the Blender repository.