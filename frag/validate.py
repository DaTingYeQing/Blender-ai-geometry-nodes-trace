# -*- coding: utf-8 -*-
"""Blender-side validation entry: open the blend, reject zones, resolve the node."""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import bpy

from frag import targeting
from infra import target as targetfile


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", required=True)
    ap.add_argument("--measure-node", default="")
    return ap.parse_args(argv)


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    args = parse_args()
    target = targetfile.load(args.eval)
    targetfile.validate(target)
    spec = args.measure_node or targetfile.measure_node(args.eval)
    if not spec:
        raise RuntimeError("eval 里没有 NODE，且没有 --measure-node")

    bpy.ops.wm.open_mainfile(filepath=target["blend"])
    obj = bpy.data.objects.get(target["object"])
    if obj is None:
        raise RuntimeError("object not found: %r" % target["object"])
    mod = obj.modifiers.get(target["modifier"])
    if mod is None or mod.type != "NODES" or mod.node_group is None:
        raise RuntimeError("modifier is not geometry nodes: %r" % target["modifier"])

    tree = mod.node_group
    targeting.validate_zones(tree)
    measure = targeting.resolve(tree, spec)
    print(">> validation: " + json.dumps(
        {"ok": True, "measure": measure.describe()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    code = 0
    try:
        code = main()
    except Exception as exc:
        print(">> validation: " + json.dumps(
            {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)},
            ensure_ascii=False))
        code = 1
    sys.exit(code)
