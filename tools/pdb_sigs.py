# -*- coding: utf-8 -*-
"""Per-function output classification from blender.pdb.

Subcommands:
  extract   dump module symbol streams and collect function records
  resolve   resolve full signatures from the TPI stream and classify outputs
  all       extract + resolve

`extract` reads S_GPROC32 (global) and S_LPROC32 (static) records. Static
functions matter: every node_geo_exec is static and would be missed otherwise.

`resolve` consumes the TPI dump, because the signature text printed in the
symbol stream is truncated for long types. The type index in the record is
exact, so the full return type and parameter list are recovered by joining the
symbol stream with the type stream.
"""

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from infra import paths

DEFAULT_LIBS = ("bf_nodes", "bf_geometry", "bf_blenkernel", "bf_functions")
DEFAULT_RVA_SECTION = 1
IMAGE_SECTION_VA = 0x1000

MOD_RE = re.compile(r"\s*Mod (\d+) \| `(.+)`:")
PROC_RE = re.compile(r"S_[GL]PROC32 \[size = \d+\] `(.*)`\s*$")
ADDR_RE = re.compile(r"addr = ([0-9A-Fa-f]+):(\d+), code size = (\d+)")
PTR_SIG_RE = re.compile(r"type = `(0x[0-9A-Fa-f]+) \((.*)\)`")

RET_RE = re.compile(
    r"return type = (0x[0-9A-Fa-f]+)(?: \((.*?)\))?, # args = (\d+), "
    r"param list = (0x[0-9A-Fa-f]+)")
THIS_RE = re.compile(r"this type = (0x[0-9A-Fa-f]+)(?: \((.*?)\))?")
PTR_RE = re.compile(
    r"referent = (0x[0-9A-Fa-f]+)(?: \((.*?)\))?, mode = (\w+), "
    r"opts = (\w+), kind = (\w+)")
MODIFIER_RE = re.compile(r"referent = (0x[0-9A-Fa-f]+)(?: \((.*?)\))?, modifiers = (.+)$")
ARR_RE = re.compile(r"element type: (0x[0-9A-Fa-f]+)(?: \((.*?)\))?")
NAMED_KINDS = {"STRUCTURE", "CLASS", "UNION", "ENUM", "TYPEDEF"}
BUILTIN_RET = re.compile(
    r"^(void|bool|char|signed char|unsigned char|short|unsigned short|int|"
    r"unsigned int|long|unsigned long|__int64|unsigned __int64|float|double|"
    r"long double|wchar_t|char8_t|char16_t|char32_t)(?:$|[^A-Za-z0-9_])")

# Handles whose outputs are written through the object rather than returned.
OUTPUT_CHANNELS = (
    ("node_exec_params", "blender::nodes::GeoNodeExecParams"),
    ("lazy_function_params", "blender::fn::lazy_function::Params"),
    ("multi_function_params", "blender::fn::multi_function::Params"),
    ("mutable_span", "blender::MutableSpan<"),
    ("node_declaration_builder", "blender::nodes::NodeDeclarationBuilder"),
)


def say(msg):
    print(msg, flush=True)


def llvm_pdbutil_path(arg):
    if arg:
        return arg
    return os.path.join(paths.LLVM_BIN, "llvm-pdbutil.exe")


def default_pdb():
    return paths.pdb_for(paths.DEFAULT_BLENDER)


def cache_identity(pdb):
    fp = paths.file_fingerprint(pdb)
    key = hashlib.sha1(fp.encode("utf-8")).hexdigest()[:8]
    return os.path.join(paths.CACHE, "pdb_sigs", key)


def run_dump(tool, pdb, extra, stdout_path):
    cmd = [tool, "dump"] + extra + [pdb]
    with open(stdout_path, "wb") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise RuntimeError("llvm-pdbutil failed: %s" % " ".join(cmd))


def load_modules(mod_path):
    mods = []
    for line in open(mod_path, encoding="utf-8", errors="replace"):
        m = MOD_RE.match(line)
        if m:
            mods.append((int(m.group(1)), m.group(2)))
    return mods


def selected_modules(mods, libs, all_modules):
    if all_modules:
        return mods
    needles = tuple("\\" + lib for lib in libs)
    return [(idx, path) for idx, path in mods if any(n in path for n in needles)]


def parse_module(job):
    tool, pdb, idx, path = job
    try:
        proc = subprocess.run(
            [tool, "dump", "-symbols", "-modi=%d" % idx, pdb],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=600)
    except Exception as exc:
        return idx, path, [], str(exc)
    text = proc.stdout.decode("utf-8", "replace")
    rows = []
    name = None
    addr = None
    sec = None
    size = None
    for line in text.splitlines():
        m = PROC_RE.search(line)
        if m:
            name = m.group(1)
            addr = None
            sec = None
            size = None
            continue
        if name is None:
            continue
        m = ADDR_RE.search(line)
        if m and addr is None:
            sec = int(m.group(1), 16)
            addr = int(m.group(2))
            size = int(m.group(3))
            continue
        m = PTR_SIG_RE.search(line)
        if m and addr is not None:
            rows.append({
                "name": name,
                "module_index": idx,
                "module": path,
                "section": sec,
                "offset": addr,
                "rva": (IMAGE_SECTION_VA + addr) if sec == DEFAULT_RVA_SECTION else None,
                "code_size": size,
                "type_index": m.group(1),
                "sig": m.group(2),
            })
            name = None
    return idx, path, rows, None


def cmd_extract(args):
    pdb = paths.norm(args.pdb)
    if not os.path.isfile(pdb):
        return "PDB not found: %s" % pdb
    tool = llvm_pdbutil_path(args.llvm_pdbutil)
    out_dir = paths.norm(args.cache_dir or cache_identity(pdb))
    os.makedirs(out_dir, exist_ok=True)
    mod_path = os.path.join(out_dir, "modules.txt")
    if not os.path.isfile(mod_path) or args.refresh_modules:
        say(">> dumping module list")
        run_dump(tool, pdb, ["-modules"], mod_path)
    mods = selected_modules(load_modules(mod_path), args.libs, args.all_modules)
    say(">> selected modules: %d" % len(mods))
    jobs = [(tool, pdb, idx, path) for idx, path in mods]
    rows, errors = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for n, (idx, path, got, err) in enumerate(pool.map(parse_module, jobs), 1):
            if err:
                errors.append((idx, path, err))
            rows.extend(got)
            if n % 50 == 0:
                say("   %d/%d modules, %d functions" % (n, len(mods), len(rows)))
    sig_path = os.path.join(out_dir, "sigs.jsonl")
    with open(sig_path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    say(">> functions: %d, errors: %d" % (len(rows), len(errors)))
    say(">> %s" % sig_path)
    return None


def _split_params(text):
    if not text.strip():
        return []
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch in "<([":
            depth += 1
        elif ch in ">)]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur).strip())
    return [p for p in parts if p]


def _channel_of(param):
    p = param.strip()
    for prefix in ("const ", "volatile "):
        if p.startswith(prefix):
            p = p[len(prefix):]
    base = p.rstrip("&* ").strip()
    for name, pattern in OUTPUT_CHANNELS:
        if base == pattern or base.startswith(pattern):
            return name
    return None


def _param_flags(param):
    p = param.strip()
    cands = [i for i in (p.find("*"), p.find("&")) if i >= 0]
    if not cands:
        return {"pointer": False, "reference": False, "callback": False, "out": False}
    i = min(cands)
    before = p[:i].strip()
    after = p[i + 1:].strip()
    is_ref = p[i] == "&"
    pointee_const = before.startswith("const ") or before.endswith(" const")
    ptr_const = after.startswith("const")
    callback = "(*" in p or "(&" in p
    out = not callback and not pointee_const and not ptr_const
    return {
        "pointer": not is_ref,
        "reference": is_ref,
        "callback": callback,
        "out": out,
    }


def _parse_types(path, needed):
    names, named = {}, {}
    procs, arglists = {}, {}
    ptr, mod, arrays = {}, {}, {}
    cur_idx = None
    cur_kind = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.lstrip()
            if s.startswith("0x") and " | LF_" in line:
                idx_s, rest = s.split(" | LF_", 1)
                try:
                    cur_idx = int(idx_s, 16)
                except ValueError:
                    cur_idx, cur_kind = None, None
                    continue
                cur_kind = rest.split(" ", 1)[0].split("[", 1)[0].strip()
                if cur_kind in NAMED_KINDS:
                    a, b = line.find("`"), line.rfind("`")
                    if 0 <= a < b:
                        named[cur_idx] = line[a + 1:b]
                continue
            if cur_kind is None:
                continue
            if cur_kind == "ARGLIST":
                if s.startswith("0x") and ": `" in line:
                    _, t = s.split(": `", 1)
                    arglists.setdefault(cur_idx, []).append(t.rstrip().rstrip("`"))
                continue
            if cur_kind in ("PROCEDURE", "MFUNCTION"):
                if cur_idx not in needed:
                    continue
                m = RET_RE.search(line)
                if m:
                    ridx = int(m.group(1), 16)
                    if m.group(2):
                        names[ridx] = m.group(2)
                    procs[cur_idx] = {
                        "kind": cur_kind.lower(),
                        "ret_idx": ridx,
                        "ret_name": m.group(2),
                        "arglist": int(m.group(4), 16),
                        "this_idx": None,
                        "this_name": None,
                    }
                    continue
                m = THIS_RE.search(line)
                if m and cur_idx in procs:
                    procs[cur_idx]["this_idx"] = int(m.group(1), 16)
                    procs[cur_idx]["this_name"] = m.group(2)
                    if m.group(2):
                        names[int(m.group(1), 16)] = m.group(2)
                continue
            if cur_kind == "POINTER":
                m = PTR_RE.search(line)
                if m:
                    ref = int(m.group(1), 16)
                    if m.group(2):
                        names[ref] = m.group(2)
                    ptr[cur_idx] = (ref, m.group(3), m.group(4))
                continue
            if cur_kind == "MODIFIER":
                m = MODIFIER_RE.search(line)
                if m:
                    ref = int(m.group(1), 16)
                    if m.group(2):
                        names[ref] = m.group(2)
                    mod[cur_idx] = (ref, m.group(3).strip())
                continue
            if cur_kind == "ARRAY":
                m = ARR_RE.search(line)
                if m:
                    ref = int(m.group(1), 16)
                    if m.group(2):
                        names[ref] = m.group(2)
                    arrays[cur_idx] = ref
                continue

    def resolve(idx, depth=0):
        if depth > 12:
            return "type@0x%X" % idx
        if idx in names:
            return names[idx]
        if idx in named:
            return named[idx]
        if idx in ptr:
            ref, mode, opts = ptr[idx]
            value = resolve(ref, depth + 1) + ("*" if mode == "pointer" else "&")
            if opts == "const":
                value += " const"
            return value
        if idx in mod:
            ref, mods = mod[idx]
            return mods.replace(",", " ") + " " + resolve(ref, depth + 1)
        if idx in arrays:
            return resolve(arrays[idx], depth + 1) + "[]"
        return "type@0x%X" % idx

    def is_const_type(idx, depth=0):
        if depth > 12:
            return False
        if idx in mod:
            return "const" in mod[idx][1]
        if idx in ptr:
            return is_const_type(ptr[idx][0], depth + 1)
        return False

    return procs, arglists, resolve, is_const_type


def cmd_resolve(args):
    pdb = paths.norm(args.pdb)
    tool = llvm_pdbutil_path(args.llvm_pdbutil)
    out_dir = paths.norm(args.cache_dir or cache_identity(pdb))
    sig_path = os.path.join(out_dir, "sigs.jsonl")
    if not os.path.isfile(sig_path):
        return "missing %s; run extract first" % sig_path
    types_path = os.path.join(out_dir, "types.txt")
    if not os.path.isfile(types_path) or args.refresh_types:
        say(">> dumping type stream (about 1.2 GB)")
        run_dump(tool, pdb, ["-types"], types_path)

    needed = set()
    with open(sig_path, encoding="utf-8") as fh:
        for line in fh:
            needed.add(int(json.loads(line)["type_index"], 16))
    say(">> function type indices: %d" % len(needed))
    procs, arglists, resolve, is_const_type = _parse_types(types_path, needed)

    rows = []
    missing = 0
    with open(sig_path, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            p = procs.get(int(rec["type_index"], 16))
            if p is None:
                missing += 1
                continue
            ret = p["ret_name"] or resolve(p["ret_idx"])
            params = arglists.get(p["arglist"], [])
            flags = [_param_flags(x) for x in params]
            out_params = [i for i, f in enumerate(flags) if f["out"]]
            channels = []
            for i, param in enumerate(params):
                channel = _channel_of(param)
                if channel:
                    channels.append({"index": i, "type": param, "channel": channel})
            this_type = (p["this_name"] or resolve(p["this_idx"])) if p["this_idx"] else None
            this_const = is_const_type(p["this_idx"]) if p["this_idx"] else None
            returns_value = ret != "void"
            explicit = returns_value or bool(out_params)
            record_ret = (not ret.endswith(("*", "&"))) and not BUILTIN_RET.match(ret)
            implicit_params = []
            if p["kind"] == "mfunction" and this_type:
                implicit_params.append({"kind": "this", "type": this_type})
            if record_ret:
                implicit_params.append({"kind": "sret_candidate", "type": ret})
            if any("..." in param for param in params):
                implicit_params.append({"kind": "variadic"})
            rows.append({
                "name": rec["name"],
                "module_index": rec["module_index"],
                "module": rec["module"],
                "rva": rec["rva"],
                "code_size": rec["code_size"],
                "type_index": rec["type_index"],
                "returns_value": returns_value,
                "ret_type": ret,
                "params": params,
                "param_count": len(params),
                "explicit_params": params,
                "implicit_params": implicit_params,
                "sret_candidate": record_ret,
                "out_params": out_params,
                "has_out_param": bool(out_params),
                "output_channels": channels,
                "has_output_channel": bool(channels),
                "is_member": p["kind"] == "mfunction",
                "this_type": this_type,
                "this_const": this_const,
                "state_mutation_candidate": bool(p["kind"] == "mfunction" and this_const is False),
                "explicit_value_output": explicit,
                "any_value_output": explicit or bool(channels),
                "no_visible_output": (not explicit and not channels
                                      and not (p["kind"] == "mfunction" and this_const is False)),
            })

    full_keys = ("name", "module_index", "module", "rva", "code_size",
                 "type_index", "ret_type", "params", "param_count")
    full_path = os.path.join(out_dir, "sig_full.jsonl")
    class_path = os.path.join(out_dir, "sig_classified.jsonl")
    with open(full_path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps({k: row[k] for k in full_keys},
                                ensure_ascii=False) + "\n")
    with open(class_path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    total = len(rows)
    say(">> functions: %d, missing type info: %d" % (total, missing))
    for label, pred in (
        ("returns_value", lambda r: r["returns_value"]),
        ("has_out_param", lambda r: r["has_out_param"]),
        ("has_output_channel", lambda r: r["has_output_channel"]),
        ("no_visible_output", lambda r: r["no_visible_output"]),
    ):
        count = sum(1 for r in rows if pred(r))
        say("   %-20s %6d (%.1f%%)" % (label, count, 100.0 * count / total if total else 0.0))
    node_exec = [r for r in rows if r["name"].endswith("::node_geo_exec")]
    if node_exec:
        hit = sum(1 for r in node_exec if r["has_output_channel"])
        say("   node_geo_exec       %6d, channel hit %d" % (len(node_exec), hit))
    say(">> %s" % class_path)
    if args.drop_types:
        try:
            os.remove(types_path)
            say(">> removed type dump: %s" % types_path)
        except OSError as exc:
            say(">> could not remove type dump: %s" % exc)
    return None


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--pdb", default=default_pdb())
    common.add_argument("--llvm-pdbutil", default="")
    common.add_argument("--cache-dir", default="")
    common.add_argument("--libs", default=",".join(DEFAULT_LIBS),
                        help="comma separated library name fragments")
    common.add_argument("--all-modules", action="store_true")
    common.add_argument("--workers", type=int, default=4)

    ap = argparse.ArgumentParser(prog="pdb_sigs.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("extract", parents=[common])
    p.add_argument("--refresh-modules", action="store_true")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("resolve", parents=[common])
    p.add_argument("--refresh-types", action="store_true")
    p.add_argument("--drop-types", action="store_true")
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("all", parents=[common])
    p.add_argument("--refresh-modules", action="store_true")
    p.add_argument("--refresh-types", action="store_true")
    p.add_argument("--drop-types", action="store_true")
    p.set_defaults(func=None)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.cmd == "all":
        args.libs = tuple(x for x in args.libs.split(",") if x)
        err = cmd_extract(args)
        if err:
            say("ERROR: " + err)
            return 2
        err = cmd_resolve(args)
        if err:
            say("ERROR: " + err)
            return 2
        return 0
    args.libs = tuple(x for x in args.libs.split(",") if x)
    err = args.func(args)
    if err:
        say("ERROR: " + err)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
