#!/bin/sh
# Host test runner for the GIP class-driver logic (ring / hex / frames /
# state machine / pin). The SAME ogxbox/gipdriver/src/gipdrive.h compiles into
# both the Xbox title and this harness.
set -e
cd "$(dirname "$0")"
cc -std=c11 -Wall -Wextra -I ../../gipdriver/src test_gipdriver.c -o test_gipdriver
./test_gipdriver
