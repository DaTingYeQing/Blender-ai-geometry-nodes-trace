# -*- coding: utf-8 -*-
"""Blender-side base: open project, arm gates, run evaluate, dump raw."""

import argparse
import importlib
import json
import os
import runpy
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import bpy

from gates.base import GateContext, missing_exports
from infra import target as targetfile


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="bootstrap.py")
    ap.add_argument("--eval", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--node", required=True)
    ap.add_argument("--gates", default="")
    ap.add_argument("--blend", default="")
    ap.add_argument("--obj", default="")
    ap.add_argument("--mod", default="")
    ap.add_argument("--param", default="")
    return ap.parse_args(argv)


def write_status(work_dir, data):
    path = os.path.join(work_dir, "status.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    os.replace(tmp, path)


def load_gates(spec):
    gates = []
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        module_name, class_name = part.split(":", 1)
        module = importlib.import_module(module_name)
        gates.append(getattr(module, class_name)())
    return gates


def resolve_param(node_group, display):
    names = []
    for item in node_group.interface.items_tree:
        if getattr(item, "item_type", "") != "SOCKET":
            continue
        if getattr(item, "in_out", "") != "INPUT":
            continue
        names.append(item.name)
        if item.name == display:
            return item.identifier
    raise RuntimeError("param %r not in sockets %s" % (display, names))


class Context:
    pass


def main():
    args = parse_args()
    os.makedirs(args.work, exist_ok=True)
    try:
        target = targetfile.load(args.eval)
        target = targetfile.merge(target, args.blend, args.obj, args.mod, args.param)
        targetfile.validate(target)

        bpy.ops.wm.open_mainfile(filepath=target["blend"])

        obj = bpy.data.objects.get(target["object"])
        if obj is None:
            raise RuntimeError(
                "object not found: %r; available: %s"
                % (target["object"], [o.name for o in bpy.data.objects]))
        mod = obj.modifiers.get(target["modifier"])
        if mod is None:
            raise RuntimeError(
                "modifier not found: %r on %r; available: %s"
                % (target["modifier"], obj.name,
                   [(m.name, m.type) for m in obj.modifiers]))
        if mod.type != "NODES" or mod.node_group is None:
            raise RuntimeError("modifier %r is not a geometry nodes modifier" % mod.name)
        if target.get("node_tree") and mod.node_group.name != target["node_tree"]:
            raise RuntimeError(
                "node tree mismatch: modifier has %r, TARGET says %r"
                % (mod.node_group.name, target["node_tree"]))
        param_id = resolve_param(mod.node_group, target["param"])

        ns = runpy.run_path(args.eval, run_name="__covtrace_eval__")
        evaluate = ns.get("evaluate")
        if not callable(evaluate):
            raise RuntimeError("eval script must define evaluate(ctx)")
        evaluate.__globals__.setdefault("bpy", bpy)
        evaluate.__globals__.setdefault("time", time)

        def set_value(value):
            mod[param_id] = value
            obj.update_tag()
            t0 = time.perf_counter()
            bpy.context.view_layer.update()
            return (time.perf_counter() - t0) * 1000.0

        def instance_count():
            dg = bpy.context.evaluated_depsgraph_get()
            return len(list(dg.object_instances))

        ctx = Context()
        ctx.bpy = bpy
        ctx.target = target
        ctx.obj = obj
        ctx.mod = mod
        ctx.node_tree = mod.node_group
        ctx.param = target["param"]
        ctx.param_id = param_id
        ctx.set_value = set_value
        ctx.instance_count = instance_count

        gates = load_gates(args.gates)
        missing = [(g.name, name) for g in gates for name in missing_exports(g)]
        if missing:
            raise RuntimeError("missing exports: %s" % missing)

        gctx = GateContext(args.work)
        summaries = []
        for gate in gates:
            gate.arm(gctx)
        try:
            evaluate(ctx)
        finally:
            for gate in reversed(gates):
                summaries.append(gate.dump(gctx))

        raw = {}
        for summary in summaries:
            raw.update(summary.get("raw", {}))
        write_status(args.work, {
            "ok": True,
            "node": args.node,
            "target": target,
            "gates": summaries,
            "raw": raw,
        })
        print(">> raw:", json.dumps(raw, ensure_ascii=False))
    except Exception as exc:
        write_status(args.work, {
            "ok": False,
            "error": "%s: %s" % (type(exc).__name__, exc),
            "traceback": traceback.format_exc(),
        })
        traceback.print_exc()
        raise


main()
