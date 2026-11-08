# -*- coding: utf-8 -*-
"""timing card: timings.bin -> timing.json.

The hook records three totals per function: call count, self time and
inclusive time (QPC ticks). This card resolves the RVAs and exposes both
raw totals in nanoseconds and their per-call averages.
"""

import json
import os
import struct
import time

from . import symbols
from .base import TranslationCard

HEADER = struct.Struct("<IIQII")
RECORD = struct.Struct("<QQQQ")
MAGIC = 0x4D495442  # 'BTIM'
VERSION = 1


def _ns(ticks, freq):
    if not freq:
        return 0.0
    return ticks * 1_000_000_000.0 / freq


class TimingCard(TranslationCard):
    name = "timing"
    needs = ()

    def build(self, ctx):
        raw_path = ctx.raw_paths.get("timings")
        if not raw_path or not os.path.isfile(raw_path):
            return {"name": self.name, "skipped": "timings.bin missing"}
        raw = open(raw_path, "rb").read()
        if len(raw) < HEADER.size:
            raise RuntimeError("timings.bin header is truncated")
        magic, version, freq, record_size, count = HEADER.unpack_from(raw, 0)
        if magic != MAGIC:
            raise RuntimeError("timings.bin magic mismatch: 0x%08X" % magic)
        if version != VERSION:
            raise RuntimeError("timings.bin version %d is not supported" % version)
        if record_size != RECORD.size:
            raise RuntimeError(
                "timings.bin record size %d != %d" % (record_size, RECORD.size))

        offset = HEADER.size
        records = []
        for _ in range(count):
            if offset + RECORD.size > len(raw):
                break
            key, calls, self_ticks, inclusive_ticks = RECORD.unpack_from(raw, offset)
            offset += RECORD.size
            if key and calls:
                records.append((key, calls, self_ticks, inclusive_ticks))

        symbols.load(ctx.blender)
        functions = []
        for key, calls, self_ticks, inclusive_ticks in records:
            rva = key - 1
            name, path, line = symbols.resolve(rva)
            if not name:
                continue
            total_self = _ns(self_ticks, freq)
            total_inclusive = _ns(inclusive_ticks, freq)
            functions.append({
                "rva": rva,
                "name": name,
                "file": symbols.norm_path(path),
                "line": line,
                "module": symbols.module_of(path),
                "count": calls,
                "total_self_ns": round(total_self, 3),
                "total_inclusive_ns": round(total_inclusive, 3),
                "mean_self_ns": round(total_self / calls, 3),
                "mean_inclusive_ns": round(total_inclusive / calls, 3),
                "self_share": round(
                    self_ticks / inclusive_ticks, 6) if inclusive_ticks else 0.0,
            })

        functions.sort(key=lambda item: (item["mean_self_ns"], item["name"]))
        report = {
            "meta": {
                "blender": ctx.blender.replace("\\", "/"),
                "timings_bin": "timings.bin",
                "qpc_freq": freq,
                "records": len(records),
                "functions": len(functions),
                "total_calls": sum(item["count"] for item in functions),
                "sorted_by": "mean_self_ns",
                "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "functions": functions,
        }

        path = ctx.publish("timing")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
            fh.write("\n")

        return {
            "name": self.name,
            "records": len(records),
            "functions": len(functions),
            "total_calls": report["meta"]["total_calls"],
        }
