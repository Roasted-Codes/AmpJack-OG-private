/* SPDX-License-Identifier: GPL-3.0-or-later */
ENTRY(ogx_module_entry)
SECTIONS
{
    . = 0;
    .text : { KEEP(*(.text.entry)) *(.text .text.*) }
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
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.interp) }
}
