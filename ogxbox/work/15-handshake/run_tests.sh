#!/bin/sh
# Host test runner for the worker-15 v3 fixes (gipdrive.h). The SAME
# ogxbox/gipdriver/src/gipdrive.h compiles into the Xbox title and this harness.
set -e
cd "$(dirname "$0")"
cc -std=c11 -Wall -Wextra -I ../../gipdriver/src test_handshake.c -o test_handshake
./test_handshake
