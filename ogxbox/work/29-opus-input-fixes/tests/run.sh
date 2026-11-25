#!/usr/bin/env bash
# run.sh SRC_DIR OUT_DIR -- work/29 F1/F2/F3 recovery regressions.
# Same build as work/28 tests/run.sh: PRODUCTION transport/present/stub +
# xinput_model + gipdrive.h (GIPDRIVER, default frozen copy) -m32 ASan/UBSan,
# title side = work/28 native_mock.c (read-only, unmodified). Never edits SRC.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OGX=$(cd "$HERE/../../.." && pwd)
SRC=$(cd "$1" && pwd)
OUT=$2; mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
GIPDRIVER=${GIPDRIVER:-$HERE/../frozen/ogxbox/gipdriver}
MOCK=$OGX/work/28-opus-controller-review/tests
T="$OUT/tree"; rm -rf "$T"; mkdir -p "$T/ogxbox"
cp -r "$SRC" "$T/ogxbox/integration"
ln -s "$GIPDRIVER" "$T/ogxbox/gipdriver"; ln -s "$OGX/gip" "$T/ogxbox/gip"; ln -s "$OGX/halo2" "$T/ogxbox/halo2"
ln -s "$OGX/../core" "$T/core"
I="$T/ogxbox/integration"
{ echo "src=$SRC"; echo "gipdriver=$GIPDRIVER"
  (cd "$SRC" && sha256sum ogx_transport.c ogx_present.c ogx_present.h ogx_stub.c ogx_module.h)
  sha256sum "$GIPDRIVER/src/gipdrive.h" "$MOCK/native_mock.c" "$HERE/regress_test.c"; gcc --version | head -1; } > "$OUT/inputs.txt"
CF="-m32 -std=gnu11 -O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=undefined -Wall -Wno-unused-function -Wno-unused-parameter -I$I -I$MOCK -I$T/ogxbox/gip -I$T/ogxbox/halo2 -I$T/core -I$GIPDRIVER/src"
set -x
for f in "$I/ogx_transport.c" "$I/ogx_present.c" "$I/ogx_stub.c" "$T/ogxbox/halo2/xinput_model.c" "$MOCK/native_mock.c" "$HERE/regress_test.c"; do
  gcc $CF -c "$f" -o "$OUT/$(basename "${f%.c}").o" || { echo BUILD FAILED; exit 3; }
done
gcc $CF "$OUT"/*.o -o "$OUT/regress_test" || { echo LINK FAILED; exit 3; }
set +x
ASAN_OPTIONS=detect_leaks=0 "$OUT/regress_test" > "$OUT/regress.log" 2>&1; r=$?
echo "regress rc=$r: $(tail -1 "$OUT/regress.log")"; exit $r
