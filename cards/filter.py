# -*- coding: utf-8 -*-
"""filter card: functions.jsonl -> filter.json.

Placeholder: keep every function entry. The output is an rva decision list so
downstream tools can filter functions.jsonl without touching edge.json.
"""

import json
import time

from .base import TranslationCard


def _read_rows(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "rva" in row:
                rows.append(row)
    return rows


class FilterCard(TranslationCard):
    name = "filter"
    needs = ("functions.jsonl",)

    def build(self, ctx):
        rows = _read_rows(ctx.out("functions.jsonl"))
        kept = [row["rva"] for row in rows]
        dropped = []

        report = {
            "meta": {
                "identity": "rva",
                "criterion": "placeholder: keep all",
                "functions": len(rows),
                "kept": len(kept),
                "dropped": len(dropped),
                "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "kept": kept,
            "dropped": dropped,
        }

        path = ctx.out("filter.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
            fh.write("\n")

        return {
            "name": self.name,
            "functions": len(rows),
            "kept": len(kept),
            "dropped": len(dropped),
            "output": "filter.json",
        }
