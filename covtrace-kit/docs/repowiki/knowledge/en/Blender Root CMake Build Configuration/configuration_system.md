## Overview

This repository is a CMake-based build configuration system for the Blender application. There is no runtime application configuration subsystem (no `.yaml`, `.toml`, `.env`, `application.properties`, or in-process config loader). All "configuration" here is **build-time configuration**: selecting which features, platforms, libraries, and output layout are compiled into Blender.

## Approach

- **Framework:** CMake ≥ 3.10 (`cmake_minimum_required(VERSION 3.10)` in root `CMakeLists.txt`).
- **Entry point:** `CMakeLists.txt` at the repository root bootstraps the build, validates the environment, sets policies, defines options, and includes modular sub-configurations under `build_files/cmake/Modules` and `build_files/cmake/platform` (added to `CMAKE_MODULE_PATH`).
- **Options model:** Feature flags are declared with `option(...)` and then gated by `if(WITH_*)` throughout the tree. Advanced/dangerous options are hidden from `ccmake`/`cmake-gui` via `mark_as_advanced()`.
- **Environment integration:** The build reads compiler/library discovery through CMake's built-in mechanisms (`find_package`, compiler version checks) and explicitly warns about relying on Python virtual environments' default interpreter (see comments around line 912–916 of the root `CMakeLists.txt`).
- **No runtime config files:** A search across all `.c`, `.cpp`, and YAML/TOML/ENV patterns returns zero matches; the only non-CMake file referencing environment variables is `source/creator/CMakeLists.txt` where `set_source_files_properties(... PROPERTIES SYMBOLIC TRUE)` appears — unrelated to application config.

## Key Files

- `CMakeLists.txt` (~2900 lines): root entry point — policy setup, option declarations, compiler/version validation, output paths, per-platform defaults.
- `source/creator/CMakeLists.txt`: builds the `blender` executable target, applies platform-specific properties (`MACOSX_BUNDLE`, `VS_GLOBAL_VcpkgEnabled`, `PDB_NAME`, `OUTPUT_NAME`), and wires generated `buildinfo.h`.
- `bltrace/CMakeLists.txt`, `covtrace/CMakeLists.txt`, `intern/CMakeLists.txt`, `source/CMakeLists.txt`: per-subsystem CMake fragments included by the root.
- `build_files/cmake/macros.cmake` (referenced via `include(build_files/cmake/macros.cmake)`): custom macros used throughout the build.
- `build_files/cmake/have_features.cmake` (included via `include(build_files/cmake/have_features.cmake)`): feature detection logic.

## Architecture and Conventions

1. **Out-of-source builds enforced.** The root `CMakeLists.txt` rejects in-source builds unless `WITH_IN_SOURCE_BUILD` is explicitly defined, printing an error that instructs users to create a separate build directory (e.g. `cmake-make`) and run `cmake ../blender`.

2. **Policy-driven compatibility.** Policies `CMP0003`, `CMP0005`, `CMP0010`, `CMP0014`, `CMP0068`, `CMP0074`, `CMP0087`, `CMP0119`, `CMP0144`, `CMP0177` are set to their NEW behavior, pinning CMake semantics across versions.

3. **Compiler-version gating.** GCC < 11.0.0, Clang < 8.0, MSVC < 1928 (Visual Studio 2019 16.9.16) cause `message(FATAL_ERROR ...)` and abort generation.

4. **Option taxonomy:**
   - `WITH_*` boolean toggles for every feature (Python, OpenVDB, Bullet, FFmpeg, Wayland, JACK, PulseAudio, PipeWire, WASAPI, etc.).
   - `WITH_SYSTEM_*` toggles switch between bundled and system-provided libraries (Bullet, Audaspace, Freetype, Eigen3, LZO, GFlags, GLog).
   - `_DYNLOAD` suffixes toggle runtime dynamic loading of optional libraries (Wayland, JACK, PulseAudio, PipeWire).
   - `CPACK_OVERRIDE_PACKAGENAME`, `BUILDINFO_OVERRIDE_DATE`, `BUILDINFO_OVERRIDE_TIME` are cache string overrides for reproducible packaging.

5. **Platform-specific defaults:**
   - macOS: `WITH_XR_OPENXR` defaults OFF; CoreAudio ON; app bundle uses `MACOSX_BUNDLE_INFO_PLIST`.
   - Windows: `WITH_WASAPI` ON; `VS_GLOBAL_VcpkgEnabled = false`; PDB name forced to `blender_private`.
   - Linux/X11/Wayland: X11 + Wayland both ON by default; Wayland can be split into LibDecor and dynload.
   - UNIX-only: `WITH_LIBS_PRECOMPILED` and `WITH_STATIC_LIBS` options.

6. **Dependency inter-option enforcement:**
   - `set_and_warn_dependency(WITH_AUDASPACE WITH_SYSTEM_AUDASPACE OFF)` enforces that system Audaspace cannot be combined with the bundled Audaspace.
   - `WITH_CPU_CHECK` is auto-enabled only for 64-bit Windows/macOS or UNIX builds when not building as a Python module.
   - `WITH_PYTHON_NUMPY` is auto-enabled when either `WITH_AUDASPACE` (non-system) or `WITH_MOD_FLUID` is on.

7. **Build info injection:** The creator target generates a `buildinfo.h` header containing version, date, and build-type constants, exposed to the application via compile-time defines such as `BLENDER_WIN_APPID` and `BLENDER_WIN_APPID_FRIENDLY_NAME` on Windows.

## Conventions and Constraints

- **Convention:** Every new feature flag is introduced as an `option(WITH_<NAME> ...)` near the top of the root `CMakeLists.txt`, followed by conditional compilation blocks elsewhere in the tree.
- **Convention:** Advanced or potentially unsafe options are immediately marked with `mark_as_advanced(<OPTION>)` so they are hidden from casual GUI use.
- **Convention:** Platform-specific option defaults are computed via `if(WIN32/APPLE/UNIX AND NOT APPLE/HAIKU)` blocks rather than separate files.
- **Constraint (enforced):** In-source CMake generation is rejected with `FATAL_ERROR` unless `WITH_IN_SOURCE_BUILD` is explicitly defined.
- **Constraint (enforced):** Minimum compiler versions (GCC 11, Clang 8, MSVC 1928) are validated at configure time and abort with `FATAL_ERROR` if unmet.
- **Constraint (enforced):** The build requires CMake ≥ 3.10 and refuses to proceed if `CMAKE_SOURCE_DIR == CMAKE_BINARY_DIR` without the override.
- **Constraint (documented):** Users should not rely on `find_package(Python3)` discovering a virtual environment's default interpreter; builders must set the Python path explicitly (comment at root `CMakeLists.txt` ~line 912–916).
- **Constraint (enforced):** `WITH_SYSTEM_AUDASPACE` cannot be combined with the bundled `WITH_AUDASPACE` (`set_and_warn_dependency` enforces this).
- **Convention:** Reproducible builds are supported via `BUILDINFO_OVERRIDE_DATE`, `BUILDINFO_OVERRIDE_TIME`, and `CPACK_OVERRIDE_PACKAGENAME` cache variables.