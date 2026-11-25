#!/bin/sh
# Host test runner for the worker-14 completion-driven Attach state machine.
# The SAME ogxbox/gipdriver/src/gipdrive.h compiles into both the Xbox title
# and this harness.
set -e
cd "$(dirname "$0")"
cc -std=c11 -Wall -Wextra -I ../../gipdriver/src test_attach.c -o test_attach
./test_attach
