# -*- coding: utf-8 -*-
"""metrics card: disasm.json + timing.json + edges.bin -> functions.jsonl.

Rows are keyed by function entry RVA. Name/file/line is not unique (the same
source line can hold several template/lambda instances), so it is not used as
the join key. Timing keeps only count and the per-call averages; out-degree is
the number of distinct callees observed in edges.bin. Derived columns are not
stored; meta.derived_removed lists their formulas.
"""

import json
import os
import time
from collections import defaultdict

from . import symbols
from .base import TranslationCard

DISASM_FIELDS = (
    "size", "instructions", "decoded_bytes",
    "padding_bytes",
    "direct_calls", "indirect_calls", "hook_enter", "hook_exit",
    "runtime_calls", "distinct_call_targets",
    "jumps", "conditional_jumps", "basic_blocks", "back_edges", "switch_tables",
    "rets", "stack_frame_bytes", "push_count",
    "rip_relative_refs", "global_refs", "fp_simd_insns", "lock_insns",
    "first", "first_after_hook", "last", "tail_target_kind",
)

TIMING_FIELDS = ("count", "mean_self_ns", "mean_inclusive_ns", "self_share")

FIELDS = ("rva", "name", "file", "line", "module") + TIMING_FIELDS + (
    "out_degree",
) + DISASM_FIELDS


def _out_degrees(path):
    degrees = defaultdict(set)
    for key in symbols.read_u64s(path):
        caller = key >> 32
        callee = key & 0xFFFFFFFF
        if caller:
            degrees[caller].add(callee)
    return degrees


class MetricsCard(TranslationCard):
    name = "metrics"
    needs = ("disasm.json", "raw:edges")

    def build(self, ctx):
        with open(ctx.out("disasm.json"), encoding="utf-8") as fh:
            disasm = json.load(fh)

        timing_path = ctx.out("timing.json")
        timing = {}
        if os.path.isfile(timing_path):
            with open(timing_path, encoding="utf-8") as fh:
                for row in json.load(fh).get("functions", []):
                    if row.get("rva") is not None:
                        timing[row["rva"]] = row

        degrees = _out_degrees(ctx.raw("edges"))
        disasm_rvas = {
            item["rva"] for item in disasm.get("functions", [])
            if item.get("rva") is not None
        }

        rows = []
        seen = set()
        duplicates = 0
        for item in disasm.get("functions", []):
            rva = item.get("rva")
            if rva is None:
                continue
            if rva in seen:
                duplicates += 1
                continue
            seen.add(rva)

            disasm_row = item["disasm"]
            hook = disasm_row["hook_balance"]
            timing_row = timing.get(rva, {})
            out_degree = len(degrees.get(rva, ()))

            row = {
                "rva": rva,
                "name": item["name"],
                "file": item["file"],
                "line": item["line"],
                "module": item["module"],
            }
            for field in TIMING_FIELDS:
                row[field] = timing_row.get(field)
            row["out_degree"] = out_degree
            for field in DISASM_FIELDS:
                if field == "hook_enter":
                    row[field] = hook["enter"]
                elif field == "hook_exit":
                    row[field] = hook["exit"]
                else:
                    row[field] = disasm_row[field]
            rows.append(row)

        rows.sort(key=lambda row: row["rva"])
        meta = {
            "blender": disasm.get("meta", {}).get("blender"),
            "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "functions": len(rows),
            "timing_matched": sum(1 for row in rows if row["count"] is not None),
            "duplicate_rvas": duplicates,
            "edge_callers_not_in_disasm": len(set(degrees) - disasm_rvas),
            "identity": "one row per function entry rva",
            "out_degree": "distinct callees from edges.bin",
            "derived_removed": {
                "calls": "direct_calls + indirect_calls",
                "hook_calls": "hook_enter + hook_exit",
                "real_calls": (
                    "direct_calls + indirect_calls - hook_enter - hook_exit"),
                "logic_calls": "real_calls - runtime_calls",
                "only_call": "out_degree == 1",
                "branchless": "conditional_jumps == 0",
                "tiny": "0 < size <= 128",
                "forwarder_candidate": (
                    "tiny and branchless and real_calls == 1 and rets >= 1"),
                "tail_thunk": "tail_target_kind == 'direct_external'",
                "decode_error": "decoded_bytes < size",
                "trailing_pad": "padding_bytes > 0",
                "hook_balanced": (
                    "hook_enter == hook_exit and hook_enter > 0"),
            },
            "derived_kept": {
                "self_share": "mean_self_ns / mean_inclusive_ns",
            },
            "fields": list(FIELDS),
        }

        path = ctx.out("functions.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"_meta": meta}, ensure_ascii=False,
                                separators=(",", ":")))
            fh.write("\n")
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False,
                                    separators=(",", ":")))
                fh.write("\n")

        return {
            "name": self.name,
            "functions": len(rows),
            "timing_matched": meta["timing_matched"],
            "duplicate_rvas": duplicates,
            "output": "functions.jsonl",
        }
