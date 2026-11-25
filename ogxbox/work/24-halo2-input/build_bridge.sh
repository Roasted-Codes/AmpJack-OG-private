#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Production-linked bridge test (HOST build, no guest). Links the REAL
# ogx_transport.c + ogx_stub.c + ogx_present.c + xinput_model.c and drives the
# gdr attach state machine through a FAKE native USB transport (the only mock).
#
# gcc + clang + asan variants, mirroring integration/Makefile.
set -euo pipefail
cd "$(dirname "$0")"

INT=../../integration
CORE=../../../core
SRCS="$INT/ogx_transport.c $INT/ogx_stub.c $INT/ogx_install.c $INT/ogx_present.c ../../halo2/xinput_model.c test_bridge.c"
INC="-I$INT -I../../halo2 -I../../gip -I../../gipdriver/src -I$CORE"
WARN="-Wall -Wextra -Wno-unused-parameter -Wno-unused-function"

echo "== gcc bridge test =="
cc -O2 -g -std=gnu11 $WARN $INC $SRCS -o test_bridge
./test_bridge

echo "== clang bridge test =="
clang -O2 -g -std=gnu11 $WARN $INC $SRCS -o test_bridge_clang
./test_bridge_clang

echo "== asan bridge test =="
cc -O1 -g -std=gnu11 $WARN -fsanitize=address,undefined -fno-omit-frame-pointer \
   $INC $SRCS -o test_bridge_asan
./test_bridge_asan

echo "ALL BRIDGE TEST VARIANTS PASSED"
