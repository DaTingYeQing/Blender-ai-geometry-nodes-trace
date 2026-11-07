# -*- coding: utf-8 -*-
"""Boundary backend: validate, run before/after, let DiffCard write diff.json.

Usage:
  python frag/backend.py --eval eval/frag2.py
  python frag/backend.py --eval eval/frag2.py --node my_boundary --force
"""

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import directories
import registry
from infra import paths
from infra import target as targetfile


def _run_engine(args):
    cmd = [sys.executable, directories.ENGINE_SCRIPT] + args
    print(">>", " ".join(cmd))
    proc = subprocess.run(
        cmd, text=True, encoding="utf-8", errors="replace",
        capture_output=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc


def _line(text, prefix):
    for line in text.splitlines():
        if line.startswith(prefix):
            rest = line[len(prefix):].strip()
            return rest.lstrip(": ").strip()
    return ""


def _validation(text):
    raw = _line(text, ">> validation")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    ap = argparse.ArgumentParser(prog="frag/backend.py")
    ap.add_argument("--eval", required=True)
    ap.add_argument("--measure-node", default="",
                    help="覆盖 eval 里的 NODE")
    ap.add_argument("--node", default="", help="输出目录名")
    ap.add_argument("--blender", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    eval_path = paths.norm(args.eval)
    if not os.path.isfile(eval_path):
        print("!! 找不到 eval: %s" % eval_path, file=sys.stderr)
        return 2
    target = targetfile.load(eval_path)
    targetfile.validate(target)
    from_eval = targetfile.measure_node(eval_path)
    spec = args.measure_node or from_eval
    if not spec:
        print("!! eval 里没有 NODE，也没有 --measure-node", file=sys.stderr)
        return 2

    # NODE 已经在 eval 里时，不再通过命令行传中文，避免编码问题。
    measure_arg = ["--measure-node", args.measure_node] if args.measure_node else []

    common = []
    if args.blender:
        common += ["--blender", args.blender]
    if args.out:
        common += ["--out", args.out]
    if args.force:
        common += ["--force"]

    # 1) 校验：开文件，但不开 trace，不求值
    validate_cmd = ["validate", "--eval", eval_path] + measure_arg
    if args.blender:
        validate_cmd += ["--blender", args.blender]
    checked = _run_engine(validate_cmd)
    if checked.returncode != 0:
        print("!! 校验失败，未执行求值", file=sys.stderr)
        return checked.returncode or 1
    info = _validation(checked.stdout) or {}
    measure = info.get("measure") or {}
    node_name = args.node or ("bnd_" + paths.safe_name(
        measure.get("type") or spec))

    # 2) before：组输出接目标的几何输入
    before = _run_engine(
        ["run", "--eval", eval_path, "--node", node_name,
         "--phase", "before"] + measure_arg + common)
    if before.returncode != 0:
        return before.returncode
    before_cache = _line(before.stdout, ">> cache")
    if not before_cache:
        print("!! 没找到 before cache 路径", file=sys.stderr)
        return 1

    # 3) after：组输出接目标的几何输出；DiffCard 最后和 before 相减
    after = _run_engine(
        ["run", "--eval", eval_path, "--node", node_name,
         "--phase", "after", "--diff-against", before_cache] +
        measure_arg + common)
    if after.returncode != 0:
        return after.returncode

    run_dir = _line(after.stdout, ">> run dir")
    print()
    print(">> measure : %s (%s)" % (measure.get("node") or spec,
                                    measure.get("type") or "?"))
    print(">> before  : %s" % before_cache)
    print(">> after   : %s" % (run_dir or "?"))
    if run_dir:
        print(">> diff    : %s" % os.path.join(
            run_dir, registry.PRODUCTS["diff"].path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
