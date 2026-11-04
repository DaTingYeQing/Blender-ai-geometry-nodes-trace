# -*- coding: utf-8 -*-
"""only_call card: edge.json -> only_call.json.

Flattens functions observed to call exactly one distinct callee (out-degree 1).
This is a dynamic observation for the current run, not a static call graph.
"""

import json
from collections import defaultdict

from .base import TranslationCard


class OnlyCallCard(TranslationCard):
    name = "only_call"
    needs = ("edge.json",)

    def build(self, ctx):
        with open(ctx.out("edge.json"), encoding="utf-8") as fh:
            edge = json.load(fh)

        funcs = edge.get("functions", [])
        files = edge.get("files", [])
        out_degree = defaultdict(int)
        for edge_row in edge.get("edges", []):
            caller = edge_row.get("caller")
            if isinstance(caller, int) and 0 <= caller < len(funcs):
                out_degree[caller] += 1

        functions = []
        for i, f in enumerate(funcs):
            if out_degree.get(i, 0) != 1:
                continue
            file_idx = f.get("file")
            path = ""
            if isinstance(file_idx, int) and 0 <= file_idx < len(files):
                path = files[file_idx]
            functions.append({
                "name": f.get("name", ""),
                "file": path,
                "line": f.get("line"),
            })

        report = {
            "meta": {
                "criterion": "observed_out_degree == 1",
                "count": len(functions),
                "edge_json": "edge.json",
            },
            "functions": functions,
        }

        path = ctx.out("only_call.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
            fh.write("\n")

        return {
            "name": self.name,
            "functions": len(functions),
            "output": "only_call.json",
        }
