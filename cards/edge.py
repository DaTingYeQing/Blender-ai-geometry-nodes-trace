# -*- coding: utf-8 -*-
"""edge card: functions.bin + edges.bin -> edge.json."""

from . import symbols
from .base import TranslationCard


class EdgeCard(TranslationCard):
    name = "edge"
    needs = ("raw:functions", "raw:edges")

    def build(self, ctx):
        obj = symbols.symbolize(
            ctx.raw("functions"), ctx.raw("edges"), ctx.blender,
            with_addresses=True)
        path = ctx.out("edge.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(symbols.dumps_export(obj))
        return {
            "name": self.name,
            "functions": len(obj["functions"]),
            "edges": len(obj.get("edges", [])),
            "output": "edge.json",
        }
