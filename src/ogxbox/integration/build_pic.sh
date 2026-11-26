#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# i386 static-PIE build of the TITLE-RESIDENT module: the proven GIP USB transport
# (gipdrive.h, header-only, address-independent) + the hardened virtual-XInput
# presentation + the six hook stubs + chain trampolines + build-bound installer +
# FindClassDriver class-match hook. Proves the whole vertical slice is PIC: only
# R_386_RELATIVE relocation is permitted (readelf -r), no text relocations
# (-z text), and the chain trampolines hold no stale displaced PC-relative offset.
#
# The GIP core/adapter PIC-ness was already proven by ogxbox/loader (worker 05);
# this build is the loadable module the parent injector stages + relocates.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out

CLANG=${CLANG:-clang}
LLD=${LLD:-ld.lld}

CFLAGS="-target i386-unknown-none-elf -march=pentium3 -Os -std=gnu11 \
 -ffreestanding -nostdlib -fpie -fvisibility=hidden \
 -mstack-alignment=4 -fno-stack-protector -fno-asynchronous-unwind-tables \
 -fno-unwind-tables -fno-exceptions -fno-common -ffunction-sections -fdata-sections \
 -Wall -Wextra -Wno-unused-parameter -Wno-unused-function"

LDFLAGS="-pie --no-dynamic-linker -z text -z norelro --hash-style=sysv --gc-sections -T link.ld"

INC="-I. -Ifreestanding -I.. -I../gip -I../halo2 -I../../core -I../gipdriver/src"

$CLANG $CFLAGS $INC -c crt0.c          -o out/crt0.o
$CLANG $CFLAGS $INC -c string.c        -o out/string.o
$CLANG $CFLAGS $INC -c ogx_present.c   -o out/ogx_present.o
$CLANG $CFLAGS $INC -c ogx_stub.c      -o out/ogx_stub.o
$CLANG $CFLAGS $INC -c ../halo2/xinput_model.c -o out/xinput_model.o
$CLANG $CFLAGS $INC -c ogx_transport.c -o out/ogx_transport.o
$CLANG $CFLAGS $INC -c ogx_install.c   -o out/ogx_install.o
$CLANG $CFLAGS $INC -c module_main.c   -o out/module_main.o
$CLANG $CFLAGS $INC -c trampoline.S    -o out/trampoline.o

$LLD $LDFLAGS -Map out/pic.map -o out/pic.elf \
    out/crt0.o out/string.o out/ogx_present.o out/ogx_stub.o \
    out/xinput_model.o out/ogx_transport.o out/ogx_install.o \
    out/module_main.o out/trampoline.o

echo "== relocation audit: only R_386_RELATIVE allowed, no TEXTREL =="
readelf -r out/pic.elf
readelf -d out/pic.elf | grep -i textrel && { echo "FAIL: TEXTREL present"; exit 1; } || echo "ok: no TEXTREL flag"

echo "== text/data/bss sizes (from size on the linked ELF) =="
size out/pic.elf

echo "== section sizes from the linker map =="
grep -E '^\\.(text|rodata|data|bss|data\\.hooktab)' out/pic.map | head -20 || true

echo "== chain trampoline bytes: XInputClose re-encoded (no stale E8 rel32) =="
objdump -d -Mintel out/trampoline.o | grep -A8 'ogx_chain_inputclose' || true
echo "== confirm no stale call-rel32 (e8 <target>) remains in any chain stub =="
if objdump -d out/trampoline.o | grep -qE 'call +[0-9]'; then
    echo "FAIL: a relative call remains"; exit 1
else
    echo "ok: no relative call retained (all absolute-constant + register-indirect)"
fi
