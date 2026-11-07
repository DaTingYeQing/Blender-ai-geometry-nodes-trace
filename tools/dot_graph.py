# -*- coding: utf-8 -*-
"""Render a CovTrace edge.json as a full Graphviz graph.

Usage:
  python tools/dot_graph.py 7343650d            # -> out/<node>/7343650d/full.png
  python tools/dot_graph.py 7343650d -svg       # -> full.svg
  python tools/dot_graph.py 7343650d -png -svg  # both
  python tools/dot_graph.py --edge-json out/diff/edge_diff.json -svg
"""

import argparse
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")
DEFAULT_DOT = r"D:\qcachegrind074-x86\dot.exe"


def find_edge_json(hash8):
    """Find out/*/<hash8>/edge.json. Accept an unambiguous hash prefix."""
    exact = glob.glob(os.path.join(OUT, "*", hash8, "edge.json"))
    if exact:
        return sorted(exact)
    return sorted(p for p in glob.glob(os.path.join(OUT, "*", "*", "edge.json"))
                  if os.path.basename(os.path.dirname(p)).startswith(hash8))


def short_name(name, limit=64):
    text = name
    depth = 0
    out = []
    for ch in text:
        if ch == "<":
            depth += 1
            continue
        if ch == ">":
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            out.append(ch)
    text = "".join(out)
    parts = [p for p in text.split("::") if p]
    if len(parts) > 2:
        text = "::".join(parts[-2:])
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text or name[:limit]


def esc(text):
    return text.replace("\\", "\\\\").replace('"', '\\"')


def load_graph(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("functions") or [], data.get("edges") or []


def write_dot(path, funcs, edges, title):
    uniq_edges = {(e.get("caller"), e.get("callee")) for e in edges
                  if e.get("caller") is not None and e.get("callee") is not None}

    lines = [
        "digraph covtrace {",
        '  graph [rankdir=LR, overlap=false, splines=true, nodesep=0.18,'
        ' ranksep=0.45, fontsize=10, label="%s", labelloc=t];' % esc(title),
        '  node [shape=box, style="rounded,filled", fillcolor="#dbeafe",'
        ' color="#2563eb", fontname="Consolas", fontsize=8, margin="0.04,0.02"];',
        '  edge [color="#8a8a8a", arrowsize=0.55, penwidth=0.6];',
    ]
    for idx, f in enumerate(funcs):
        lines.append('  %d [label="%s", tooltip="%s"];'
                     % (idx, esc(short_name(f.get("name", ""))),
                        esc(f.get("name", ""))))
    for a, b in sorted(uniq_edges):
        lines.append("  %d -> %d;" % (a, b))
    lines.append("}")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("hash8", nargs="?", help="run hash, e.g. 7343650d")
    ap.add_argument("--edge-json", default="",
                    help="explicit edge.json (for diff files outside out/*/<hash>/)")
    ap.add_argument("--name", default="full", help="output basename")
    ap.add_argument("--out", default="", help="output directory")
    ap.add_argument("-png", "--png", action="store_true", dest="png",
                    help="render PNG (default)")
    ap.add_argument("-svg", "--svg", action="store_true", dest="svg",
                    help="render SVG")
    ap.add_argument("--dot", default=DEFAULT_DOT, help="dot.exe path")
    a = ap.parse_args()

    if a.edge_json:
        edge_path = os.path.abspath(a.edge_json)
        if not os.path.isfile(edge_path):
            print("!! edge.json not found: %s" % edge_path, file=sys.stderr)
            return 2
        run_id = a.hash8 or os.path.basename(os.path.dirname(edge_path))
    else:
        if not a.hash8:
            avail = sorted({os.path.basename(os.path.dirname(p))
                            for p in glob.glob(os.path.join(OUT, "*", "*", "edge.json"))})
            print("!! 需要指定哈希，例如: python tools/dot_graph.py 7343650d",
                  file=sys.stderr)
            if avail:
                print("   可用: %s" % ", ".join(avail[-20:]), file=sys.stderr)
            return 2
        matches = find_edge_json(a.hash8)
        if not matches:
            print("!! out/*/%s/edge.json 不存在" % a.hash8, file=sys.stderr)
            return 2
        if len(matches) > 1:
            matches.sort(key=os.path.getmtime, reverse=True)
            print(">> 多个匹配，使用最新的: %s" % matches[0])
        edge_path = matches[0]
        run_id = a.hash8

    funcs, edges = load_graph(edge_path)
    out_dir = a.out or os.path.dirname(edge_path)
    os.makedirs(out_dir, exist_ok=True)

    base = a.name
    title = "%s full: %d functions, %d edges" % (run_id, len(funcs), len(edges))
    dot_path = os.path.join(out_dir, base + ".dot")
    write_dot(dot_path, funcs, edges, title)
    print(">> edge: %s" % edge_path)
    print(">> dot : %s (%d nodes, %d edges)" % (dot_path, len(funcs), len(edges)))

    if not (a.png or a.svg):
        a.png = True
    formats = []
    if a.png:
        formats.append("png")
    if a.svg:
        formats.append("svg")

    if not os.path.isfile(a.dot):
        print("!! dot.exe not found: %s" % a.dot, file=sys.stderr)
        return 3
    for fmt in formats:
        path = os.path.join(out_dir, "%s.%s" % (base, fmt))
        subprocess.run([a.dot, "-T" + fmt, "-o", path, dot_path], check=True)
        print(">> img : %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
