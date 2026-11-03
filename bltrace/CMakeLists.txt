# SPDX-FileCopyrightText: 2026 Blender Authors
#
# SPDX-License-Identifier: GPL-2.0-or-later

# Compile the MASM hook with a custom command. MASM does not accept the
# globally added BLENDER_WIN_APPID definitions (quoted values containing a
# dot), and the hook does not need any of the global C/C++ definitions.
set(BLTRACE_ASM "${CMAKE_CURRENT_SOURCE_DIR}/bltrace_penter.asm")
set(BLTRACE_ASM_OBJ "${CMAKE_CURRENT_BINARY_DIR}/bltrace_penter.obj")

add_custom_command(
  OUTPUT "${BLTRACE_ASM_OBJ}"
  COMMAND "${CMAKE_ASM_MASM_COMPILER}" /nologo /c /Fo "${BLTRACE_ASM_OBJ}" "${BLTRACE_ASM}"
  DEPENDS "${BLTRACE_ASM}"
  COMMENT "Assembling bltrace_penter.asm"
  VERBATIM
)

add_library(bltrace STATIC
  bltrace_hook.c
  "${BLTRACE_ASM_OBJ}"
)

set_source_files_properties("${BLTRACE_ASM_OBJ}" PROPERTIES
  EXTERNAL_OBJECT TRUE
  GENERATED TRUE
)