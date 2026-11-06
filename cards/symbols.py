# -*- coding: utf-8 -*-
"""dbghelp RVA resolver and format-2 export.

Copied from verysleep/btrace_symbolize.py; the old project is left untouched.
"""

import ctypes
import json
import os
import time
from ctypes import wintypes

IMAGE_BASE = 0x140000000
SYMBOL_INFO_SIZE = 88
NAME_CHARS = 2048


class SYMBOL_INFOW(ctypes.Structure):
    _fields_ = [
        ("SizeOfStruct", wintypes.ULONG),
        ("TypeIndex", wintypes.ULONG),
        ("Reserved", ctypes.c_ulonglong * 2),
        ("Index", wintypes.ULONG),
        ("Size", wintypes.ULONG),
        ("ModBase", ctypes.c_ulonglong),
        ("Flags", wintypes.ULONG),
        ("Value", ctypes.c_ulonglong),
        ("Address", ctypes.c_ulonglong),
        ("Register", wintypes.ULONG),
        ("Scope", wintypes.ULONG),
        ("Tag", wintypes.ULONG),
        ("NameLen", wintypes.ULONG),
        ("MaxNameLen", wintypes.ULONG),
        ("Name", ctypes.c_wchar * NAME_CHARS),
    ]


class IMAGEHLP_LINE64(ctypes.Structure):
    _fields_ = [
        ("SizeOfStruct", wintypes.DWORD),
        ("Key", ctypes.c_void_p),
        ("LineNumber", wintypes.DWORD),
        ("FileName", ctypes.c_char_p),
        ("Address", ctypes.c_ulonglong),
    ]


dbghelp = ctypes.WinDLL("dbghelp.dll")
kernel32 = ctypes.WinDLL("kernel32.dll")

SYMOPT_UNDNAME = 0x00000002
SYMOPT_LOAD_LINES = 0x00000010

dbghelp.SymSetOptions.argtypes = [wintypes.DWORD]
dbghelp.SymSetOptions.restype = wintypes.DWORD
dbghelp.SymInitializeW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.BOOL]
dbghelp.SymInitializeW.restype = wintypes.BOOL
dbghelp.SymLoadModuleExW.argtypes = [
    wintypes.HANDLE, wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPCWSTR,
    ctypes.c_ulonglong, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
dbghelp.SymLoadModuleExW.restype = ctypes.c_ulonglong
dbghelp.SymFromAddrW.argtypes = [
    wintypes.HANDLE, ctypes.c_ulonglong, ctypes.POINTER(ctypes.c_ulonglong),
    ctypes.POINTER(SYMBOL_INFOW)]
dbghelp.SymFromAddrW.restype = wintypes.BOOL
dbghelp.SymGetLineFromAddr64.argtypes = [
    wintypes.HANDLE, ctypes.c_ulonglong, ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(IMAGEHLP_LINE64)]
dbghelp.SymGetLineFromAddr64.restype = wintypes.BOOL

H = kernel32.GetCurrentProcess()
MOD_BASE = None
_LOADED = None


def load(exe):
    global MOD_BASE, _LOADED
    key = os.path.normpath(exe)
    if _LOADED == key and MOD_BASE:
        return
    if _LOADED is not None:
        raise RuntimeError("symbolizer already loaded for %s" % _LOADED)
    dbghelp.SymSetOptions(SYMOPT_UNDNAME | SYMOPT_LOAD_LINES)
    if not dbghelp.SymInitializeW(H, os.path.dirname(exe), False):
        raise RuntimeError("SymInitialize failed")
    MOD_BASE = dbghelp.SymLoadModuleExW(H, None, exe, None, IMAGE_BASE, 0, None, 0)
    if not MOD_BASE:
        raise RuntimeError("SymLoadModuleEx failed (missing PDB?)")
    _LOADED = key


def _sym_from_va(va):
    disp = ctypes.c_ulonglong(0)
    sym = SYMBOL_INFOW()
    sym.SizeOfStruct = SYMBOL_INFO_SIZE
    sym.MaxNameLen = NAME_CHARS
    if not dbghelp.SymFromAddrW(H, va, ctypes.byref(disp), ctypes.byref(sym)):
        return None, 0
    return sym.Name, sym.Address


def _line_from_va(va):
    disp = wintypes.DWORD(0)
    ln = IMAGEHLP_LINE64()
    ln.SizeOfStruct = ctypes.sizeof(IMAGEHLP_LINE64)
    if not dbghelp.SymGetLineFromAddr64(H, va, ctypes.byref(disp), ctypes.byref(ln)):
        return "", 0
    f = ln.FileName.decode("utf-8", "replace") if ln.FileName else ""
    return f, ln.LineNumber


def resolve(rva):
    va = MOD_BASE + rva
    name, fn_va = _sym_from_va(va)
    if not name:
        return None, "", 0
    f, ln = _line_from_va(fn_va)
    return name, f, ln


def resolve_with_size(rva):
    """Like resolve(), plus the function's code size in bytes from the PDB."""
    va = MOD_BASE + rva
    disp = ctypes.c_ulonglong(0)
    sym = SYMBOL_INFOW()
    sym.SizeOfStruct = SYMBOL_INFO_SIZE
    sym.MaxNameLen = NAME_CHARS
    if not dbghelp.SymFromAddrW(H, va, ctypes.byref(disp), ctypes.byref(sym)):
        return None, "", 0, 0
    f, ln = _line_from_va(sym.Address)
    return sym.Name, f, ln, int(sym.Size)


def name_of(rva):
    """Exact symbol name at rva, without the line lookup."""
    va = MOD_BASE + rva
    name, fn_va = _sym_from_va(va)
    if not name or fn_va != va:
        return ""
    return name


def address_of(name):
    """RVA of a symbol by name (used to identify instrumentation hooks)."""
    fn = dbghelp.SymFromNameW
    fn.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, ctypes.POINTER(SYMBOL_INFOW)]
    fn.restype = wintypes.BOOL
    sym = SYMBOL_INFOW()
    sym.SizeOfStruct = SYMBOL_INFO_SIZE
    sym.MaxNameLen = NAME_CHARS
    if not fn(H, name, ctypes.byref(sym)):
        return None
    return int(sym.Address) - int(MOD_BASE)


def norm_path(f):
    if not f:
        return ""
    q = f.replace("\\", "/")
    mark = "/blender-4.5.0/"
    i = q.lower().find(mark)
    if i >= 0:
        return q[i + len(mark):]
    return q


def is_project(f):
    if not f:
        return True
    low = f.replace("\\", "/").lower()
    for bad in ("windows kits", "/tools/msvc/", "/lib/windows", "program files"):
        if bad in low:
            return False
    return True


def module_of(f):
    if not f:
        return ""
    path = norm_path(f)
    if not path.startswith("/"):
        path = "/" + path
    low = path.lower()
    for root in ("/source/blender/", "/intern/", "/source/", "/extern/", "/lib/"):
        i = low.find(root)
        if i >= 0:
            return path[i + len(root):].split("/")[0]
    return ""


def read_u64s(path):
    raw = open(path, "rb").read()
    return [int.from_bytes(raw[i:i + 8], "little") for i in range(0, len(raw), 8)]


def _export_function(name, f, ln, module, rva, mod_base, with_addresses):
    row = {"name": name, "file": f, "line": ln, "module": module}
    if with_addresses:
        row["rva"] = rva
        row["va"] = mod_base + rva
    return row


def _export_edge(an, af, al, cn, cf, cl, cr, ce, with_addresses):
    row = {
        "caller": an or "(unknown)", "callee": cn or "?",
        "caller_file": af, "caller_line": al,
        "callee_file": cf, "callee_line": cl,
    }
    if with_addresses:
        row["caller_rva"] = cr
        row["callee_rva"] = ce
        row["caller_va"] = MOD_BASE + cr
        row["callee_va"] = MOD_BASE + ce
    return row


def build_export(funcs, edge_rows, meta, has_edges, with_addresses=False):
    files, file_idx = [], {}

    def add_file(path):
        p = norm_path(path)
        if not p:
            return None
        if p not in file_idx:
            file_idx[p] = len(files)
            files.append(p)
        return file_idx[p]

    symbols, sym_idx = [], {}

    def sym_key(name, f, line, addr=None):
        p = norm_path(f)
        if with_addresses and addr and addr.get("rva") is not None:
            return ("rva", int(addr["rva"]))
        return ("sym", name, p, int(line or 0))

    def add_symbol(name, f, line, module, addr=None):
        p = norm_path(f)
        if not p:
            return None
        key = sym_key(name, p, line, addr)
        if key in sym_idx:
            return sym_idx[key]
        row = {"name": name, "file": add_file(p), "line": int(line or 0),
               "module": module or ""}
        if with_addresses and addr:
            row.update(addr)
        sym_idx[key] = len(symbols)
        symbols.append(row)
        return sym_idx[key]

    dropped_funcs = 0
    for d in funcs:
        addr = None
        if with_addresses and "rva" in d:
            addr = {"rva": d["rva"], "va": d["va"]}
        if add_symbol(d["name"], d["file"], d["line"], d["module"],
                      addr) is None:
            dropped_funcs += 1
    project_symbols = len(symbols)

    dropped_edges = 0
    valid_edges = []
    for e in edge_rows:
        if not norm_path(e["caller_file"]) or not norm_path(e["callee_file"]):
            dropped_edges += 1
            continue
        caller_addr = callee_addr = None
        if with_addresses and "caller_rva" in e:
            caller_addr = {"rva": e["caller_rva"], "va": e["caller_va"]}
            callee_addr = {"rva": e["callee_rva"], "va": e["callee_va"]}
        add_symbol(e["caller"], e["caller_file"], e["caller_line"],
                   module_of(e["caller_file"]), caller_addr)
        add_symbol(e["callee"], e["callee_file"], e["callee_line"],
                   module_of(e["callee_file"]), callee_addr)
        valid_edges.append(e)

    out = {
        "meta": dict(
            meta,
            generated=time.strftime("%Y-%m-%d %H:%M:%S"),
            file_count=len(files),
            symbol_count=len(symbols),
            project_symbols=project_symbols,
            dropped_no_file_functions=dropped_funcs,
            dropped_no_file_edges=dropped_edges,
        ),
        "files": files,
        "functions": symbols,
    }

    if has_edges:
        edges = []
        for e in valid_edges:
            caller_addr = callee_addr = None
            if with_addresses and "caller_rva" in e:
                caller_addr = {"rva": e["caller_rva"]}
                callee_addr = {"rva": e["callee_rva"]}
            ck = sym_key(e["caller"], e["caller_file"], e["caller_line"],
                         caller_addr)
            ek = sym_key(e["callee"], e["callee_file"], e["callee_line"],
                         callee_addr)
            row = {"caller": sym_idx[ck], "callee": sym_idx[ek]}
            if with_addresses:
                if "caller_rva" in e:
                    row["caller_rva"] = e["caller_rva"]
                if "callee_rva" in e:
                    row["callee_rva"] = e["callee_rva"]
            edges.append(row)
        out["edges"] = edges
        out["meta"]["edge_count"] = len(edges)

    return out


def dumps_export(obj):
    body = []
    if "meta" in obj:
        m = json.dumps(obj["meta"], ensure_ascii=False, indent=2).replace("\n", "\n  ")
        body.append('  "meta": ' + m)
    for key in ("files", "functions", "edges"):
        if key not in obj:
            continue
        items = obj[key]
        if items:
            rows = ",\n".join("    " + json.dumps(x, ensure_ascii=False) for x in items)
            body.append('  "%s": [\n%s\n  ]' % (key, rows))
        else:
            body.append('  "%s": []' % key)
    for key, val in obj.items():
        if key in ("meta", "files", "functions", "edges"):
            continue
        v = json.dumps(val, ensure_ascii=False, indent=2).replace("\n", "\n  ")
        body.append('  "%s": %s' % (key, v))
    return "{\n" + ",\n".join(body) + "\n}\n"


def symbolize(functions_bin, edges_bin, exe, with_addresses=False):
    load(exe)
    rvas = read_u64s(functions_bin)

    funcs = []
    for value in rvas:
        rva = value - 1
        name, f, ln = resolve(rva)
        if not name:
            continue
        if not is_project(f):
            continue
        funcs.append(_export_function(
            name, f, ln, module_of(f), rva, MOD_BASE, with_addresses))
    funcs.sort(key=lambda d: (d["file"], d["line"], d["name"]))

    meta = {
        "exe": exe.replace("\\", "/"),
        "rva_file": os.path.abspath(functions_bin).replace("\\", "/"),
        "total_rvas": len(rvas),
        "project_functions": len(funcs),
    }

    edges = []
    has_edges = bool(edges_bin and os.path.exists(edges_bin))
    if has_edges:
        for key in read_u64s(edges_bin):
            cr = key >> 32
            ce = key & 0xFFFFFFFF
            cn, cf, cl = resolve(ce) if ce else (None, "", 0)
            an, af, al = resolve(cr) if cr else (None, "", 0)
            edges.append(_export_edge(an, af, al, cn, cf, cl, cr, ce, with_addresses))
        edges.sort(key=lambda d: (d["caller"], d["callee"]))

    return build_export(funcs, edges, meta, has_edges, with_addresses)
