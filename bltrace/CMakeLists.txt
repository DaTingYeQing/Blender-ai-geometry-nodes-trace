# SPDX-FileCopyrightText: 2026 Blender Authors
#
# SPDX-License-Identifier: GPL-2.0-or-later

add_library(bltrace STATIC
  bltrace_hook.c
  bltrace_penter.asm
)

set_source_files_properties(bltrace_penter.asm PROPERTIES LANGUAGE ASM_MASM)