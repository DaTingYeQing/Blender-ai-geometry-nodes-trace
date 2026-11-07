# -*- coding: utf-8 -*-
"""Render CovTrace edge.json as Graphviz DOT.

Examples:
  python tools/dot_graph.py --edge-json out/frag2/xxxx/edge.json --all
  python tools/dot_graph.py --edge-json ... --root "node_geo_boolean.*node_geo_exec" --depth 6
  python tools/dot_graph.py --edge-json ... --root "LazyFunctionForMultiFunctionNode.*execute_impl"
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import deque

DEFAULT_DOT = r"D:\qcachegrind074-x86\dot.exe"


def short_name(name, limit=64):
    """Keep the last two scope segments; strip template args for readability."""
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
    funcs = data.get("functions") or []
    edges = data.get("edges") or []
    return data, funcs, edges


def site_of(data, func):
    files = data.get("files") or []
    idx = func.get("file")
    if isinstance(idx, int) and 0 <= idx < len(files):
        path = files[idx].replace("\\", "/")
        return "%s:%s" % (os.path.basename(path), func.get("line") or 0)
    return ""


def label_of(data, func, with_site):
    label = short_name(func.get("name", ""))
    if with_site:
        site = site_of(data, func)
        if site:
            label += "\\n" + site
    return label


def adjacency(funcs, edges):
    out = {i: [] for i in range(len(funcs))}
    rev = {i: [] for i in range(len(funcs))}
    for e in edges:
        a, b = e.get("caller"), e.get("callee")
        if a is None or b is None:
            continue
        out[a].append(b)
        rev[b].append(a)
    return out, rev


def select_roots(funcs, patterns):
    rx = [re.compile(p) for p in patterns]
    return [i for i, f in enumerate(funcs) if any(r.search(f.get("name", "")) for r in rx)]


def closure(funcs, out, rev, roots, depth, direction):
    seen = set(roots)
    queue = deque((r, 0) for r in roots)
    while queue:
        node, d = queue.popleft()
        if depth >= 0 and d >= depth:
            continue
        nxt = []
        if direction in ("out", "both"):
            nxt.extend(out.get(node, ()))
        if direction in ("in", "both"):
            nxt.extend(rev.get(node, ()))
        for child in nxt:
            if child not in seen:
                seen.add(child)
                queue.append((child, d + 1))
    return seen


def write_dot(path, data, funcs, edges, keep, title,
              cluster_module=False, label_site=False):
    keep = set(keep)
    uniq_edges = set()
    for e in edges:
        a, b = e.get("caller"), e.get("callee")
        if a in keep and b in keep:
            uniq_edges.add((a, b))

    modules = {}
    if cluster_module:
        for idx in keep:
            modules.setdefault(funcs[idx].get("module") or "(unknown)", []).append(idx)
        modules = {k: sorted(v) for k, v in modules.items()}

    lines = [
        "digraph covtrace {",
        '  graph [rankdir=LR, overlap=false, splines=true, nodesep=0.18, ranksep=0.45,'
        ' fontsize=10, label="%s", labelloc=t];' % esc(title),
        '  node [shape=box, style="rounded,filled", fillcolor="#eef3fb",'
        ' color="#5b7fa6", fontname="Consolas", fontsize=8, margin="0.04,0.02"];',
        '  edge [color="#8a8a8a", arrowsize=0.55, penwidth=0.6];',
    ]

    def node_lines(indices, indent="  "):
        rows = []
        for idx in indices:
            f = funcs[idx]
            label = label_of(data, f, label_site)
            rows.append(
                '%s%d [label="%s", fillcolor="#dbeafe", color="#2563eb", tooltip="%s"];'
                % (indent, idx, esc(label), esc(f.get("name", ""))))
        return rows

    if cluster_module:
        for module in sorted(modules):
            lines.append('  subgraph "cluster_%s" {' % esc(module).replace(" ", "_"))
            lines.append('    label="%s";' % esc(module))
            lines.append('    style="rounded,dashed"; color="#bbbbbb"; fontsize=8;')
            lines.extend(node_lines(modules[module], "    "))
            lines.append("  }")
    else:
        lines.extend(node_lines(sorted(keep)))

    for a, b in sorted(uniq_edges):
        lines.append("  %d -> %d;" % (a, b))

    lines.append("}")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def render(dot_exe, dot_path, out_dir, base, formats):
    made = []
    for fmt in formats:
        out = os.path.join(out_dir, "%s.%s" % (base, fmt))
        cmd = [dot_exe, "-T" + fmt, "-o", out, dot_path]
        subprocess.run(cmd, check=True)
        made.append(out)
    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edge-json", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--name", default="", help="output basename")
    ap.add_argument("--all", action="store_true", help="include every node")
    ap.add_argument("--root", action="append", default=[],
                    help="regex on full symbol name; repeatable")
    ap.add_argument("--depth", type=int, default=-1,
                    help="BFS depth from roots (-1 = unlimited)")
    ap.add_argument("--direction", choices=("out", "in", "both"), default="out")
    ap.add_argument("--cluster-module", action="store_true")
    ap.add_argument("--label-site", action="store_true",
                    help="append file:line to each node label")
    ap.add_argument("--format", action="append", default=[],
                    help="svg/png/pdf; repeatable")
    ap.add_argument("--dot", default=DEFAULT_DOT)
    ap.add_argument("--max-nodes", type=int, default=0,
                    help="refuse graphs larger than this unless --all")
    a = ap.parse_args()

    data, funcs, edges = load_graph(a.edge_json)
    out_dir = a.out or os.path.dirname(os.path.abspath(a.edge_json))
    os.makedirs(out_dir, exist_ok=True)

    if a.all:
        keep = set(range(len(funcs)))
        base = a.name or "full"
        title = "CovTrace full call graph: %d functions, %d edges" % (
            len(funcs), len(edges))
    elif a.root:
        out, rev = adjacency(funcs, edges)
        roots = select_roots(funcs, a.root)
        if not roots:
            print("!! no root matches: %s" % a.root, file=sys.stderr)
            return 2
        keep = closure(funcs, out, rev, roots, a.depth, a.direction)
        base = a.name or "graph"
        title = "%s (roots=%d, depth=%s)" % (
            ", ".join(a.root), len(roots),
            "unlimited" if a.depth < 0 else a.depth)
    else:
        print("!! use --all or --root", file=sys.stderr)
        return 2

    if a.max_nodes and not a.all and len(keep) > a.max_nodes:
        print("!! graph too large: %d nodes > %d" % (len(keep), a.max_nodes),
              file=sys.stderr)
        return 3

    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", base)
    dot_path = os.path.join(out_dir, base + ".dot")
    write_dot(dot_path, data, funcs, edges, keep, title,
              a.cluster_module, a.label_site)
    print(">> dot : %s (%d nodes)" % (dot_path, len(keep)))

    formats = a.format or ["svg"]
    if a.dot and os.path.isfile(a.dot):
        for path in render(a.dot, dot_path, out_dir, base, formats):
            print(">> img : %s" % path)
    else:
        print(">> dot.exe not found, leaving .dot only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
