#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CovTrace engine: orchestration only.

Module 1 scope: paths, run identity, manifest/duplicate checks, CLI skeleton.
Gates and cards are registered here explicitly by the developer; runtime users
only pass --eval and --node.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile

from cards.base import CardContext
from cards.between import BetweenCard
from cards.coverage import CoverageCard
from cards.edge import EdgeCard
from cards.returns import ReturnsCard
from gates.calls import CallsGate
from gates.coverage import CoverageGate
from infra import blender as blender_lib
from infra import manifest, paths, runkey, target as targetfile

# Registration lives here. Add a module by importing it and appending one entry.
GATES = [CoverageGate(), CallsGate()]
CARDS = [EdgeCard(), ReturnsCard(), BetweenCard(), CoverageCard()]


def fail(message):
    print("!! " + message, file=sys.stderr)
    return 1


def run(a):
    eval_path = paths.norm(a.eval)
    if not os.path.isfile(eval_path):
        return fail("找不到求值脚本: %s" % eval_path)
    if not a.node.strip():
        return fail("--node 不能为空")

    try:
        target = targetfile.load(eval_path)
        target = targetfile.merge(target, a.blend, a.obj, a.mod, a.param)
        target["blend"] = paths.norm(target["blend"])
        targetfile.validate(target)
    except targetfile.TargetError as exc:
        return fail(str(exc))

    blender = paths.norm(a.blender or paths.DEFAULT_BLENDER)
    if not os.path.isfile(blender):
        return fail("找不到插桩 blender: %s" % blender)

    pdb = paths.pdb_for(blender)
    key = runkey.run_key(eval_path, a.node, blender, pdb, target)
    hash8 = runkey.short(key)
    out_root = paths.norm(a.out or paths.DEFAULT_OUT)
    run_dir = os.path.join(out_root, paths.safe_name(a.node), hash8)

    state = manifest.classify(run_dir, key)
    if state == "duplicate":
        return fail("你要的东西已经跑过了：%s" % run_dir)
    if state == "conflict" and not a.force:
        return fail("目录已存在但是另一次运行：%s\n  用 --force 覆盖" % run_dir)
    if state == "incomplete" and not a.force:
        return fail("目录存在但没有完整 manifest：%s\n  用 --force 覆盖" % run_dir)

    print("node      :", a.node)
    print("eval      :", eval_path)
    print("blend     :", target["blend"])
    print("object    :", target["object"])
    print("modifier  :", target["modifier"])
    print("node tree :", target.get("node_tree") or "(修改器的 node_group)")
    print("param     :", target["param"])
    print("blender   :", blender)
    print("pdb       :", pdb if os.path.isfile(pdb) else "(缺失)")
    print("run key   :", key)
    print("hash8     :", hash8)
    print("run dir   :", run_dir)
    print("gates     :", [g.name for g in GATES] or "(未注册)")
    print("cards     :", [c.name for c in CARDS] or "(未注册)")

    if a.dry_run:
        print(">> dry-run：只检查路径和重复状态，不启动 blender")
        return 0

    if not GATES:
        return fail("没有注册任何闸门")

    work_dir = tempfile.mkdtemp(prefix="covtrace-work-")
    manifest.write(work_dir, manifest.base(
        key, hash8, a.node, eval_path, target["blend"], blender, pdb))

    gate_specs = ",".join(
        "%s:%s" % (type(g).__module__, type(g).__qualname__) for g in GATES)
    cmd = blender_lib.command(
        blender, eval_path, work_dir, a.node,
        blend=a.blend, obj=a.obj, mod=a.mod, param=a.param, gates=gate_specs)
    env = dict(os.environ)
    env.setdefault("LLVM_PROFILE_FILE", "NUL")
    blender_lib.run(cmd, env=env)

    status_path = os.path.join(work_dir, "status.json")
    status = None
    if os.path.isfile(status_path):
        with open(status_path, encoding="utf-8") as fh:
            status = json.load(fh)
    if not status or not status.get("ok"):
        reason = (status or {}).get("error", "没有生成 status.json")
        return fail("采集失败: %s\n  work: %s" % (reason, work_dir))

    data = manifest.load(work_dir) or {}
    data["gates"] = status.get("gates", [])
    data["raw"] = status.get("raw", {})
    data["counts"] = {
        gate.get("name", "?"): {
            key: value for key, value in gate.items()
            if key.endswith("_count")
        }
        for gate in status.get("gates", [])
    }
    manifest.write(work_dir, data)

    print(">> raw :", json.dumps(status.get("raw", {}), ensure_ascii=False))
    print(">> work:", work_dir)
    if not CARDS:
        print(">> 模块 2 完成：raw 已生成，翻译卡片尚未注册")
        return 0

    node_dir = os.path.dirname(run_dir)
    os.makedirs(node_dir, exist_ok=True)
    staging_dir = os.path.join(node_dir, ".%s.tmp" % hash8)
    shutil.rmtree(staging_dir, ignore_errors=True)
    os.makedirs(staging_dir)

    ctx = CardContext(
        work_dir, staging_dir, target, a.node, data, blender, pdb,
        status.get("raw", {}))
    available_raw = set(status.get("raw", {}))
    products = set()
    summaries = []
    try:
        for card in CARDS:
            missing = []
            for need in card.needs:
                if need.startswith("raw:"):
                    if need[4:] not in available_raw:
                        missing.append(need)
                elif need not in products:
                    missing.append(need)
            if missing:
                raise RuntimeError(
                    "card %s missing inputs: %s" % (card.name, missing))

            summary = card.build(ctx)
            if summary.get("output"):
                products.add(summary["output"])
            summaries.append(summary)

        data["cards"] = summaries
        data["products"] = {
            item.get("name", "?"): item.get("output")
            for item in summaries if item.get("output")
        }
        manifest.write(staging_dir, data)

        if os.path.isdir(run_dir):
            if not a.force:
                raise RuntimeError("run dir appeared without --force: %s" % run_dir)
            shutil.rmtree(run_dir)
        os.replace(staging_dir, run_dir)
    except Exception as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        return fail("翻译失败: %s\n  work: %s" % (exc, work_dir))

    print(">> products:", json.dumps(data["products"], ensure_ascii=False))
    print(">> run dir :", run_dir)
    return 0


def main():
    ap = argparse.ArgumentParser(prog="engine.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="跑一次求值并生成产物")
    p.add_argument("--blend", default="", help="覆盖 TARGET['blend']")
    p.add_argument("--eval", required=True, help="求值脚本 .py（含 TARGET）")
    p.add_argument("--node", required=True, help="节点名，用于目录命名和 between 解析")
    p.add_argument("--obj", default="", help="覆盖 TARGET['object']")
    p.add_argument("--mod", default="", help="覆盖 TARGET['modifier']")
    p.add_argument("--param", default="", help="覆盖 TARGET['param']")
    p.add_argument("--blender", default="", help="插桩 blender.exe")
    p.add_argument("--out", default="", help="输出根目录，默认 CovTrace/out")
    p.add_argument("--force", action="store_true", help="覆盖冲突/不完整目录")
    p.add_argument("--dry-run", action="store_true", help="只检查路径和重复，不启动")

    a = ap.parse_args()
    if a.cmd == "run":
        return run(a)
    return 2


if __name__ == "__main__":
    sys.exit(main())
