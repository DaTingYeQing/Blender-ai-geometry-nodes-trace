; bltrace_penter.asm -- MSVC /Gh and /GH entry/exit hooks.
;
; Reconstructed 2026-11-03 from bltrace_penter.obj.
;
; /Gh emits `call _penter` at function entry with no arguments and no
; shadow space reserved for the hook. /GH emits `call _pexit` before each
; return. Both hooks must preserve every volatile register and flag, keep
; the stack 16-byte aligned, and pass the address directly above the hook
; call (the caller's return address) to the C side.

OPTION CASEMAP:NONE

EXTERN bltrace_enter:PROC
EXTERN bltrace_exit:PROC

_TEXT SEGMENT

PUBLIC _penter

_penter PROC
    pushfq
    push    rax
    push    rcx
    push    rdx
    push    r8
    push    r9
    push    r10
    push    r11
    push    r12
    sub     rsp, 60h
    movups  XMMWORD PTR [rsp], xmm0
    movups  XMMWORD PTR [rsp+10h], xmm1
    movups  XMMWORD PTR [rsp+20h], xmm2
    movups  XMMWORD PTR [rsp+30h], xmm3
    movups  XMMWORD PTR [rsp+40h], xmm4
    movups  XMMWORD PTR [rsp+50h], xmm5
    mov     r12, rsp
    and     rsp, -10h
    sub     rsp, 20h
    mov     rcx, QWORD PTR [r12+0A8h]
    call    bltrace_enter
    mov     rsp, r12
    movups  xmm0, XMMWORD PTR [rsp]
    movups  xmm1, XMMWORD PTR [rsp+10h]
    movups  xmm2, XMMWORD PTR [rsp+20h]
    movups  xmm3, XMMWORD PTR [rsp+30h]
    movups  xmm4, XMMWORD PTR [rsp+40h]
    movups  xmm5, XMMWORD PTR [rsp+50h]
    add     rsp, 60h
    pop     r12
    pop     r11
    pop     r10
    pop     r9
    pop     r8
    pop     rdx
    pop     rcx
    pop     rax
    popfq
    ret
_penter ENDP

PUBLIC _pexit

_pexit PROC
    pushfq
    push    rax
    push    rcx
    push    rdx
    push    r8
    push    r9
    push    r10
    push    r11
    push    r12
    sub     rsp, 60h
    movups  XMMWORD PTR [rsp], xmm0
    movups  XMMWORD PTR [rsp+10h], xmm1
    movups  XMMWORD PTR [rsp+20h], xmm2
    movups  XMMWORD PTR [rsp+30h], xmm3
    movups  XMMWORD PTR [rsp+40h], xmm4
    movups  XMMWORD PTR [rsp+50h], xmm5
    mov     r12, rsp
    and     rsp, -10h
    sub     rsp, 20h
    mov     rcx, QWORD PTR [r12+0A8h]
    call    bltrace_exit
    mov     rsp, r12
    movups  xmm0, XMMWORD PTR [rsp]
    movups  xmm1, XMMWORD PTR [rsp+10h]
    movups  xmm2, XMMWORD PTR [rsp+20h]
    movups  xmm3, XMMWORD PTR [rsp+30h]
    movups  xmm4, XMMWORD PTR [rsp+40h]
    movups  xmm5, XMMWORD PTR [rsp+50h]
    add     rsp, 60h
    pop     r12
    pop     r11
    pop     r10
    pop     r9
    pop     r8
    pop     rdx
    pop     rcx
    pop     rax
    popfq
    ret
_pexit ENDP

_TEXT ENDS

END