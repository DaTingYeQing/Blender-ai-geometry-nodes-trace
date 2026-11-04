# -*- coding: utf-8 -*-
"""coverage card: window.profraw -> coverage.json.

Parser logic copied from cov/parse_coverage.py; the old project is untouched.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections import Counter

from infra import paths

from .base import TranslationCard

LLVM_COV = os.path.join(paths.LLVM_BIN, "llvm-cov.exe")
LLVM_PROFDATA = os.path.join(paths.LLVM_BIN, "llvm-profdata.exe")
SOURCE_ROOT = os.path.normpath(os.path.join(paths.ROOT, os.pardir, "blender-4.5.0"))

KEEP_PREFIXES = ("source/", "intern/")
HEADER_EXT = (".hh", ".h", ".hpp", ".hxx", ".inl", ".ipp", ".inc")

DATA_RE = re.compile(r"^\s*(\d+)\|([^|]*)\|(.*)$")
COUNT_RE = re.compile(r"^(\d+(?:\.\d+)?)([kMG]?)$")
COUNT_MULT = {"": 1, "k": 1_000, "M": 1_000_000, "G": 1_000_000_000}


def parse_count(text):
    text = text.strip()
    if not text:
        return 0
    match = COUNT_RE.match(text)
    if not match:
        return 0
    return int(float(match.group(1)) * COUNT_MULT[match.group(2)])


def to_rel(path):
    p = path.replace("\\", "/")
    root = SOURCE_ROOT.replace("\\", "/")
    if p.lower().startswith(root.lower() + "/"):
        return p[len(root) + 1:]
    return p


def keep_file(rel):
    return rel.replace("\\", "/").lower().startswith(KEEP_PREFIXES)


def norm_lcov_path(path):
    return to_rel(path).replace("\\", "/").lower()


def parse_lcov_counts(path):
    fn_line = {}
    fnda = {}
    order = []
    cur = None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.rstrip("\r\n")
            if s.startswith("SF:"):
                cur = norm_lcov_path(s[3:])
            elif s.startswith("FN:"):
                rest = s[3:]
                ln, name = rest.split(",", 1)
                fn_line[name] = (cur, int(ln))
                order.append(name)
            elif s.startswith("FNDA:"):
                count, name = s[5:].split(",", 1)
                fnda[name] = int(count)

    all_funcs = [fn_line[name] for name in order if fnda.get(name, 0) > 0]
    kept = [(f, ln) for f, ln in all_funcs if keep_file(f)]
    header = sum(1 for f, _ in kept if f.endswith(HEADER_EXT))
    by_mod = Counter()
    for f, _ in kept:
        parts = f.split("/")
        if parts[0] == "source" and len(parts) > 2:
            by_mod["source/" + parts[2]] += 1
        elif parts[0] == "intern" and len(parts) > 1:
            by_mod["intern/" + parts[1]] += 1
        else:
            by_mod[parts[0]] += 1
    return {
        "function_count": len(kept),
        "function_count_all": len(all_funcs),
        "function_count_source": len(kept) - header,
        "function_count_header": header,
        "function_count_modules": dict(by_mod.most_common()),
    }


def export_lcov(exe, profdata, out_path):
    with open(out_path, "w", encoding="utf-8") as fh:
        subprocess.run(
            [LLVM_COV, "export", exe, "-instr-profile=" + profdata,
             "--unify-instantiations", "--skip-branches", "--skip-expansions",
             "-format=lcov",
             r"--include-filename-regex=blender-4\.5\.0[\\/](source|intern)[\\/]"],
            stdout=fh, check=True)


def parse_show(src_path):
    per_file = {}
    cur_file = None
    scanned = 0
    with open(src_path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n").rstrip("\r")
            if line == "":
                continue
            match = DATA_RE.match(line)
            if match:
                if cur_file is None:
                    continue
                if parse_count(match.group(2)) >= 1:
                    per_file[cur_file].add(int(match.group(1)))
                continue
            if line.lstrip().startswith("^"):
                continue
            if (not line.startswith(" ") and line.endswith(":")
                    and ("\\" in line or "/" in line)):
                cur_file = to_rel(line[:-1])
                per_file.setdefault(cur_file, set())
                scanned += 1
    total = sum(len(v) for v in per_file.values())
    return per_file, scanned, total


def to_ranges(lines):
    out = []
    for n in lines:
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return out


def build_result(per_file, scanned, total, function_counts, eval_only=True):
    files = {}
    for rel in sorted(per_file):
        if eval_only and not keep_file(rel):
            continue
        lines = sorted(per_file[rel])
        if not lines:
            continue
        files[rel] = {"count": len(lines), "ranges": to_ranges(lines)}
    line_count = sum(entry["count"] for entry in files.values())
    meta = {
        "source_root": SOURCE_ROOT.replace("\\", "/"),
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scanned_files": scanned,
        "file_count": len(files),
        "line_count": line_count,
        "eval_only": eval_only,
    }
    meta.update(function_counts)
    return {"meta": meta, "files": files}


def dumps(result):
    meta = json.dumps(result["meta"], ensure_ascii=False, indent=2)
    meta = meta.replace("\n", "\n  ")
    lines = ["{", '  "meta": %s,' % meta, '  "files": {']
    items = []
    for path, entry in result["files"].items():
        rng = "[" + ", ".join("[%d, %d]" % (a, b) for a, b in entry["ranges"]) + "]"
        items.append('    %s: {"count": %d, "ranges": %s}'
                     % (json.dumps(path, ensure_ascii=False), entry["count"], rng))
    lines.append(",\n".join(items))
    lines += ["  }", "}", ""]
    return "\n".join(lines)


class CoverageCard(TranslationCard):
    name = "coverage"
    needs = ("raw:coverage",)

    def build(self, ctx):
        profraw = ctx.raw("coverage")
        exe = ctx.blender
        temp_dir = tempfile.mkdtemp(prefix="covtrace-coverage-")
        try:
            profdata = os.path.join(temp_dir, "blender.profdata")
            subprocess.run(
                [LLVM_PROFDATA, "merge", "-sparse", profraw, "-o", profdata],
                check=True)

            show = os.path.join(temp_dir, "cov_show.txt")
            with open(show, "w", encoding="utf-8", errors="replace") as fh:
                subprocess.run(
                    [LLVM_COV, "show", exe, "-instr-profile=" + profdata,
                     "-show-line-counts-or-regions",
                     "-show-instantiations=false",
                     "-show-expansions=false"],
                    stdout=fh, check=True)

            per_file, scanned, total = parse_show(show)

            lcov = os.path.join(temp_dir, "coverage.lcov")
            export_lcov(exe, profdata, lcov)
            counts = parse_lcov_counts(lcov)

            keep_all = bool(ctx.options.get("coverage_keep_all"))
            result = build_result(per_file, scanned, total, counts,
                                  eval_only=not keep_all)
            path = ctx.out("coverage.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(dumps(result))

            shutil.rmtree(temp_dir, ignore_errors=True)
            return {
                "name": self.name,
                "files": result["meta"]["file_count"],
                "lines": result["meta"]["line_count"],
                "functions": result["meta"].get("function_count"),
                "output": "coverage.json",
            }
        except Exception:
            print("!! coverage work dir kept:", temp_dir)
            raise
