# Build System: CMake

## Approach

Blender's build is driven entirely by **CMake** (minimum version 3.10). There are no Makefiles, `build*.sh` scripts, Dockerfiles, CI pipelines, or shell wrappers in this repository snapshot — only the CMake entry point and a few sub-CMakeLists.txt files.

The root `CMakeLists.txt` acts as the single bootstrap that:
- Enforces **out-of-source builds** (fails with `FATAL_ERROR` when `CMAKE_SOURCE_DIR == CMAKE_BINARY_DIR`, unless overridden by the `WITH_IN_SOURCE_BUILD` cache variable).
- Sets `cmake_minimum_required(VERSION 3.10)`.
- Extends `CMAKE_MODULE_PATH` to include `${CMAKE_SOURCE_DIR}/build_files/cmake/Modules` and `${CMAKE_SOURCE_DIR}/build_files/cmake/platform` — these two directories are expected to contain the rest of the build logic (`macros.cmake`, `have_features.cmake`, platform toolchain modules, etc.). They are not present in this snapshot but are referenced by the root config.
- Enables policies CMP0003, CMP0005, CMP0010, CMP0014, CMP0068, CMP0074, CMP0144, CMP0087, CMP0119, CMP0177 to pin modern CMake behavior across generator versions.
- Loads `build_files/cmake/macros.cmake` for shared macros before calling `project(Blender)`.
- Enables `enable_testing()` so CTest can drive unit tests from the generated build tree.

## Compiler & Feature Requirements

Compiler versions are validated at configure time and enforced via `message(FATAL_ERROR ...)`:
- GCC / Clang: minimum 11.0.0 (C) and 11.0.0 (C++); an additional Clang path checks ≥ 8.0 when `CMAKE_COMPILER_IS_GNUCC` is set alongside Clang.
- MSVC: minimum version 1928 (VS 2019 16.9.16), with a user-facing message naming "2019".

Feature detection is delegated to `include(build_files/cmake/have_features.cmake)`.

## Output Layout

Output directories are forced into the build tree:
- `EXECUTABLE_OUTPUT_PATH = ${CMAKE_BINARY_DIR}/bin`
- `LIBRARY_OUTPUT_PATH = ${CMAKE_BINARY_DIR}/lib`
- Test binaries go under `${EXECUTABLE_OUTPUT_PATH}/tests/` (or `tests/$<CONFIG>/` for multi-config generators).

## Versioning

Version is read via `get_blender_version()` (defined in `build_files/cmake/macros.cmake`) and exposed as `BLENDER_VERSION_MAJOR` / `BLENDER_VERSION_MINOR`. On Windows it also defines compile-time strings `BLENDER_WIN_APPID` and `BLENDER_WIN_APPID_FRIENDLY_NAME` used for file registration and taskbar/OpenWith UI.

## Subprojects

Three sibling CMake projects are included via their own `CMakeLists.txt`:
- `bltrace/` — LLVM/Clang instrumentation shim (C + assembly).
- `covtrace/` — coverage tracing hook.
- `intern/` — internal Blender library components.
- `source/creator/CMakeLists.txt` — the Blender application target.

Each has its own `CMakeLists.txt` but the snapshot does not show the module-level configuration; they are consumed through the top-level project hierarchy.

## Conventions Observed

- Out-of-source builds are mandatory (enforced by the root `CMakeLists.txt`).
- All compiler/library feature probing is centralized in `build_files/cmake/` (referenced but absent here).
- Generator expressions are used where needed (e.g., `$<CONFIG>` for test output paths).
- `CMAKE_OPTIMIZE_DEPENDENCIES` is turned on by default for CMake ≥ 3.19.
- No packaging, distribution, CI, or containerization targets exist in this snapshot.

## Key Files

- `CMakeLists.txt` — root bootstrap, policy setup, compiler/version checks, output layout, project definition.
- `bltrace/CMakeLists.txt` — instrumentation library target.
- `covtrace/CMakeLists.txt` — coverage tracing library target.
- `intern/CMakeLists.txt` — internal sources target.
- `source/CMakeLists.txt` — main source tree entry.
- `source/creator/CMakeLists.txt` — Blender executable target.