# -*- coding: utf-8 -*-
"""diff card: current (after) run minus a previous run's raw.

`options["diff_against"]` may point at a cache dir (functions.bin/edges.bin)
or an out dir (edge.json). The card runs last.
"""

import json
import os
import time

from . import symbols
from .base import TranslationCard
from infra import target as targetfile


def _load_edge(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _load_run(path, blender, edge_product):
    path = os.path.abspath(path)
    edge = os.path.join(path, edge_product)
    if os.path.isfile(edge):
        return _load_edge(edge)
    funcs = os.path.join(path, "functions.bin")
    edges = os.path.join(path, "edges.bin")
    if os.path.isfile(funcs) and os.path.isfile(edges):
        return symbols.symbolize(funcs, edges, blender, with_addresses=True)
    raise RuntimeError(
        "diff_against 里没有 edge.json 或 functions.bin/edges.bin: %s" % path)


def _sets(data):
    by_rva = {}
    for row in data.get("functions") or []:
        rva = row.get("rva")
        if rva is not None:
            by_rva[rva] = row
    edges = set()
    for row in data.get("edges") or []:
        caller = row.get("caller_rva")
        callee = row.get("callee_rva")
        if caller is not None and callee is not None:
            edges.add((caller, callee))
    return by_rva, edges


def _name(table, rva):
    row = table.get(rva)
    return row.get("name") if row else "0x%x" % rva


def _function_rows(keys, table):
    return [table[key] for key in sorted(keys) if key in table]


def _edge_rows(edges, table):
    pairs = sorted({(_name(table, a), _name(table, b)) for a, b in edges})
    return [{"caller": a, "callee": b} for a, b in pairs]


class DiffCard(TranslationCard):
    name = "diff"
    needs = ("raw:functions", "raw:edges")

    def build(self, ctx):
        other = ctx.options.get("diff_against")
        if not other:
            return {"name": self.name, "skipped": True}

        after_path = ctx.out("edge")
        if os.path.isfile(after_path):
            after = _load_edge(after_path)
        else:
            after = symbols.symbolize(
                ctx.raw("functions"), ctx.raw("edges"), ctx.blender,
                with_addresses=True)
        before = _load_run(other, ctx.blender, ctx.product("edge").path)

        af, ae = _sets(after)
        bf, be = _sets(before)
        added_f = set(af) - set(bf)
        removed_f = set(bf) - set(af)
        added_e = ae - be
        removed_e = be - ae

        measure = ""
        eval_path = (ctx.manifest or {}).get("eval") or ""
        if eval_path:
            try:
                measure = targetfile.measure_node(eval_path)
            except Exception:
                measure = ""
        measure = measure or ctx.options.get("measure_node") or ""

        hash8 = (ctx.manifest or {}).get("hash8") or ""
        cache_root = os.path.dirname(ctx.work_dir)
        after_dir = os.path.join(cache_root, hash8) if hash8 else ctx.work_dir

        report = {
            "meta": {
                "measure_node": measure,
                "phase": ctx.options.get("phase") or "",
                "before": os.path.abspath(other).replace("\\", "/"),
                "after": os.path.abspath(after_dir).replace("\\", "/"),
                "before_functions": len(bf),
                "before_edges": len(be),
                "after_functions": len(af),
                "after_edges": len(ae),
                "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "added": {
                "functions": _function_rows(added_f, af),
                "edges": _edge_rows(added_e, af),
                "function_count": len(added_f),
                "edge_count_raw": len(added_e),
                "edge_count_dedup": len(_edge_rows(added_e, af)),
            },
            "removed": {
                "functions": _function_rows(removed_f, bf),
                "edges": _edge_rows(removed_e, bf),
                "function_count": len(removed_f),
                "edge_count_raw": len(removed_e),
                "edge_count_dedup": len(_edge_rows(removed_e, bf)),
            },
        }

        path = ctx.out("diff")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
            fh.write("\n")

        return {
            "name": self.name,
            "added_functions": report["added"]["function_count"],
            "removed_functions": report["removed"]["function_count"],
            "added_edges_raw": report["added"]["edge_count_raw"],
            "added_edges_dedup": report["added"]["edge_count_dedup"],
        }
