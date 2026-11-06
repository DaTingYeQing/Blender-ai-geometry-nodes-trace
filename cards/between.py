# -*- coding: utf-8 -*-
"""between card: edge.json + return.json + node -> between.json.

Graph traversal is keyed by RVA. Names are kept for display only, because
distinct functions can share the same name/file/line.
"""

import json
import os
from collections import defaultdict, deque

from .base import TranslationCard


def _resolve_node(names, node):
    names = set(names)
    if node in names:
        return node
    candidates = sorted(n for n in names if node in n)
    execs = [n for n in candidates if n.endswith("::node_geo_exec")]
    if len(execs) == 1:
        return execs[0]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise RuntimeError("node %r not found" % node)
    if len(execs) > 1:
        raise RuntimeError(
            "node %r matches multiple node_geo_exec: %s" % (node, execs))
    raise RuntimeError(
        "node %r matches multiple functions: %s" % (node, candidates))


def _direct_returners(functions, targets):
    return {
        f.get("rva")
        for f in functions
        if f.get("rva") is not None
        and any(ref.get("rva") in targets for ref in f.get("returns_to", []))
    }


def _closure(seeds, graph):
    seen = set(seeds)
    queue = deque(seeds)
    while queue:
        node = queue.popleft()
        for nxt in graph.get(node, ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


class BetweenCard(TranslationCard):
    name = "between"
    needs = ("edge.json", "return.json")

    def build(self, ctx):
        edge_path = ctx.out("edge.json")
        return_path = ctx.input("return.json")
        with open(edge_path, encoding="utf-8") as fh:
            edge = json.load(fh)
        with open(return_path, encoding="utf-8") as fh:
            returns = json.load(fh)

        files = edge.get("files", [])
        funcs = edge.get("functions", [])
        names = [f.get("name", "") for f in funcs]
        rvas = [f.get("rva") for f in funcs]

        def func_path(f):
            i = f.get("file")
            if isinstance(i, int) and 0 <= i < len(files):
                return files[i]
            return ""

        by_rva = {}
        for f in funcs:
            rva = f.get("rva")
            if rva is not None:
                by_rva[rva] = f

        def node_ref(rva):
            f = by_rva[rva]
            return {
                "rva": rva,
                "name": f.get("name", ""),
                "file": func_path(f),
                "line": f.get("line"),
            }

        resolved = _resolve_node(names, ctx.node)
        node_indices = [i for i, name in enumerate(names) if name == resolved]
        if len(node_indices) != 1:
            raise RuntimeError(
                "node %r matches %d rva records" % (resolved, len(node_indices)))
        node_rva = rvas[node_indices[0]]
        if node_rva is None:
            raise RuntimeError("node %r has no rva" % resolved)

        start = _direct_returners(returns.get("functions", []), {node_rva})
        final = _direct_returners(returns.get("functions", []), start)

        missing = sorted(rva for rva in (start | final) if rva not in by_rva)
        if missing:
            raise RuntimeError(
                "start/finally missing from edge.json: %s" % missing)

        callees = defaultdict(set)
        callers = defaultdict(set)
        for rva in by_rva:
            callees[rva]
            callers[rva]
        for edge_row in edge.get("edges", []):
            caller_idx = edge_row.get("caller")
            callee_idx = edge_row.get("callee")
            if not (isinstance(caller_idx, int) and isinstance(callee_idx, int)):
                continue
            if not (0 <= caller_idx < len(funcs) and 0 <= callee_idx < len(funcs)):
                continue
            caller_rva = rvas[caller_idx]
            callee_rva = rvas[callee_idx]
            if caller_rva is None or callee_rva is None:
                continue
            callees[caller_rva].add(callee_rva)
            callers[callee_rva].add(caller_rva)

        down = _closure(start, callees)
        up = _closure(final, callers)
        keep = sorted(down & up)

        between = [node_ref(rva) for rva in keep if rva in by_rva]
        between.sort(key=lambda item: (item["name"], item["file"],
                                       item["line"] or 0))

        def sort_refs(rva_set):
            return sorted(
                (node_ref(rva) for rva in rva_set if rva in by_rva),
                key=lambda item: (item["name"], item["file"],
                                  item["line"] or 0))

        boundary = {
            "meta": {
                "node": ctx.node,
                "node_resolved": resolved,
                "identity": "rva",
                "start": len(start),
                "finally": len(final),
                "edge_json": "edge.json",
                "return_json": "return.json",
            },
            "start": sort_refs(start),
            "finally": sort_refs(final),
        }
        boundary_path = ctx.out("boundary.json")
        with open(boundary_path, "w", encoding="utf-8") as fh:
            json.dump(boundary, fh, ensure_ascii=False, indent=1)
            fh.write("\n")

        report = {
            "meta": {
                "node": ctx.node,
                "node_resolved": resolved,
                "identity": "rva",
                "start": len(start),
                "finally": len(final),
                "between": len(between),
                "call_edges": len(edge.get("edges", [])),
                "return_edges": returns.get("meta", {}).get("return_edges"),
                "return_edges_unmatched": returns.get("meta", {}).get(
                    "return_edges_unmatched"),
                "edge_json": "edge.json",
                "return_json": "return.json",
            },
            "between": between,
        }

        path = ctx.out("between.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
            fh.write("\n")

        return {
            "name": self.name,
            "node": ctx.node,
            "node_resolved": resolved,
            "start": len(start),
            "finally": len(final),
            "between": len(between),
            "boundary": "boundary.json",
            "output": "between.json",
            "extra_outputs": ["boundary.json"],
        }
