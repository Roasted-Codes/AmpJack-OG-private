#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# OG Xbox stage-2 LOADER feasibility build. Run from ogxbox/loader/ .
#
#   ./build.sh          -> out/diag.bin  (DISABLED diagnostic container)
#                          out/core_probe.bin  (real AmpJack core, SYNTHETIC stub
#                                               transport: link+size evidence only)
#                          out/thunk_demo.txt  (objdump of the call conventions)
#
# Toolchain = system clang + ld.lld (i386 ELF, static PIE), the same route the
# LAN_Stats stage-2 module uses. No OXDK/XBE needed: this is not an XBE build.
# XBE25 note: -mstack-alignment is accepted by clang/i386 here.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out

CLANG=${CLANG:-clang}
LLD=${LLD:-ld.lld}

# i386 ELF so lld emits R_386_RELATIVE; pentium3 = the Xbox CPU. -fpie: PC/EBX-relative
# code, load-time fixups only for absolute pointers in data. No x87/SSE (runs inside the
# game's own threads). No libc beyond the stub; no exceptions/unwind.
CFLAGS="-target i386-unknown-none-elf -march=pentium3 -Os -std=gnu11 \
 -ffreestanding -nostdlib -fpie -fvisibility=hidden -mgeneral-regs-only \
 -mstack-alignment=4 -fno-stack-protector -fno-asynchronous-unwind-tables \
 -fno-unwind-tables -fno-exceptions -fno-common -ffunction-sections -fdata-sections \
 -Wall -Wextra -Werror -Wno-unused-parameter"

# -z text: lld refuses relocations in code; mkmodule.py also rejects anything but
# R_386_RELATIVE. --gc-sections drops unreferenced code (the diag module links only
# crt0 + main). The size probe omits --gc-sections to measure the whole driver.
LDFLAGS="-pie --no-dynamic-linker -z text -z norelro --hash-style=sysv -T link.ld"

echo "== 1/3 DISABLED diagnostic container =="
$CLANG $CFLAGS -I. -c crt0.c -o out/crt0.o
$CLANG $CFLAGS -I. -c diag_main.c -o out/diag_main.o
$LLD $LDFLAGS --gc-sections -Map out/diag.map -o out/diag.elf out/crt0.o out/diag_main.o
python3 mkmodule.py out/diag.elf out/diag.bin
readelf -r out/diag.elf | grep -i TEXTREL && { echo "FAIL: text relocations"; exit 1; } || true

echo "== 2/3 call-convention encodings (objdump) =="
$CLANG $CFLAGS -I. -c thunk_demo.c -o out/thunk_demo.o
objdump -d -Mintel out/thunk_demo.o > out/thunk_demo.txt
grep -A12 '<ogx_alloc_via_thunk_slot>\|<ogx_call_title_absolute>' out/thunk_demo.txt

echo "== 3/3 core-size probe (real AmpJack core + sylthetic stub transport) =="
CORE="../../core/gip.c ../../core/dongle.c ../../core/mt76.c ../../core/sha256.c"
ECC="../../third_party/micro-ecc/uECC.c"
ECC_DEFS="-DuECC_SUPPORTS_secp160r1=0 -DuECC_SUPPORTS_secp192r1=0 -DuECC_SUPPORTS_secp224r1=0 \
 -DuECC_SUPPORTS_secp256k1=0 -DuECC_PLATFORM=uECC_arch_other"
$CLANG $CFLAGS $ECC_DEFS -I. -Ifreestanding -I../../core -I../../third_party/micro-ecc \
    -c core_probe_main.c -o out/core_probe_main.o
$CLANG $CFLAGS $ECC_DEFS -I. -Ifreestanding -I../../core -c stub_libc.c -o out/stub_libc.o
$CLANG $CFLAGS $ECC_DEFS -I. -Ifreestanding -I../../core -c stub_platform.c -o out/stub_platform.o
for src in $CORE; do
    $CLANG $CFLAGS $ECC_DEFS -I../../core -I../../third_party/micro-ecc -I. -Ifreestanding \
        -c "$src" -o "out/$(basename "${src%.c}").o"
done
$CLANG $CFLAGS $ECC_DEFS -I../../third_party/micro-ecc -c $ECC -o out/uECC.o
# No --gc-sections: keep the whole driver so the sizes are an honest upper bound.
$LLD $LDFLAGS -Map out/core_probe.map -o out/core_probe.elf \
    out/core_probe_main.o out/stub_libc.o out/stub_platform.o \
    out/gip.o out/dongle.o out/mt76.o out/sha256.o out/uECC.o \
    out/crt0.o 2>&1 | head -40 || {
        # Undefined 64-bit helpers (no compiler-rt): provide a tiny __udivdi3 set.
        echo "NOTE: link needs 64-bit helpers; retrying with stub_div64.c"
        $CLANG $CFLAGS -I. -c stub_div64.c -o out/stub_div64.o
        $LLD $LDFLAGS -Map out/core_probe.map -o out/core_probe.elf \
            out/core_probe_main.o out/stub_libc.o out/stub_platform.o out/stub_div64.o \
            out/gip.o out/dongle.o out/mt76.o out/sha256.o out/uECC.o out/crt0.o
    }
python3 mkmodule.py out/core_probe.elf out/core_probe.bin

echo "== section sizes (from linker map / nm) =="
size out/core_probe.elf out/diag.elf || true
echo "-- per-object .text/.data/.rodata contributions to core_probe (nm, sorted) --"
LC_ALL=C nm --print-size --size-sort out/core_probe.elf > out/core_probe.nm 2>/dev/null
head -30 out/core_probe.nm

echo "== done; artifacts in out/ =="
ls -l out/*.bin out/*.elf out/*.map out/thunk_demo.txt
