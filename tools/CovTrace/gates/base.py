# -*- coding: utf-8 -*-
"""Gate interface and shared helpers. Runs inside Blender."""

import ctypes
import os


def get_proc(name):
    k = ctypes.windll.kernel32
    k.GetModuleHandleA.restype = ctypes.c_void_p
    k.GetModuleHandleA.argtypes = [ctypes.c_char_p]
    k.GetProcAddress.restype = ctypes.c_void_p
    k.GetProcAddress.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    module = k.GetModuleHandleA(None)
    return k.GetProcAddress(module, name.encode("ascii"))


def missing_exports(gate):
    return [name for name in gate.exports if not get_proc(name)]


class GateContext:
    def __init__(self, work_dir):
        self.work_dir = work_dir

    def path(self, name):
        return os.path.join(self.work_dir, name)


class Gate:
    name = ""
    exports = ()

    def arm(self, ctx):
        raise NotImplementedError

    def dump(self, ctx):
        raise NotImplementedError
