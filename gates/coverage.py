# -*- coding: utf-8 -*-
"""coverage gate: line-coverage window via covtrace_arm/covtrace_dump."""

import ctypes
import json

from .base import Gate, get_proc


def _fn(name, restype, argtypes=()):
    return ctypes.CFUNCTYPE(restype, *argtypes)(get_proc(name))


class CoverageGate(Gate):
    name = "coverage"
    exports = ("covtrace_arm", "covtrace_dump")

    def arm(self, ctx):
        path = ctx.path("window.profraw")
        try:
            raw = path.encode("ascii")
        except UnicodeEncodeError:
            raise RuntimeError("coverage work path must be ASCII: %r" % path)
        arm = _fn("covtrace_arm", None, (ctypes.c_char_p,))
        arm(raw)

    def dump(self, ctx):
        dump = _fn("covtrace_dump", ctypes.c_int, (ctypes.c_char_p,))
        rc = int(dump(b"NUL"))
        if rc != 0:
            raise RuntimeError("covtrace_dump failed: %d" % rc)
        summary = {
            "name": self.name,
            "raw": {"coverage": ctx.path("window.profraw")},
        }
        with open(ctx.path("coverage_raw.json"), "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        return summary
