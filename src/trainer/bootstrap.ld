/* SPDX-License-Identifier: GPL-3.0-or-later */
ENTRY(trainer_entry)
SECTIONS {
 . = 0;
 .text : { *(.text.entry) *(.text*) *(.rodata*) }
 .data : { *(.data*) *(.got*) }
 .dynamic : { *(.dynamic) }
 .dynsym : { *(.dynsym) }
 .dynstr : { *(.dynstr) }
 .hash : { *(.hash) }
 .rel.dyn : { *(.rel*) }
 .bss : { *(.bss*) *(COMMON) }
 boot_end = .;
 /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
