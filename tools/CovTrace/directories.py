# -*- coding: utf-8 -*-
"""All project directories and fixed tool paths."""

import os

ROOT = os.path.dirname(os.path.abspath(__file__))

BLENDER_BIN_DIR = r"D:\blender-src\build_windows_x64_ClangCovTrace\bin"
LLVM_BIN_DIR = r"D:\tools\llvm\bin"
GRAPHVIZ_BIN_DIR = r"D:\qcachegrind074-x86"

# Root recorded in the PDB and coverage data (build machine path).
# Only change this for a build compiled with path remapping.
PDB_SOURCE_DIR = os.environ.get("COVTRACE_PDB_SOURCE_DIR", r"D:\blender-src\blender-4.5.0")
# Actual source checkout on this machine. Defaults to the recorded root.
SOURCE_DIR = os.environ.get("COVTRACE_SOURCE_DIR", PDB_SOURCE_DIR)

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
