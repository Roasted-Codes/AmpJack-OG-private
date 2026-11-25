/* SPDX-License-Identifier: GPL-3.0-or-later */
.intel_syntax noprefix
.code32
.section .text.entry,"ax"
.global trainer_entry
trainer_entry:
    pushfd
    pushad
    cld
    push ebp
    call trainer_main
    add esp, 4
    popad
    popfd
    ret
.section .note.GNU-stack,"",@progbits
