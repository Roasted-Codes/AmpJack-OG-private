#!/usr/bin/env bash
# run63.sh -- W63 hosted tests (tests/test63.c) + the work/32 F6 regression
# (f6_test.c, byte-identical copy) against the MODIFIED sources in ../src.
# -m32 ASan+UBSan. Exit 0 only if everything is GREEN.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); W=$(cd "$HERE/.." && pwd); OGX=$(cd "$W/../.." && pwd)
CC=${CC:-clang}
S="$W/src/ogxbox"; I="$S/integration"; OUT="$W/tests/out"; rm -rf "$OUT"; mkdir -p "$OUT"
MOCK=$OGX/work/28-opus-controller-review/tests
CF="-m32 -std=gnu11 -O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=undefined -Wall -Wno-unused-function -Wno-unused-parameter -I$I -I$S/gip -I$S/halo2 -I$W/src/core -I$S/gipdriver/src"
rc=0
# --- 1. W63 hosted tests
for s in ogx_transport ogx_present ogx_stub ogx_log; do $CC $CF -c "$I/$s.c" -o "$OUT/$s.o" || exit 3; done
$CC $CF -c "$S/halo2/xinput_model.c" -o "$OUT/xinput_model.o" || exit 3
$CC $CF -c "$HERE/test63.c" -o "$OUT/test63.o" || exit 3
$CC $CF "$OUT"/ogx_*.o "$OUT/xinput_model.o" "$OUT/test63.o" -o "$OUT/test63" || exit 3
pass=0; total=0
for c in a b c1 c2 c3 c4 c5; do
  total=$((total+1))
  if ASAN_OPTIONS=detect_leaks=0 "$OUT/test63" $c > "$OUT/test63-$c.log" 2>&1; then pass=$((pass+1)); else rc=1; fi
  echo "test63 $c: $(tail -1 "$OUT/test63-$c.log")"
done
echo "test63 summary: $pass/$total PASS"
# --- 2. F6 regression (work/32 suite, unmodified test code, modified module sources)
F="$OUT/f6"; mkdir -p "$F"
for s in ogx_transport ogx_present ogx_stub ogx_install ogx_log; do gcc $CF -I$MOCK -c "$I/$s.c" -o "$F/$s.o" >> "$F/build.log" 2>&1 || { echo "F6 BUILD FAILED $s"; cat "$F/build.log"; exit 3; }; done
gcc $CF -I$MOCK -c "$S/halo2/xinput_model.c" -o "$F/xinput_model.o" >> "$F/build.log" 2>&1 &&
gcc $CF -I$MOCK -c "$MOCK/native_mock.c" -o "$F/native_mock.o" >> "$F/build.log" 2>&1 &&
gcc $CF -I$MOCK -c "$HERE/f6_test.c" -o "$F/f6_test.o" >> "$F/build.log" 2>&1 &&
gcc $CF "$F"/*.o -o "$F/f6_test" >> "$F/build.log" 2>&1 || { echo "F6 BUILD FAILED"; cat "$F/build.log"; exit 3; }
ASAN_OPTIONS=detect_leaks=0 "$F/f6_test" > "$F/stubs-only.log" 2>&1; r1=$?
OGX_EXPLICIT_PUMP=1 ASAN_OPTIONS=detect_leaks=0 "$F/f6_test" > "$F/explicit-pump.log" 2>&1; r2=$?
echo "f6 stubs-only rc=$r1: $(tail -1 "$F/stubs-only.log")"
echo "f6 explicit-pump rc=$r2: $(tail -1 "$F/explicit-pump.log")"
[ $r1 -eq 0 ] && [ $r2 -eq 0 ] || rc=1
exit $rc
