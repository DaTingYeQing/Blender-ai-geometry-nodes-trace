# -*- coding: utf-8 -*-
"""All project directories and fixed tool paths."""

import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))


def _source_root():
    env = os.environ.get("COVTRACE_SOURCE_DIR")
    if env:
        return os.path.normpath(env)
    path = ROOT
    for _ in range(4):
        path = os.path.dirname(path)
        if os.path.isfile(os.path.join(path, "CMakeLists.txt")) and all(
                os.path.isdir(os.path.join(path, name)) for name in ("source", "intern")):
            return path
    return os.path.normpath(os.path.join(ROOT, "..", ".."))


def _blender_bin(source):
    env = os.environ.get("COVTRACE_BLENDER_BIN_DIR")
    if env:
        return os.path.normpath(env)

    parent = os.path.dirname(source)
    direct = [source, parent]
    nested = []
    for base in (source, parent):
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for name in names:
            if "blender" not in name.lower() and "build" not in name.lower():
                continue
            path = os.path.join(base, name)
            if os.path.isdir(path):
                nested.extend((path, os.path.join(path, "bin")))
    for path in direct + nested:
        if os.path.isfile(os.path.join(path, "blender.exe")):
            return os.path.normpath(path)
    return source


def _tool_bin(env_name, exe_name, folder, legacy):
    env = os.environ.get(env_name)
    if env:
        return os.path.normpath(env)

    for base in (os.path.dirname(SOURCE_DIR), SOURCE_DIR):
        root = os.path.join(base, folder)
        for path in (os.path.join(root, "bin"), root):
            if os.path.isfile(os.path.join(path, exe_name)):
                return os.path.normpath(path)

    found = shutil.which(exe_name)
    if found:
        return os.path.normpath(os.path.dirname(found))
    return legacy


SOURCE_DIR = _source_root()
BLENDER_BIN_DIR = _blender_bin(SOURCE_DIR)

# Root recorded in the PDB and coverage data (build machine path).
# Keep this matching the PDB; override only for a build compiled with path remapping.
PDB_SOURCE_DIR = os.environ.get("COVTRACE_PDB_SOURCE_DIR", r"D:\blender-src\blender-4.5.0")

LLVM_BIN_DIR = _tool_bin(
    "COVTRACE_LLVM_BIN_DIR", "llvm-cov.exe", "llvm", r"D:\blender-src\llvm\bin")
GRAPHVIZ_BIN_DIR = _tool_bin(
    "COVTRACE_GRAPHVIZ_BIN_DIR", "dot.exe", "graphviz", r"D:\blender-src\graphviz")

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
