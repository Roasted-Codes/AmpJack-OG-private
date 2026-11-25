#!/usr/bin/env bash
# run30.sh INTEGRATION_SRC OUT_DIR
#  1) work/28 suite (unaltered) via its run.sh  -> OUT/t28
#  2) work/30 lifetime variants, same production objects, i386 ASan+UBSan -> OUT/v30
#  3) legacy header regressions (11/14/15/17 + 22 close contract) vs LIVE header -> OUT/legacy
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); OGX=$(cd "$HERE/../../.." && pwd)
SRC=$(cd "$1" && pwd); OUT=$2; mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
export GIPDRIVER=${GIPDRIVER:-$OGX/gipdriver}; GIP=$GIPDRIVER/src   # override = baseline header copy (RED run)
bash "$OGX/work/28-opus-controller-review/tests/run.sh" "$SRC" "$OUT/t28" > "$OUT/t28.summary" 2>&1; echo "t28: $(tail -2 "$OUT/t28.summary" | tr '\n' ' ')"
T=$OUT/t28/tree; I=$T/ogxbox/integration; V=$OUT/v30; mkdir -p "$V"
CF="-m32 -std=gnu11 -O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=undefined -Wall -Wno-unused-function -Wno-unused-parameter -I$I -I$T/ogxbox/gip -I$T/ogxbox/halo2 -I$T/core -I$GIP -I$OGX/work/28-opus-controller-review/tests"
gcc $CF ${BASELINE_DEF:-} -c "$HERE/lifetime_test.c" -o "$V/lifetime_test.o" 2> "$V/build.log" &&
gcc $CF "$OUT"/t28/{ogx_transport,ogx_present,ogx_stub,xinput_model,native_mock}.o "$V/lifetime_test.o" -o "$V/lifetime_test" 2>> "$V/build.log" || { echo "v30 BUILD FAILED"; cat "$V/build.log"; }
ASAN_OPTIONS=detect_leaks=0 "$V/lifetime_test" > "$V/stubs-only.log" 2>&1; r1=$?
OGX_EXPLICIT_PUMP=1 ASAN_OPTIONS=detect_leaks=0 "$V/lifetime_test" > "$V/explicit-pump.log" 2>&1; r2=$?
echo "v30 stubs-only rc=$r1: $(tail -1 "$V/stubs-only.log")"; echo "v30 explicit-pump rc=$r2: $(tail -1 "$V/explicit-pump.log")"
L=$OUT/legacy; mkdir -p "$L"
for t in 11-gipdriver/test_gipdriver 14-attach/test_attach 15-handshake/test_handshake 17-sol-execution/test_sol17; do
  n=$(basename $t)
  if cc -std=c11 -Wall -Wextra -I "$GIP" "$OGX/work/$t.c" -o "$L/$n" > "$L/$n.build" 2>&1; then "$L/$n" > "$L/$n.log" 2>&1; echo "legacy $n rc=$? $(tail -1 "$L/$n.log")"; else echo "legacy $n BUILD FAIL: $(head -3 "$L/$n.build")"; fi
done
for f in "" "-m32 -fsanitize=address,undefined -fno-sanitize-recover=undefined"; do
  if cc -std=gnu11 -Wall -Wextra $f -DGDR_HAS_CLOSE -I "$GIP" "$OGX/work/22-native-close/tests/test_close_contract.c" -o "$L/close22" > "$L/close22.build" 2>&1; then ASAN_OPTIONS=detect_leaks=0 "$L/close22" > "$L/close22${f:+-asan}.log" 2>&1; echo "legacy close22 ${f:+asan} rc=$? $(tail -1 "$L/close22${f:+-asan}.log")"; else echo "legacy close22 BUILD FAIL: $(head -5 "$L/close22.build")"; fi
done
grep -h "warning" "$OUT"/t28/*.log "$V/build.log" "$L"/*.build 2>/dev/null | grep -i gipdrive | sort -u | head
exit 0
