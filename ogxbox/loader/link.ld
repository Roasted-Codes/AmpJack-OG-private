/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Flat static-PIE layout for an OG Xbox stage-2 module: one image from address 0,
 * then bss. The only run-time relocations are R_386_RELATIVE (mkmodule.py refuses
 * anything else). Dynamic sections go AFTER _end so they are not part of the image. */
ENTRY(h2s2_entry)
SECTIONS
{
    . = 0;
    .h2s2hdr : { KEEP(*(.h2s2hdr)) }
    .text : { *(.text.entry) *(.text .text.*) }
    .rodata : { *(.rodata .rodata.*) }
    .data : {
        *(.data.rel.ro .data.rel.ro.*)
        *(.got) *(.got.plt) *(.igot.plt)
        *(.data .data.*)
    }
    . = ALIGN(4);
    _image_end = .;
    .bss : { *(.bss .bss.* COMMON) }
    . = ALIGN(4);
    _end = .;
    . = ALIGN(4096);
    .dynamic : { *(.dynamic) }
    .dynsym : { *(.dynsym) }
    .dynstr : { *(.dynstr) }
    .hash : { *(.hash) }
    .gnu.hash : { *(.gnu.hash) }
    .rel.dyn : { *(.rel.dyn) }
    .rel.plt : { *(.rel.plt) }
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.interp) }
}
