#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CovTrace engine: orchestration only.

Record writes raw into cache/<node>/<hash8>/, translate reads that cache and
rebuilds the final JSON products without launching Blender again.
"""

import argparse
import json
import os
import shutil
import sys
import time

from cards.base import CardContext
from cards.between import BetweenCard
from cards.coverage import CoverageCard
from cards.disasm import DisasmCard
from cards.edge import EdgeCard
from cards.only_call import OnlyCallCard
from cards.returns import ReturnsCard
from cards.timing import TimingCard
from gates.calls import CallsGate
from gates.coverage import CoverageGate
from infra import blender as blender_lib
from infra import manifest, paths, runkey, target as targetfile

# Registration lives here. Add a module by importing it and appending one entry.
GATES = [CoverageGate(), CallsGate()]
CARDS = [EdgeCard(), OnlyCallCard(), DisasmCard(), ReturnsCard(), BetweenCard(),
         CoverageCard(), TimingCard()]

DEFAULT_KEEP_CACHE = 5


def fail(message):
    print("!! " + message, file=sys.stderr)
    return 1


def _load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _rebase_path(path, src, dst):
    if not path or not src or not dst:
        return path
    absolute = os.path.abspath(path)
    root = os.path.abspath(src)
    if os.path.normcase(absolute) == os.path.normcase(root):
        return dst
    prefix = root + os.sep
    if os.path.normcase(absolute).startswith(os.path.normcase(prefix)):
        return os.path.join(dst, absolute[len(prefix):])
    return path


def _rebase(obj, src, dst):
    raw = obj.get("raw")
    if isinstance(raw, dict):
        obj["raw"] = {k: _rebase_path(v, src, dst) for k, v in raw.items()}
    for gate in obj.get("gates", []):
        raw = gate.get("raw")
        if isinstance(raw, dict):
            gate["raw"] = {k: _rebase_path(v, src, dst) for k, v in raw.items()}
    return obj


def _prune_cache(node_dir, keep):
    if keep <= 0:
        return
    entries = []
    for name in os.listdir(node_dir):
        path = os.path.join(node_dir, name)
        if os.path.isdir(path):
            entries.append(path)
    entries.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for path in entries[keep:]:
        shutil.rmtree(path, ignore_errors=True)


def _keep_failed(work_dir, hash8, keep):
    if not os.path.isdir(work_dir):
        return ""
    node_dir = os.path.dirname(work_dir)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(node_dir, "%s.failed-%s" % (hash8, stamp))
    suffix = 1
    while os.path.exists(dest):
        dest = os.path.join(
            node_dir, "%s.failed-%s-%d" % (hash8, stamp, suffix))
        suffix += 1

    data = manifest.load(work_dir)
    if data is not None:
        _rebase(data, work_dir, dest)
        manifest.write(work_dir, data)
    status_path = os.path.join(work_dir, "status.json")
    if os.path.isfile(status_path):
        status = _load_json(status_path)
        _rebase(status, work_dir, dest)
        with open(status_path, "w", encoding="utf-8") as fh:
            json.dump(status, fh, ensure_ascii=False, indent=1)
            fh.write("\n")

    os.replace(work_dir, dest)
    _prune_cache(node_dir, keep)
    print(">> failed raw:", dest)
    return dest


def _capture_problem(status):
    gates = status.get("gates", [])
    calls = next((g for g in gates if g.get("name") == "calls"), None)
    if calls is None:
        return "calls 闸门没有产出"
    functions = calls.get("raw", {}).get("functions")
    if not functions or not os.path.isfile(functions) or os.path.getsize(functions) == 0:
        return "functions.bin 为空或缺失"
    if int(calls.get("edge_count", 0)) == 0:
        return "edge_count == 0（求值可能没有触发）"
    coverage = next((g for g in gates if g.get("name") == "coverage"), None)
    if coverage is not None:
        profraw = coverage.get("raw", {}).get("coverage")
        if not profraw or not os.path.isfile(profraw) or os.path.getsize(profraw) == 0:
            return "window.profraw 为空或缺失"
    return ""


def _run_cards(ctx, data):
    available_raw = set(ctx.raw_paths)
    products = set()
    summaries = []
    for card in CARDS:
        missing = []
        for need in card.needs:
            if need.startswith("raw:"):
                if need[4:] not in available_raw:
                    missing.append(need)
            elif need not in products:
                missing.append(need)
        if missing:
            raise RuntimeError("card %s missing inputs: %s" % (card.name, missing))

        summary = card.build(ctx)
        if summary.get("output"):
            products.add(summary["output"])
        summaries.append(summary)

    data["cards"] = summaries
    data["products"] = {
        item.get("name", "?"): item.get("output")
        for item in summaries if item.get("output")
    }
    return data


def _finalize_out(run_dir, staging_dir, data, force=False):
    manifest.write(staging_dir, data)
    if os.path.isdir(run_dir):
        if not force:
            raise RuntimeError("run dir appeared without --force: %s" % run_dir)
        shutil.rmtree(run_dir)
    os.replace(staging_dir, run_dir)


def _load_status(work_dir):
    path = os.path.join(work_dir, "status.json")
    if not os.path.isfile(path):
        return None
    return _load_json(path)


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
    options = {"coverage_keep_all": True} if a.keep_all else {}
    key = runkey.run_key(eval_path, a.node, blender, pdb, target, options)
    hash8 = runkey.short(key)
    out_root = paths.norm(a.out or paths.DEFAULT_OUT)
    run_dir = os.path.join(out_root, paths.safe_name(a.node), hash8)
    cache_dir = os.path.join(paths.CACHE, paths.safe_name(a.node), hash8)
    work_dir = cache_dir + ".tmp"

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
    print("options   :", json.dumps(options, ensure_ascii=False))
    print("run dir   :", run_dir)
    print("cache dir :", cache_dir)
    print("gates     :", [g.name for g in GATES] or "(未注册)")
    print("cards     :", [c.name for c in CARDS] or "(未注册)")

    if a.dry_run:
        print(">> dry-run：只检查路径和重复状态，不启动 blender")
        return 0

    if not GATES:
        return fail("没有注册任何闸门")

    os.makedirs(os.path.dirname(work_dir), exist_ok=True)
    shutil.rmtree(work_dir, ignore_errors=True)
    os.makedirs(work_dir)
    manifest.write(work_dir, manifest.base(
        key, hash8, a.node, eval_path, target["blend"], blender, pdb, options))

    gate_specs = ",".join(
        "%s:%s" % (type(g).__module__, type(g).__qualname__) for g in GATES)
    cmd = blender_lib.command(
        blender, eval_path, work_dir, a.node,
        blend=a.blend, obj=a.obj, mod=a.mod, param=a.param, gates=gate_specs)
    env = dict(os.environ)
    env.setdefault("LLVM_PROFILE_FILE", "NUL")
    blender_lib.run(cmd, env=env)

    status = _load_status(work_dir)
    if not status or not status.get("ok"):
        reason = (status or {}).get("error", "没有生成 status.json")
        failed = _keep_failed(work_dir, hash8, a.keep_cache)
        return fail("采集失败: %s\n  raw: %s" % (reason, failed))

    problem = _capture_problem(status)
    if problem:
        failed = _keep_failed(work_dir, hash8, a.keep_cache)
        return fail("采集结果异常: %s\n  raw: %s" % (problem, failed))

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

    print(">> raw :", json.dumps(data["raw"], ensure_ascii=False))
    print(">> work:", work_dir)
    if not CARDS:
        print(">> 模块 2 完成：raw 已生成，翻译卡片尚未注册")
        return 0

    os.makedirs(os.path.dirname(run_dir), exist_ok=True)
    staging_dir = os.path.join(os.path.dirname(run_dir), ".%s.tmp" % hash8)
    shutil.rmtree(staging_dir, ignore_errors=True)
    os.makedirs(staging_dir)

    ctx = CardContext(
        work_dir, staging_dir, target, a.node, data, blender, pdb, data["raw"],
        options=options)
    try:
        _run_cards(ctx, data)

        if a.no_raw:
            data["raw"] = {}
            for gate in data.get("gates", []):
                gate["raw"] = {}
            data["raw_removed"] = True
        else:
            _rebase(data, work_dir, cache_dir)
            status = _load_json(os.path.join(work_dir, "status.json"))
            _rebase(status, work_dir, cache_dir)
            with open(os.path.join(work_dir, "status.json"), "w",
                      encoding="utf-8") as fh:
                json.dump(status, fh, ensure_ascii=False, indent=1)
                fh.write("\n")

        _finalize_out(run_dir, staging_dir, data, force=a.force)

        if a.no_raw:
            shutil.rmtree(work_dir, ignore_errors=True)
        else:
            if os.path.isdir(cache_dir):
                shutil.rmtree(cache_dir)
            os.replace(work_dir, cache_dir)
            manifest.write(cache_dir, data)
            _prune_cache(os.path.dirname(cache_dir), a.keep_cache)
            print(">> cache:", cache_dir)
    except Exception as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        failed = _keep_failed(work_dir, hash8, a.keep_cache)
        return fail("翻译失败: %s\n  raw: %s" % (exc, failed))

    print(">> products:", json.dumps(data["products"], ensure_ascii=False))
    print(">> run dir :", run_dir)
    return 0


def translate(a):
    cache_dir = paths.norm(a.cache_dir)
    data = manifest.load(cache_dir)
    if data is None:
        return fail("cache 里没有 run.json: %s" % cache_dir)

    status = _load_status(cache_dir)
    if not status or not status.get("ok"):
        return fail("cache 的 status.json 不是成功状态: %s" % cache_dir)

    raw = data.get("raw") or status.get("raw") or {}
    if not raw:
        return fail("cache 没有 raw 数据: %s" % cache_dir)
    missing = [path for path in raw.values() if not os.path.isfile(path)]
    if missing:
        return fail("cache raw 文件缺失:\n  " + "\n  ".join(missing))

    node = data.get("node") or status.get("node")
    hash8 = data.get("hash8") or runkey.short(data.get("run_key", ""))
    blender = data.get("blender")
    pdb = data.get("pdb")
    if not node or not hash8 or not blender:
        return fail("cache manifest 缺少 node/hash8/blender: %s" % cache_dir)

    options = dict(data.get("options") or {})
    if a.keep_all is not None:
        options["coverage_keep_all"] = a.keep_all
    data["options"] = options

    out_root = paths.norm(a.out or paths.DEFAULT_OUT)
    run_dir = os.path.join(out_root, paths.safe_name(node), hash8)
    os.makedirs(os.path.dirname(run_dir), exist_ok=True)
    staging_dir = os.path.join(
        os.path.dirname(run_dir), ".%s.translate.tmp" % hash8)
    shutil.rmtree(staging_dir, ignore_errors=True)
    os.makedirs(staging_dir)

    ctx = CardContext(
        cache_dir, staging_dir, status.get("target", {}), node, data,
        blender, pdb, raw, options=options)
    try:
        _run_cards(ctx, data)
        _finalize_out(run_dir, staging_dir, data, force=True)
    except Exception as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        return fail("翻译失败: %s\n  cache: %s" % (exc, cache_dir))

    print(">> products:", json.dumps(data["products"], ensure_ascii=False))
    print(">> run dir :", run_dir)
    print(">> cache   :", cache_dir)
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
    p.add_argument("--keep-cache", type=int, default=DEFAULT_KEEP_CACHE,
                   help="每个节点保留最近 N 个 cache（0=不清理）")
    p.add_argument("--no-raw", action="store_true",
                   help="所有卡片成功后删除 raw cache")
    p.add_argument("--keep-all", action="store_true",
                   help="coverage.json 不过滤路径（默认只留 source/ + intern/）")

    t = sub.add_parser("translate", help="用 cache 里的 raw 重跑翻译卡片")
    t.add_argument("cache_dir", help="cache/<node>/<hash8> 目录")
    t.add_argument("--out", default="", help="输出根目录，默认 CovTrace/out")
    t.add_argument("--keep-all", action="store_true", default=None,
                   help="覆盖 cache 里的 coverage_keep_all 设置")

    a = ap.parse_args()
    if a.cmd == "run":
        return run(a)
    if a.cmd == "translate":
        return translate(a)
    return 2


if __name__ == "__main__":
    sys.exit(main())
