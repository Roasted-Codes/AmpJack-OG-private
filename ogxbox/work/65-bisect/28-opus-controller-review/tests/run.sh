#!/usr/bin/env bash
# run.sh SRC_DIR [OUT_DIR]
#   Builds the PRODUCTION module sources in SRC_DIR (default: frozen baseline
#   work/24-halo2-input/parent-before-correction) UNMODIFIED for i386 (-m32,
#   real thiscall/stdcall, 32-bit VAs) with ASan+UBSan, links the SYNTHETIC
#   title doubles, runs both service modes. Never edits SRC_DIR.
#   Exit: 0 only if stubs-only mode is all GREEN.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OGX=$(cd "$HERE/../../.." && pwd)                       # .../ogxbox
SRC=$(cd "${1:-$OGX/work/24-halo2-input/parent-before-correction}" && pwd)
OUT=${2:-$HERE/../logs/run-$(basename "$SRC")}
GIPDRIVER=${GIPDRIVER:-$OGX/gipdriver}
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
T="$OUT/tree"; rm -rf "$T"; mkdir -p "$T/ogxbox"
cp -r "$SRC" "$T/ogxbox/integration"
ln -s "$GIPDRIVER" "$T/ogxbox/gipdriver"; ln -s "$OGX/gip" "$T/ogxbox/gip"; ln -s "$OGX/halo2" "$T/ogxbox/halo2"
ln -s "$OGX/../core" "$T/core"
I="$T/ogxbox/integration"
{
 echo "src=$SRC"; echo "gipdriver=$GIPDRIVER"
 (cd "$SRC" && sha256sum ogx_transport.c ogx_present.c ogx_present.h ogx_stub.c ogx_module.h 2>/dev/null)
 sha256sum "$GIPDRIVER/src/gipdrive.h"
 gcc --version | head -1
} > "$OUT/inputs.txt"
CF="-m32 -std=gnu11 -O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=undefined -Wall -Wno-unused-function -Wno-unused-parameter -I$I -I$T/ogxbox/gip -I$T/ogxbox/halo2 -I$T/core -I$GIPDRIVER/src"
set -x
gcc $CF -c "$I/ogx_transport.c" -o "$OUT/ogx_transport.o" &&
gcc $CF -c "$I/ogx_present.c"   -o "$OUT/ogx_present.o" &&
gcc $CF -c "$I/ogx_stub.c"      -o "$OUT/ogx_stub.o" &&
gcc $CF -c "$T/ogxbox/halo2/xinput_model.c" -o "$OUT/xinput_model.o" &&
gcc $CF -c "$HERE/native_mock.c"    -o "$OUT/native_mock.o" &&
gcc $CF -c "$HERE/lifecycle_test.c" -o "$OUT/lifecycle_test.o" &&
gcc $CF "$OUT"/*.o -o "$OUT/lifecycle_test"
rc=$?; set +x
[ $rc -eq 0 ] || { echo "BUILD FAILED rc=$rc (adapt harness_init() if host ABI changed)"; exit 3; }
ASAN_OPTIONS=detect_leaks=0 "$OUT/lifecycle_test" > "$OUT/stubs-only.log" 2>&1; r1=$?
OGX_EXPLICIT_PUMP=1 ASAN_OPTIONS=detect_leaks=0 "$OUT/lifecycle_test" > "$OUT/explicit-pump.log" 2>&1; r2=$?
echo "stubs-only rc=$r1: $(tail -1 "$OUT/stubs-only.log")"
echo "explicit-pump rc=$r2: $(tail -1 "$OUT/explicit-pump.log")"
exit $r1
