# -*- coding: utf-8 -*-
"""return card: edge.json + returns.bin -> return.json.

Returns are matched by RVA, so distinct functions that share the same
name/file/line are not collapsed.
"""

import json
import os
import time
from collections import defaultdict

from . import symbols
from .base import TranslationCard


class ReturnsCard(TranslationCard):
    name = "return"
    needs = ("edge.json", "raw:returns")

    def build(self, ctx):
        with open(ctx.out("edge.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        funcs = data.get("functions", [])
        files = data.get("files", [])

        def func_path(f):
            i = f.get("file")
            if isinstance(i, int) and 0 <= i < len(files):
                return files[i]
            return ""

        rva_to_idx = {}
        for i, f in enumerate(funcs):
            rva = f.get("rva")
            if rva is not None:
                rva_to_idx[rva] = i

        returns_bin = ctx.raw("returns")
        pairs = set()
        unresolved = []
        for key in symbols.read_u64s(returns_bin):
            callee_rva = key >> 32
            caller_rva = key & 0xFFFFFFFF
            callee = rva_to_idx.get(callee_rva)
            caller = rva_to_idx.get(caller_rva)
            if callee is None or caller is None:
                unresolved.append((callee_rva, caller_rva))
                continue
            pairs.add((callee, caller))

        call_edges = {(e.get("caller"), e.get("callee")) for e in data.get("edges", [])}
        matched = {(callee, caller) for callee, caller in pairs
                   if (caller, callee) in call_edges}
        call_no_return = call_edges - {(caller, callee) for callee, caller in matched}
        return_no_call = pairs - matched

        returns_to = defaultdict(set)
        for callee, caller in pairs:
            returns_to[callee].add(caller)

        def ref(i):
            f = funcs[i]
            row = {"rva": f.get("rva"), "name": f.get("name", "")}
            path = func_path(f)
            if path:
                row["file"] = path
            row["line"] = f.get("line")
            return row

        report = {
            "meta": {
                "edge_json": "edge.json",
                "returns_bin": os.path.basename(returns_bin),
                "exe": os.path.abspath(ctx.blender).replace("\\", "/"),
                "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "identity": "rva",
                "functions": len(funcs),
                "functions_with_return": len(returns_to),
                "return_edges": len(pairs),
                "return_edges_unmatched": len(unresolved),
                "call_edges": len(call_edges),
                "call_return_matched": len(matched),
                "call_without_return": len(call_no_return),
                "return_without_call": len(return_no_call),
            },
            "functions": [
                {
                    "rva": f.get("rva"),
                    "name": f.get("name", ""),
                    "file": func_path(f),
                    "line": f.get("line"),
                    "module": f.get("module", ""),
                    "returns_to": [
                        ref(c) for c in sorted(
                            returns_to.get(i, ()),
                            key=lambda c: (funcs[c].get("name", ""),
                                           func_path(funcs[c]),
                                           funcs[c].get("line") or 0))
                    ],
                }
                for i, f in enumerate(funcs)
            ],
        }

        path = ctx.publish("return.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
            fh.write("\n")

        return {
            "name": self.name,
            "functions": len(funcs),
            "functions_with_return": len(returns_to),
            "return_edges": len(pairs),
            "unmatched": len(unresolved),
            "output": "return.json",
            "public": ctx.test,
        }
