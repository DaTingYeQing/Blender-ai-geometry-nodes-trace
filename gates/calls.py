# -*- coding: utf-8 -*-
"""calls gate: function table, call edges and return edges."""

import ctypes
import json

from .base import Gate, get_proc


def _fn(name, restype, argtypes=()):
    return ctypes.CFUNCTYPE(restype, *argtypes)(get_proc(name))


class CallsGate(Gate):
    name = "calls"
    exports = (
        "covtrace_calls_arm",
        "covtrace_calls_reset",
        "covtrace_calls_disarm",
        "covtrace_calls_dump",
        "covtrace_calls_dump_edges",
        "covtrace_calls_dump_returns",
        "covtrace_calls_dump_timings",
        "covtrace_calls_edge_count",
        "covtrace_calls_return_count",
        "covtrace_calls_timing_count",
    )

    def arm(self, ctx):
        arm = _fn("covtrace_calls_arm", ctypes.c_int)
        reset = _fn("covtrace_calls_reset", None)
        if not arm():
            raise RuntimeError("covtrace_calls_arm failed")
        reset()

    def dump(self, ctx):
        disarm = _fn("covtrace_calls_disarm", ctypes.c_int)
        disarm()
        dump = _fn("covtrace_calls_dump", None, (ctypes.c_char_p,))
        dump_edges = _fn("covtrace_calls_dump_edges", None, (ctypes.c_char_p,))
        dump_returns = _fn("covtrace_calls_dump_returns", None, (ctypes.c_char_p,))
        dump_timings = _fn("covtrace_calls_dump_timings", None, (ctypes.c_char_p,))
        edge_count = _fn("covtrace_calls_edge_count", ctypes.c_uint32)
        return_count = _fn("covtrace_calls_return_count", ctypes.c_uint32)
        timing_count = _fn("covtrace_calls_timing_count", ctypes.c_uint32)

        outputs = {
            "functions": ("functions.bin", dump),
            "edges": ("edges.bin", dump_edges),
            "returns": ("returns.bin", dump_returns),
            "timings": ("timings.bin", dump_timings),
        }
        raw = {}
        for key, (filename, write) in outputs.items():
            path = ctx.path(filename)
            write(path.encode("ascii"))
            raw[key] = path

        summary = {
            "name": self.name,
            "edge_count": int(edge_count()),
            "return_count": int(return_count()),
            "timing_count": int(timing_count()),
            "raw": raw,
        }
        with open(ctx.path("calls.json"), "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        return summary
