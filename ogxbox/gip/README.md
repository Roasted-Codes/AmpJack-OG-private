# og_gip — wired Xbox One (GIP) → OG Xbox input adapter

A small, host-compilable, reusable adapter that reuses AmpJack's existing
`core/gip.c` parser unchanged, and republishes its output as a fixed-size
original-Xbox controller snapshot. This is worker 04 of the ogxbox port.

## What it is

- `og_gamepad.h` — the OG Xbox `XINPUT_GAMEPAD` shape (VERIFIED against
  `OXDK/xbox/xdk/include/xbox.h`), and `og_gamepad_from_gip()`: the
  button/stick/trigger map from `struct gip_gamepad_state`.
- `og_gip.h` / `og_gip.c` — the adapter: one wired, `no_auth` GIP client per
  port; a bounded outgoing queue for the init/ack/control packets the parser
  emits (power-on, LED, rumble-stop, identify requests, acknowledge); an
  injected clock (the adapter owns `xa_now_ms`); explicit unknown-command and
  length-limit handling; hot-unplug and reset. No audio, no headset, no
  security handshake, no dongle — nothing wired input doesn't need.
- `og_host_platform.c` / `og_gip_test.c` — a TEST-ONLY host harness that links
  the **real** `core/gip.c` (+ `sha256.c`, `mt76.c`, `dongle.c`, `micro-ecc`)
  and drives it with labelled synthetic frames.

## Build and test (gcc, clang, sanitizers)

    make -C ogxbox/gip test      # gcc: the positive end-to-end scenarios
    make -C ogxbox/gip hardtest  # gcc: the boundary/hardening regression suite
    make -C ogxbox/gip CC=clang test hardtest
    make -C ogxbox/gip asan hardtest_asan   # -fsanitize=address,undefined
    ./ogxbox/gip/test            # or hardtest, asan, hardtest_asan
    XA_DEBUG=1 ./ogxbox/gip/test # shows the GIP packet hex

All four binaries must end `all ok`. The positive suite exercises the real parser
(announce → identify request → start_gamepad → input → snapshot, plus an
acknowledged input, the Guide path, status-off, hot unplug, unknown/length-limit
frames, and the 1500 ms wired "no announce" fallback). The hardening suite
(`hardtest`) drives the boundary: trigger saturation, individual LB/RB mapping,
tx_drain refusal-to-truncate (negative/too-small/NULL), tx_send backpressure and
ring wrap/recovery, powered-ready vs snapshot-valid, no-stale-state lifecycle,
and malformed framing/varints under the sanitizers.

## What this is NOT

**The USB transport backend still needs to be built.** This adapter consumes
already-collected interrupt-IN bytes and hands back a queue of interrupt-OUT
packets; it does not enumerate, claim or reset any USB device, and it will not,
by itself, make a controller appear on the console. On the console it must sit
behind the XID/class driver (worker 02) and feed the title's `XInputGetState`
(worker 03). No host test here proves USB enumeration or playable hardware —
`lsusb` showed no pad at dispatch.

## Notes for the console port

- Time: install a nonzero monotonic clock with `og_gip_clock_set` (e.g. from the
  kernel time base). `core/gip.c` guards its wired start-fallback with
  `gc->started &&`, so the clock must be nonzero for the xpad-style blind start
  to ever run (observed in the tests).
- Threading: no locks, no lock-free claims. One owner thread calls init/rx/poll/
  unplug/reset/deinit and installs the clock; the gip_ops callbacks fire
  synchronously on that thread. The outgoing queue has one producer
  (`og_tx_send`, from within rx/poll) and one consumer (`og_gip_tx_drain`, the
  USB OUT backend) — serialize them if they are not the same thread.
- Memory: the adapter is static (584 B). The only dynamic memory is
  `core/gip.c`'s own chunk buffers, each capped at core's
  `GIP_CHUNK_BUF_MAX_LENGTH` (0xffff = 65535 bytes) and sized from the untrusted
  `chunk_offset` of an incoming CHUNK_START frame (core rejects offsets above the
  cap; an allocation failure surfaces as `-XA_ENOMEM`). This is NOT a static
  bound on parser memory: supply a bounded `malloc/calloc/free` on-console (the
  console port's allocator is the real cap), and do not advertise static memory.
- Endianness: the OG Xbox is x86, so the packed `og_gamepad` in memory is the
  wire layout; `og_gamepad_pack` spells the byte order out for big-endian hosts.

## Boundary / backpressure contract (worker 08 hardening)

- `og_tx_send` (the transport `.send`): 0 = accepted; a negative XA code =
  refused. A full ring is backpressure — the NEW packet is dropped and counted in
  `tx_dropped`, existing queued packets are untouched, and `-XA_ENOSPC` is
  returned so `core/gip.c` sees the failure (it will NOT publish ready after a
  dropped power-on). `core/gip.c` does not retry a refused send itself; drain
  promptly, and recover by re-plug/reset once its state machine has run past the
  send it failed.
- `og_gip_tx_drain`: 0 = empty, >0 = popped length, `-XA_ENOSPC` = the next
  packet does not fit `max` (left queued, retry with a bigger buffer),
  `-XA_EINVAL` = NULL port/out or negative `max`. It never truncates.
- `ready` is POWERED-READY (core fired `ops->ready` after power-on), not
  input-seen — a Halo consumer must read `snapshot_valid` for "a real input frame
  has populated the snapshot". `snapshot_valid` is cleared on gone/unplug/deinit/
  reset, so no stale button state can be read as live input.
- Trigger mapping saturates before scaling: values above 1023 clamp to 1023, so
  an out-of-range u16 report (which used to wrap the narrowing cast, e.g.
  65535 → 209) maps to 255. In-range values (0..1023) are unchanged.
- LB → Black and RB → White is kept (standard dual-analog equivalence); it is an
  INFERENCE — there is no verified Halo 2 or user mapping evidence that reverses
  it, so it was left as-is and covered by individual-press tests.
