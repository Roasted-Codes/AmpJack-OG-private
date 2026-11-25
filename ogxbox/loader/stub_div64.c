/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * 64-bit division/modulo helpers for i386 freestanding (compiler-rt is not linked
 * with -nostdlib). Provided only so the core-size probe links; the core may avoid
 * u64 division on this path, but if clang emits calls to __udivdi3/__umoddi3 the
 * link still succeeds. Disabled for the diagnostic container (not needed there).
 */
typedef unsigned long long u64;
typedef unsigned int u32;

static u64 __udivmoddi4_local(u64 n, u64 d, u64 *rem)
{
    u64 q = 0;
    u64 r = 0;
    int i;
    for (i = 63; i >= 0; i--) {
        r = (r << 1) | ((n >> i) & 1);
        if (r >= d) { r -= d; q |= ((u64)1 << i); }
    }
    if (rem) *rem = r;
    return q;
}

u64 __udivdi3(u64 n, u64 d) { return __udivmoddi4_local(n, d, 0); }
u64 __umoddi3(u64 n, u64 d) { u64 r; __udivmoddi4_local(n, d, &r); return r; }
u64 __udivmoddi4(u64 n, u64 d, u64 *r) { return __udivmoddi4_local(n, d, r); }
