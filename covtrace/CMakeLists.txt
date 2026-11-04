# SPDX-FileCopyrightText: 2026 Blender Authors
#
# SPDX-License-Identifier: GPL-2.0-or-later

# Coverage window control: exports covtrace_arm / covtrace_dump.
add_library(covtrace_obj OBJECT covtrace_hook.c)

# The hook must not count itself, otherwise resetting counters re-pollutes them.
target_compile_options(covtrace_obj PRIVATE
  -fno-profile-instr-generate
  -fno-coverage-mapping
  /clang:-fno-instrument-functions
  /clang:-fno-instrument-functions-after-inlining
)
