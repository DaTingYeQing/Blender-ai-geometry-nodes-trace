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

from capstone import Cs, CS_ARCH_X86, CS_GRP_JUMP, CS_MODE_64, x86
from capstone.x86 import X86_INS_CALL, X86_INS_JMP, X86_INS_RET, X86_OP_IMM

from . import symbols
from .base import TranslationCard

MAX_FUNC_BYTES = 256 * 1024

FP_SIMD_GROUPS = frozenset((
    x86.X86_GRP_FPU, x86.X86_GRP_MMX,
    x86.X86_GRP_SSE1, x86.X86_GRP_SSE2, x86.X86_GRP_SSE3,
    x86.X86_GRP_SSSE3, x86.X86_GRP_SSE41, x86.X86_GRP_SSE42,
    x86.X86_GRP_SSE4A, x86.X86_GRP_AVX, x86.X86_GRP_AVX2,
    x86.X86_GRP_AVX512, x86.X86_GRP_FMA, x86.X86_GRP_FMA4,
    x86.X86_GRP_XOP, x86.X86_GRP_3DNOW, x86.X86_GRP_F16C,
    x86.X86_GRP_PCLMUL, x86.X86_GRP_AES, x86.X86_GRP_SHA,
))

RUNTIME_NAME_TOKENS = (
    "__chkstk", "__security_check_cookie", "__security_init_cookie",
    "__report_gsfailure", "__report_rangecheckfailure", "__gshandlercheck",
    "__cxxframehandler", "_cxxtthrowexception", "__std_terminate",
    "__std_call_terminate", "_invoke_watson", "_invalid_parameter",
    "__fastfail", "__unhandled_exception", "__raise_exception",
    "__current_exception", "_seh_filter", "_except_handler",
    "guard_dispatch_icall",
)

GLOBAL_SECTION_NAMES = (".rdata", ".data", ".tls")


def _is_runtime_name(name):
    low = name.lower()
    return any(token in low for token in RUNTIME_NAME_TOKENS)


def _section_name(sections, rva):
    for name, va, vsize, raw_size, _raw_ptr in sections:
        if va <= rva < va + max(vsize, raw_size):
            return name
    return ""


def _count_switch_tables(decoded):
    count = 0
    for index, insn in enumerate(decoded):
        if insn.id != X86_INS_JMP or not insn.operands:
            continue
        operand = insn.operands[0]
        if operand.type == X86_OP_IMM:
            continue
        indexed = (operand.type == x86.X86_OP_MEM and
                   operand.mem.index != 0 and operand.mem.scale > 1)
        window = decoded[max(0, index - 10):index]
        if not indexed:
            indexed = any(
                op.type == x86.X86_OP_MEM and op.mem.index != 0 and
                op.mem.scale > 1
                for prev in window for op in prev.operands)
        if not indexed:
            continue
        guarded = any(
            prev.mnemonic in ("cmp", "test") or
            (prev.group(CS_GRP_JUMP) and prev.id != X86_INS_JMP)
            for prev in window)
        if guarded:
            count += 1
    return count


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

        hook_rvas = {}
        for hook_kind, hook_name in (("enter", "__cyg_profile_func_enter"),
                                     ("exit", "__cyg_profile_func_exit")):
            hook_rva = symbols.address_of(hook_name)
            if hook_rva is not None:
                hook_rvas[hook_rva] = hook_kind

        md = Cs(CS_ARCH_X86, CS_MODE_64)
        md.detail = True

        runtime_cache = {}
        section_cache = {}
        functions = []
        for value in symbols.read_u64s(ctx.raw("functions")):
            rva = value - 1
            name, path, line, size = symbols.resolve_with_size(rva)
            if not name:
                continue

            start_va = image_base + rva
            instructions = calls = hook_calls = 0
            hook_enter = hook_exit = 0
            direct_calls = indirect_calls = runtime_calls = 0
            jumps = conditional_jumps = rets = 0
            back_edges = push_count = stack_frame_bytes = 0
            fp_simd_insns = lock_insns = 0
            rip_relative_refs = global_refs = 0
            first = last = ""
            decoded = []
            decoded_hook = []
            distinct_targets = set()
            code_len = 0

            if size > 0:
                offset, available = _map_rva(sections, rva)
                if offset is not None:
                    code = data[offset:offset + min(size, available, MAX_FUNC_BYTES)]
                    code_len = len(code)
                    for insn in md.disasm(code, start_va):
                        instructions += 1
                        decoded.append(insn)
                        if not first:
                            first = insn.mnemonic
                        last = insn.mnemonic

                        is_hook = False
                        if insn.id == X86_INS_CALL:
                            calls += 1
                            target = None
                            if insn.operands and insn.operands[0].type == X86_OP_IMM:
                                target = insn.operands[0].imm - image_base
                                direct_calls += 1
                            else:
                                indirect_calls += 1
                            if target in hook_rvas:
                                is_hook = True
                                hook_calls += 1
                                if hook_rvas[target] == "enter":
                                    hook_enter += 1
                                else:
                                    hook_exit += 1
                            elif target is not None:
                                distinct_targets.add(target)
                                if target not in runtime_cache:
                                    runtime_cache[target] = _is_runtime_name(
                                        symbols.name_of(target))
                                if runtime_cache[target]:
                                    runtime_calls += 1
                        decoded_hook.append(is_hook)

                        if insn.group(CS_GRP_JUMP):
                            jumps += 1
                            if insn.id != X86_INS_JMP:
                                conditional_jumps += 1
                            if insn.operands and insn.operands[0].type == X86_OP_IMM:
                                target_va = insn.operands[0].imm
                                if start_va <= target_va <= insn.address:
                                    back_edges += 1
                        if insn.id == X86_INS_RET:
                            rets += 1
                        if insn.id == x86.X86_INS_PUSH:
                            push_count += 1
                        if insn.id == x86.X86_INS_SUB and len(insn.operands) >= 2:
                            if (insn.operands[0].type == x86.X86_OP_REG and
                                    insn.operands[0].reg == x86.X86_REG_RSP and
                                    insn.operands[1].type == x86.X86_OP_IMM):
                                stack_frame_bytes += insn.operands[1].imm
                        if any(group in FP_SIMD_GROUPS for group in insn.groups):
                            fp_simd_insns += 1
                        if (x86.X86_PREFIX_LOCK in insn.prefix or
                                (insn.id == x86.X86_INS_XCHG and
                                 any(op.type == x86.X86_OP_MEM
                                     for op in insn.operands))):
                            lock_insns += 1

                        rip_hit = False
                        for operand in insn.operands:
                            if (operand.type != x86.X86_OP_MEM or
                                    operand.mem.base != x86.X86_REG_RIP):
                                continue
                            rip_hit = True
                            target_rva = (
                                insn.address + insn.size +
                                operand.mem.disp - image_base)
                            if target_rva not in section_cache:
                                section_cache[target_rva] = _section_name(
                                    sections, target_rva)
                            if section_cache[target_rva] in GLOBAL_SECTION_NAMES:
                                global_refs += 1
                        if rip_hit:
                            rip_relative_refs += 1

            decoded_bytes = sum(insn.size for insn in decoded)
            decode_error = size > 0 and decoded_bytes < size

            padding_bytes = 0
            for insn in reversed(decoded):
                if insn.id in (x86.X86_INS_NOP, x86.X86_INS_INT3):
                    padding_bytes += insn.size
                else:
                    break
            trailing_pad = padding_bytes > 0

            basic_blocks = 0
            if decoded:
                end_va = start_va + code_len
                addresses = {insn.address for insn in decoded}
                block_starts = {decoded[0].address}
                for insn in decoded:
                    if not insn.group(CS_GRP_JUMP):
                        continue
                    if insn.operands and insn.operands[0].type == X86_OP_IMM:
                        target_va = insn.operands[0].imm
                        if start_va <= target_va < end_va:
                            block_starts.add(target_va)
                    if insn.id != X86_INS_JMP:
                        next_va = insn.address + insn.size
                        if next_va < end_va:
                            block_starts.add(next_va)
                basic_blocks = len(block_starts & addresses)
                if basic_blocks == 0:
                    basic_blocks = 1

            switch_tables = _count_switch_tables(decoded)

            tail_target_kind = "none"
            tail_jump = None
            if decoded:
                if decoded[-1].id == X86_INS_JMP:
                    tail_jump = decoded[-1]
                elif decoded[0].id == X86_INS_JMP:
                    tail_jump = decoded[0]
            if tail_jump is not None:
                if tail_jump.operands and tail_jump.operands[0].type == X86_OP_IMM:
                    target_va = tail_jump.operands[0].imm
                    if start_va <= target_va < start_va + size:
                        tail_target_kind = "direct_local"
                    else:
                        tail_target_kind = "direct_external"
                else:
                    tail_target_kind = "indirect"

            first_after_hook = first
            for index, is_hook in enumerate(decoded_hook):
                if not is_hook:
                    continue
                next_index = index + 1
                while next_index < len(decoded) and decoded_hook[next_index]:
                    next_index += 1
                if next_index < len(decoded):
                    first_after_hook = decoded[next_index].mnemonic
                break

            hook_balance = {
                "enter": hook_enter,
                "exit": hook_exit,
                "balanced": hook_enter == hook_exit and hook_enter > 0,
            }

            real_calls = calls - hook_calls
            logic_calls = real_calls - runtime_calls
            tiny = 0 < size <= 128
            branchless = conditional_jumps == 0
            forwarder_candidate = (
                tiny and branchless and real_calls == 1 and rets >= 1)
            # A local jmp is a loop/merge edge, not a tail call.
            tail_thunk = tail_target_kind == "direct_external"

            functions.append({
                "rva": rva,
                "name": name,
                "file": symbols.norm_path(path),
                "line": line,
                "module": symbols.module_of(path),
                "disasm": {
                    "size": size,
                    "instructions": instructions,
                    "decoded_bytes": decoded_bytes,
                    "decode_error": decode_error,
                    "padding_bytes": padding_bytes,
                    "trailing_pad": trailing_pad,
                    "calls": calls,
                    "direct_calls": direct_calls,
                    "indirect_calls": indirect_calls,
                    "hook_calls": hook_calls,
                    "hook_balance": hook_balance,
                    "runtime_calls": runtime_calls,
                    "real_calls": real_calls,
                    "logic_calls": logic_calls,
                    "distinct_call_targets": len(distinct_targets),
                    "jumps": jumps,
                    "conditional_jumps": conditional_jumps,
                    "basic_blocks": basic_blocks,
                    "back_edges": back_edges,
                    "switch_tables": switch_tables,
                    "rets": rets,
                    "stack_frame_bytes": stack_frame_bytes,
                    "push_count": push_count,
                    "rip_relative_refs": rip_relative_refs,
                    "global_refs": global_refs,
                    "fp_simd_insns": fp_simd_insns,
                    "lock_insns": lock_insns,
                    "first": first,
                    "first_after_hook": first_after_hook,
                    "last": last,
                    "tail_target_kind": tail_target_kind,
                    "tiny": tiny,
                    "branchless": branchless,
                    "forwarder_candidate": forwarder_candidate,
                    "tail_thunk": tail_thunk,
                },
            })

        functions.sort(key=lambda item: (item["disasm"]["size"], item["name"]))
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
                "max_func_bytes": MAX_FUNC_BYTES,
                "note": ("size/instructions include instrumentation and coverage; "
                         "real_calls excludes __cyg_profile_func_* calls; "
                         "decoded_bytes < size means the disassembly was truncated"),
                "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "functions": functions,
        }

        path = ctx.publish("disasm")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
            fh.write("\n")

        return {
            "name": self.name,
            "functions": len(functions),
            "candidates": report["meta"]["candidates"],
            "thunks": report["meta"]["thunks"],
        }
