/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * trampoline.S -- the chain trampolines for the six Hook sites (see og_hook_sites.h).
 *
 * Each is the `orig_*` target a native call is chained through: it re-runs the
 * DISPLACED bytes of its hook site and then TAIL-JUMPS to `resume` (va+displaced_len),
 * so the original title XID code continues as if the 5-byte E9 had never been
 * written. All targets are absolute title VAs held as IMMEDIATE CONSTANTS -- there
 * is no module-relative relocation and no stale displaced PC-relative offset.
 *
 * The one displaced PC-relative instruction (XInputClose's `call rel32` to
 * XID_fCloseDevice @0x41493E) is RE-ENCODED as an absolute-constant + indirect
 * call: `movl $0x41493E,%eax; call *%eax`. It CANNOT retain the old +0x0ECD
 * displacement (that offset is only valid 5 bytes from 0x413A6C). The same holds
 * for XInputGetState's `call dword ptr [0x41b700]` -- rebuilt as load-abs + call.
 *
 * Register contract per site (EDX is the resume-bounce scratch so EAX -- the value
 * each hook's displaced span or its call leaves in EAX for `resume` -- survives):
 */
    .code32
    .text

/* move the EAX-preserving resume bounce here so every label is explicit */

/* XGetDeviceChanges  displaced: 55 8B EC 56 8B 75 08  (esi=[ebp+8], ebp frame) */
    .globl ogx_chain_getdevicechanges
    .type  ogx_chain_getdevicechanges,@function
ogx_chain_getdevicechanges:
    pushl   %ebp
    movl    %esp, %ebp
    pushl   %esi
    movl    8(%ebp), %esi
    movl    $0x004139AC, %edx         /* resume */
    jmp     *%edx
    .size ogx_chain_getdevicechanges, .-ogx_chain_getdevicechanges

/* XInputOpen  displaced: 55 8B EC 51 8B 4D 08  (ecx=[ebp+8], ebp frame) */
    .globl ogx_chain_inputopen
    .type  ogx_chain_inputopen,@function
ogx_chain_inputopen:
    pushl   %ebp
    movl    %esp, %ebp
    pushl   %ecx
    movl    8(%ebp), %ecx
    movl    $0x00413A19, %edx         /* resume */
    jmp     *%edx
    .size ogx_chain_inputopen, .-ogx_chain_inputopen

/* XInputClose  displaced: 8B 4C 24 04 E8 CD 0E 00 00
 *   mov ecx,[esp+4] ; call 0x41493E (RE-ENCODED: no stale +0x0ECD rel32) */
    .globl ogx_chain_inputclose
    .type  ogx_chain_inputclose,@function
ogx_chain_inputclose:
    movl    4(%esp), %ecx             /* handle */
    movl    $0x0041493E, %eax         /* XID_fCloseDevice (absolute) */
    call    *%eax
    movl    $0x00413A71, %edx         /* resume (ret 4) */
    jmp     *%edx
    .size ogx_chain_inputclose, .-ogx_chain_inputclose

/* XInputGetCapabilities  displaced: 55 8B EC 83 EC 48 */
    .globl ogx_chain_getcaps
    .type  ogx_chain_getcaps,@function
ogx_chain_getcaps:
    pushl   %ebp
    movl    %esp, %ebp
    subl    $0x48, %esp
    movl    $0x00413A7A, %edx         /* resume */
    jmp     *%edx
    .size ogx_chain_getcaps, .-ogx_chain_getcaps

/* XInputGetState  displaced: 53 56 33 DB FF 15 00 B7 41 00
 *   push ebx; push esi; xor ebx,ebx; call dword ptr [0x41b700] (rebuilt indirect) */
    .globl ogx_chain_getstate
    .type  ogx_chain_getstate,@function
ogx_chain_getstate:
    pushl   %ebx
    pushl   %esi
    xorl    %ebx, %ebx
    movl    $0x0041B700, %eax         /* &lock-slot */
    movl    (%eax), %eax              /* the fn ptr stored there */
    call    *%eax
    movl    $0x00413C56, %edx         /* resume (do NOT clobber eax=lock return) */
    jmp     *%edx
    .size ogx_chain_getstate, .-ogx_chain_getstate

/* XInputSetState  displaced: 8B 4C 24 04 8D 81 A3 00 00 00
 *   mov ecx,[esp+4] ; lea eax,[ecx+0xa3]  (eax MUST survive to resume) */
    .globl ogx_chain_setstate
    .type  ogx_chain_setstate,@function
ogx_chain_setstate:
    movl    4(%esp), %ecx             /* handle */
    leal    0xa3(%ecx), %eax          /* live USB interrupt data ptr */
    movl    $0x00413CC9, %edx         /* resume (eax = lea result preserved) */
    jmp     *%edx
    .size ogx_chain_setstate, .-ogx_chain_setstate

    .section .note.GNU-stack,"",@progbits
