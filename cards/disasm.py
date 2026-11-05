# -*- coding: utf-8 -*-
"""disasm card: functions.bin + exe/PDB -> disasm.json.

Static per-function metrics from the linked binary:
code size (PDB), instruction count, calls, branches, returns and a few
conservative wrapper/thunk flags. Instrumentation calls are identified and
excluded from `real_calls`; instruction counts still include coverage and
instrumentation instructions.
"""

import json
import struct
import time

from capstone import Cs, CS_ARCH_X86, CS_GRP_JUMP, CS_MODE_64
from capstone.x86 import X86_INS_CALL, X86_INS_JMP, X86_INS_RET, X86_OP_IMM

from . import symbols
from .base import TranslationCard

MAX_FUNC_BYTES = 256 * 1024

SYMBOL_KINDS = ("hook", "global_init", "thunk", "deleting_destructor", "normal")


def _classify_symbol(name):
    """Apply the high-confidence rules from docs/筛选.md 5.1."""
    lower = name.lower()
    tags = []
    kind = "normal"

    if "__cyg_profile_func_enter" in lower or "__cyg_profile_func_exit" in lower:
        tags.append("hook")
        kind = "hook"

    if "dynamic initializer" in lower:
        tags.append("dynamic_initializer")
        if kind == "normal":
            kind = "global_init"
    if "dynamic atexit destructor" in lower:
        tags.append("dynamic_atexit_destructor")
        if kind == "normal":
            kind = "global_init"
    if "_global__sub_i" in lower:
        tags.append("global_sub_i")
        if kind == "normal":
            kind = "global_init"
    if "__cxx_global_var_init" in lower:
        tags.append("cxx_global_var_init")
        if kind == "normal":
            kind = "global_init"

    if "[thunk]:" in lower:
        tags.append("thunk")
    if "vcall" in lower:
        tags.append("vcall")
    if "adjustor" in lower:
        tags.append("adjustor")
    if "non-virtual thunk to" in lower:
        tags.append("non_virtual_thunk")
    elif "virtual thunk to" in lower:
        tags.append("virtual_thunk")
    if any(t in tags for t in ("thunk", "vcall", "adjustor",
                               "non_virtual_thunk", "virtual_thunk")):
        if kind == "normal":
            kind = "thunk"

    if "vector deleting destructor" in lower:
        tags.append("vector_deleting_destructor")
        tags.append("deleting_destructor")
        if kind == "normal":
            kind = "deleting_destructor"
    elif "deleting destructor" in lower:
        tags.append("deleting_destructor")
        if kind == "normal":
            kind = "deleting_destructor"

    return {
        "kind": kind,
        "tags": tags,
    }


def _pe_sections(data):
    if data[:2] != b"MZ":
        raise RuntimeError("not a PE file")
    lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[lfanew:lfanew + 4] != b"PE\0\0":
        raise RuntimeError("missing PE signature")
    coff = lfanew + 4
    count = struct.unpack_from("<H", data, coff + 2)[0]
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic == 0x20B:       # PE32+
        image_base = struct.unpack_from("<Q", data, opt + 24)[0]
    elif magic == 0x10B:     # PE32
        image_base = struct.unpack_from("<I", data, opt + 28)[0]
    else:
        raise RuntimeError("unknown PE optional header magic 0x%X" % magic)

    sections = []
    table = opt + opt_size
    for i in range(count):
        off = table + i * 40
        name = data[off:off + 8].rstrip(b"\0").decode("latin-1")
        vsize, va, raw_size, raw_ptr = struct.unpack_from("<IIII", data, off + 8)
        sections.append((name, va, vsize, raw_size, raw_ptr))
    return image_base, sections


def _map_rva(sections, rva):
    for _name, va, vsize, raw_size, raw_ptr in sections:
        extent = max(vsize, raw_size)
        if va <= rva < va + extent:
            return raw_ptr + (rva - va), va + extent - rva
    return None, 0


class DisasmCard(TranslationCard):
    name = "disasm"
    needs = ("raw:functions",)

    def build(self, ctx):
        data = open(ctx.blender, "rb").read()
        image_base, sections = _pe_sections(data)
        symbols.load(ctx.blender)

        hooks = set()
        for hook_name in ("__cyg_profile_func_enter", "__cyg_profile_func_exit"):
            rva = symbols.address_of(hook_name)
            if rva is not None:
                hooks.add(rva)

        md = Cs(CS_ARCH_X86, CS_MODE_64)
        md.detail = True

        functions = []
        for value in symbols.read_u64s(ctx.raw("functions")):
            rva = value - 1
            name, path, line, size = symbols.resolve_with_size(rva)
            if not name:
                continue

            instructions = calls = hook_calls = 0
            jumps = conditional_jumps = rets = 0
            first = last = ""
            if size > 0:
                offset, available = _map_rva(sections, rva)
                if offset is not None:
                    code = data[offset:offset + min(size, available, MAX_FUNC_BYTES)]
                    for insn in md.disasm(code, image_base + rva):
                        instructions += 1
                        if not first:
                            first = insn.mnemonic
                        last = insn.mnemonic
                        if insn.id == X86_INS_CALL:
                            calls += 1
                            target = None
                            if insn.operands and insn.operands[0].type == X86_OP_IMM:
                                target = insn.operands[0].imm - image_base
                            if target in hooks:
                                hook_calls += 1
                        if insn.group(CS_GRP_JUMP):
                            jumps += 1
                            if insn.id != X86_INS_JMP:
                                conditional_jumps += 1
                        if insn.id == X86_INS_RET:
                            rets += 1

            real_calls = calls - hook_calls
            tiny = 0 < size <= 128
            branchless = conditional_jumps == 0
            forwarder_candidate = (
                tiny and branchless and real_calls == 1 and rets >= 1)
            tail_thunk = first == "jmp" or (last == "jmp" and real_calls == 0)

            functions.append({
                "name": name,
                "file": symbols.norm_path(path),
                "line": line,
                "module": symbols.module_of(path),
                "disasm": {
                    "size": size,
                    "instructions": instructions,
                    "calls": calls,
                    "hook_calls": hook_calls,
                    "real_calls": real_calls,
                    "jumps": jumps,
                    "conditional_jumps": conditional_jumps,
                    "rets": rets,
                    "first": first,
                    "last": last,
                    "tiny": tiny,
                    "branchless": branchless,
                    "forwarder_candidate": forwarder_candidate,
                    "tail_thunk": tail_thunk,
                },
                "symbol": _classify_symbol(name),
            })

        functions.sort(key=lambda item: (item["disasm"]["size"], item["name"]))
        kind_counts = {kind: 0 for kind in SYMBOL_KINDS}
        for item in functions:
            kind_counts[item["symbol"]["kind"]] += 1
        report = {
            "meta": {
                "blender": ctx.blender.replace("\\", "/"),
                "image_base": image_base,
                "functions": len(functions),
                "candidates": sum(
                    1 for f in functions
                    if f["disasm"]["forwarder_candidate"]),
                "thunks": sum(
                    1 for f in functions if f["disasm"]["tail_thunk"]),
                "symbol_kinds": kind_counts,
                "max_func_bytes": MAX_FUNC_BYTES,
                "note": ("size/instructions include instrumentation and coverage; "
                         "real_calls excludes __cyg_profile_func_* calls"),
                "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "functions": functions,
        }

        path = ctx.out("disasm.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
            fh.write("\n")

        return {
            "name": self.name,
            "functions": len(functions),
            "candidates": report["meta"]["candidates"],
            "thunks": report["meta"]["thunks"],
            "output": "disasm.json",
        }
