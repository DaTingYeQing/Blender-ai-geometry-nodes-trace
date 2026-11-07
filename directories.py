# -*- coding: utf-8 -*-
"""All project directories and fixed tool paths."""

import os

ROOT = os.path.dirname(os.path.abspath(__file__))

BLENDER_BIN_DIR = r"D:\blender-src\build_windows_x64_ClangCovTrace\bin"
LLVM_BIN_DIR = r"D:\tools\llvm\bin"
GRAPHVIZ_BIN_DIR = r"D:\qcachegrind074-x86"
SOURCE_DIR = r"D:\blender-src\blender-4.5.0"

OUT_DIR = os.path.join(ROOT, "out")
CACHE_DIR = os.path.join(ROOT, "cache")
FRAG_DIR = os.path.join(ROOT, "frag")
INTERNAL_DIR = "_internal"

BLENDER_EXE = os.path.join(BLENDER_BIN_DIR, "blender.exe")
LLVM_COV_EXE = os.path.join(LLVM_BIN_DIR, "llvm-cov.exe")
LLVM_PROFDATA_EXE = os.path.join(LLVM_BIN_DIR, "llvm-profdata.exe")
DOT_EXE = os.path.join(GRAPHVIZ_BIN_DIR, "dot.exe")

ENGINE_SCRIPT = os.path.join(ROOT, "engine.py")
BOOTSTRAP_SCRIPT = os.path.join(ROOT, "bootstrap.py")
VALIDATE_SCRIPT = os.path.join(FRAG_DIR, "validate.py")
