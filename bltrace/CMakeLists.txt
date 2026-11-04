# SPDX-FileCopyrightText: 2026 Blender Authors
#
# SPDX-License-Identifier: GPL-2.0-or-later

set(BLTRACE_SOURCES bltrace_hook.c)

if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  # clang -finstrument-functions calls these C entry points directly; no MASM.
  list(APPEND BLTRACE_SOURCES bltrace_clang_shim.c)
else()
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

  list(APPEND BLTRACE_SOURCES "${BLTRACE_ASM_OBJ}")
endif()

add_library(bltrace STATIC ${BLTRACE_SOURCES})

if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  # The hook must not instrument itself, nor pollute line coverage.
  target_compile_options(bltrace PRIVATE
    /clang:-fno-instrument-functions
    /clang:-fno-instrument-functions-after-inlining
  )
  if(WITH_COMPILER_CODE_COVERAGE)
    target_compile_options(bltrace PRIVATE
      -fno-profile-instr-generate
      -fno-coverage-mapping
    )
  endif()
endif()

if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  set_source_files_properties("${BLTRACE_ASM_OBJ}" PROPERTIES
    EXTERNAL_OBJECT TRUE
    GENERATED TRUE
  )
endif()
