/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * og_host_platform.h -- host-only platform glue for the adapter and its tests.
 *
 * Defines the core/platform.h symbols not owned by og_gip.c (which owns
 * xa_now_ms): the unused wireless-adapter USB hooks, a deterministic RNG, a
 * no-op sleep, logging to stderr and the debug level. This file is a TEST
 * harness, not a real USB backend, and is never linked into the console port.
 */
#pragma once

#include <stdint.h>

#include "../../core/platform.h"

/* a monotonic clock for host runs (not used by the deterministic tests) */
u64 og_host_clock_ms(void);
void og_host_rng_seed(u32 seed);
