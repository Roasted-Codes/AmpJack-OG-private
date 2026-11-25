#!/bin/sh
# Host test runner for the diagnostic logic (ring / log format / signature).
# The SAME ogxbox/diagnostic/src/diag_util.h is compiled into both the Xbox
# title and this harness, so what is tested here is literally the code the
# Xbox runs.
set -e
cd "$(dirname "$0")"
cc -std=c99 -Wall -Wextra -I ../../diagnostic/src test_diagnostic.c -o test_diagnostic
./test_diagnostic
