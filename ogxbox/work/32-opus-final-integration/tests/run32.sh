#!/usr/bin/env bash
# run32.sh INTEGRATION_SRC OUT_DIR [GIPDRIVER]
#  Builds the PRODUCTION module sources (copied, never edited) -m32 ASan+UBSan,
#  real thiscall/stdcall/fastcall, with the work/28 native_mock doubles, and runs
#  the work/32 F6 suite in both service modes. Exit 0 only if both modes GREEN.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); OGX=$(cd "$HERE/../../.." && pwd)
SRC=$(cd "$1" && pwd); OUT=$2; mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
GIPDRIVER=${3:-$OGX/gipdriver}
MOCK=$OGX/work/28-opus-controller-review/tests
T="$OUT/tree"; rm -rf "$T"; mkdir -p "$T/ogxbox"
cp -r "$SRC" "$T/ogxbox/integration"; rm -rf "$T/ogxbox/integration/out"
ln -s "$GIPDRIVER" "$T/ogxbox/gipdriver"; ln -s "$OGX/gip" "$T/ogxbox/gip"; ln -s "$OGX/halo2" "$T/ogxbox/halo2"; ln -s "$OGX/../core" "$T/core"
I="$T/ogxbox/integration"
{ echo "src=$SRC"; echo "gipdriver=$GIPDRIVER"
  (cd "$SRC" && sha256sum ogx_transport.c ogx_present.c ogx_present.h ogx_stub.c ogx_module.h ogx_install.c)
  sha256sum "$GIPDRIVER/src/gipdrive.h" "$MOCK/native_mock.c" "$MOCK/lifecycle_test.c" "$HERE/f6_test.c"; gcc --version | head -1; } > "$OUT/inputs.txt"
CF="-m32 -std=gnu11 -O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=undefined -Wall -Wno-unused-function -Wno-unused-parameter -I$I -I$T/ogxbox/gip -I$T/ogxbox/halo2 -I$T/core -I$GIPDRIVER/src -I$MOCK"
B="$OUT/build.log"; : > "$B"
for s in ogx_transport ogx_present ogx_stub ogx_install; do gcc $CF -c "$I/$s.c" -o "$OUT/$s.o" >> "$B" 2>&1 || { echo "BUILD FAILED $s"; cat "$B"; exit 3; }; done
gcc $CF -c "$T/ogxbox/halo2/xinput_model.c" -o "$OUT/xinput_model.o" >> "$B" 2>&1 &&
gcc $CF -c "$MOCK/native_mock.c" -o "$OUT/native_mock.o" >> "$B" 2>&1 &&
gcc $CF -c "$HERE/f6_test.c" -o "$OUT/f6_test.o" >> "$B" 2>&1 &&
gcc $CF "$OUT"/*.o -o "$OUT/f6_test" >> "$B" 2>&1 || { echo "BUILD FAILED"; cat "$B"; exit 3; }
ASAN_OPTIONS=detect_leaks=0 "$OUT/f6_test" > "$OUT/stubs-only.log" 2>&1; r1=$?
OGX_EXPLICIT_PUMP=1 ASAN_OPTIONS=detect_leaks=0 "$OUT/f6_test" > "$OUT/explicit-pump.log" 2>&1; r2=$?
echo "f6 stubs-only rc=$r1: $(tail -1 "$OUT/stubs-only.log")"
echo "f6 explicit-pump rc=$r2: $(tail -1 "$OUT/explicit-pump.log")"
[ $r1 -eq 0 ] && [ $r2 -eq 0 ]
