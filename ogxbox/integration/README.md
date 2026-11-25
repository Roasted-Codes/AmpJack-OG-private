# ogxbox/integration — GIP parser → hardened snapshot → Halo 2 virtual XInput

Owner: worker 10. This is the honest host-side controller path: it consumes the
VERIFIED hardened GIP adapter (`ogxbox/gip/`, worker 08, read-only), serves an
original-Xbox XInput presentation, and proves a PIC trampoline build. It does NOT
pretend the USB transport exists yet: a failed/missing binding returns
"no device", never a playable lie.

## Architecture

     core/gip.c  (upstream parser, read-only, unchanged)
          |  GIP frames (synthetic in tests)
          v
     ogxbox/gip/og_gip.c  ->  struct og_gip_port  (hardened 18-byte snapshot + ready/valid/seq)
          |  reads .gamepad / .ready / .snapshot_valid / .seq only
          v
     ogxbox/integration/ogx_present.{h,c}   (production presentation layer)
          |  + ogx_stub.c  (six stdcall hook entry points, C/PIC)
          |  + trampoline.S  (six chain trampolines, re-encoded displaced bytes)
          v
     Halo 2 u803 XInput family  (via 6 verified E9 detours in XPP, validated only)

The runtime reaches everything through ONE injected pointer, `struct ogx_host_ctx`
(ogx_present.h): no absolute self-symbol loads, no guessed title pointer
(`xdevice_type_gamepad` = 0x4127D8 is injected, not hardcoded).

### The "present" contract (decided here, explicitly)

- `attached_mask[n]` — set ONLY by the USB transport backend when it has
  physically enumerated+claimed port n and interrupts flow. The presentation
  never sets it. Today there is NO backend, so the default is 0 = "no device".
- `ready[n]` — og_gip powered-ready (`ops->ready`), NOT input-seen.
- `present[n]` = `attached && ready`. Only "present" raises an insertion edge.
- `snapshot_valid[n]` — a real input frame has populated the 18-byte snapshot.
  XInputGetState returns success + zeroed gamepad when present-but-no-input-yet
  (honest boot state), and 0x48F only for a stale/disconnected handle.

### Handle discrimination (fixes worker 03 wholesale)

- Synthetic handle = address of an owned object in a fixed 16-slot arena
  (`ogx_vhandle`: magic + generation + port + live). The allocator is MONOTONIC
  and never recycles an issued address, so a stale pre-unplug handle stays dead
  forever (it is a raw uintptr; if it aliased a later live object it would
  resurrect, since classification reads the new object not the stored gen).
  Trade-off: the arena is a FINITE, fail-closed budget -- after 16 issues
  `XInputOpen` returns NULL ("no device") until the title reboots. This is
  documented, NOT a transparent infinite hotplug.
- Only arena-addresses with matching magic are intercepted. Everything else is
  CHAINED to `orig_*` (which re-run the displaced bytes + jmp resume), so native
  handles reach the untouched title XID code — never swallowed.
- `XGetDeviceChanges` merges virtual + native insertions/removals ONLY for the
  injected `XDEVICE_TYPE_GAMEPAD` pointer, and only onto ports a native gamepad
  does not already own (`present && !native-owned`, "no stealing"). Memory-unit /
  headset types pass through and do NOT touch the gamepad-native mask. On a
  native->virtual handover the virtual insertion is deferred one poll (rem-then-
  ins across two polls); on a virtual->native takeover the virtual handle is
  invalidated so it cannot keep serving the port.
- Disconnected/stale handles return the real `0x48F` (ERROR_DEVICE_NOT_CONNECTED);
  null output -> `0x57` (ERROR_INVALID_PARAM). No pointer outside the owned arena
  is ever dereferenced.

### Capabilities & rumble

- `ogx_fill_gamepad_caps()` zero-fills all 25 bytes (worker 03 left fields set),
  SubType = 1 (gamepad), Rumble = 0 (NO motors this milestone — claiming 0xFFFF
  support while returning no output would be dishonest). caps.Gamepad markers are
  INFERENCE (sizes/layout VERIFIED).
- `XInputSetState` takes `PXINPUT_FEEDBACK` (VERIFIED OXDK `xbox.h`, packed):
  `XINPUT_FEEDBACK_HEADER { DWORD dwStatus; HANDLE hEvent; BYTE Reserved[58]; }`
  then the 4-byte `XINPUT_RUMBLE` at offset 66 (70 bytes total). It is NOT a PC
  `XINPUT_VIBRATION` pointer — the motor speeds are not at offset 0. With no
  motors, the honest input-only result is `ERROR_NOT_SUPPORTED` (0x32), and
  `Header.dwStatus` is set to the same value (the XID output-completion gate).
  `hEvent` is never signalled (no completion occurs) and the Rumble bytes are
  never read or written. NULL feedback -> `0x57`; detach -> `0x48F`.

### Safe trampolines (no runtime installer shipped)

- `trampoline.S`: the six chain trampolines re-run each site's displaced bytes and
  tail-jump to `resume`. The ONE displaced PC-relative instruction —
  XInputClose's `call rel32` to XID_fCloseDevice 0x41493E — is RE-ENCODED as
  `mov eax,0x41493e; call eax` (verified by objdump: no stale `E8 CD 0E 00 00`
  displacement remains). GetState's `call [0x41b700]` is rebuilt the same way.
- `detour_plan.py` (stdlib, `--xbe PATH` supported) re-reads the XBE and asserts,
  per site: exact SHA256, XPP membership (exec+writable), the exact 5 overwrite
  bytes, instruction-boundary end of the displaced span, NO branch-into-overwrite
  hazard, and the XInputClose PC-relative re-encode target. It is an INSTALL-PLAN
  validator — it does not patch the XBE (no runtime installer is shipped because
  the URB ABI is not yet proven; see blockers).

## Run commands (all executed and green)

    make -C ogxbox/integration test          # gcc host test (real core/gip.c path)
    make -C ogxbox/integration test-clang    # clang
    make -C ogxbox/integration asan          # ASan/UBSan, leak-checked
    make -C ogxbox/integration verify        # XBE hook-site install-plan validator
    make -C ogxbox/integration pic           # i386 static-PIE + relocation audit
    python3 ogxbox/integration/detour_plan.py --xbe /path/to/default.xbe

    Result: test (gcc) PASS 0 fail (incl. 7 new parent-review regression
    scenarios); clang PASS; asan PASS (no leaks); verify "ALL HOOK-SITE
    INSTALL-PLAN ASSERTIONS PASSED" (6 sites); pic: 12 relocations all
    R_386_RELATIVE, no TEXTREL, GNU_STACK RW (PIE).

## What is executable NOW vs what remains

Executable (host, exercised): real GIP parser -> hardened og_gip snapshot ->
served XINPUT_STATE with mapped button bytes; native+virtual coexistence with a
real connected mask; insertion/removal edge exactly once; effective-presence
handover (native->virtual deferred insertion, virtual->native invalidation);
non-gamepad dtype does not contaminate the gamepad-native mask; monotonic
never-recycling handle arena with fail-closed 16-handle exhaustion; stale/
invalid handle and null-output error codes; caps/getstate/setstate presence
gate (detach fails before the next poll); monotonic packet number across a
replug that reuses the adapter seq; XInputSetState PXINPUT_FEEDBACK ABI
(offset/size/sentinel checks, ERROR_NOT_SUPPORTED, NULL = invalid param);
caps zero-fill; i386 static-PIE build with R_386_RELATIVE-only relocation audit.

NOT executable / remaining before the first physical diagnostic:
1. USB transport backend (worker 09) — the class-driver attach + interrupt-URB
   submission path. It does not exist yet; `attached_mask` stays 0.
2. The u803 E9 patch application — no runtime installer is shipped; detour_plan
   proves the bytes/math only.
3. Any real-hardware or emulator run (not authorized/owned this wave).

## Current blockers (honest)

- GIP class match id: the PNP_CLASS_ID the console computes for a GIP interface
  (class FF/47/D0) and whether the composite reaches LoadClassDriver is UNKNOWN
  (worker 07 §1/§7). MatchByte0 (0x82) derivation is not from the raw descriptor.
- Transport URB ABI: BulkOrInterrupt / OpenEndpoint / CloseEndpoint variant byte
  layouts + completion IRQL are UNKNOWN. worker 09 owns `research/binding/`; their
  `ogxbox_urb_abi.h` / `work/09-urb` were NOT present at integration time, so this
  layer deliberately does not fabricate a transport.
- Hotplug/concurrency: real attach/detach timing and the title's dispatch thread
  are UNKNOWN (no console run). The presentation is single-owner and NOT
  lock-free: `attached_mask` is `volatile` (signal visibility only, not
  synchronization); the transport must serialize cross-thread access / og_gip
  calls (see og_gip.h). No concurrency-safety claim is made here.

## Memory (from the linker map, built)

- Integration layer (presentation + stubs + trampolines): text 2097 B, data 156 B,
  bss 408 B = 2661 B (from `out/pic.map`). The runtime `ogx_host_ctx` is
  populated by the loader at install time (arena + port pointers); the static
  `g_ctx` pointer lives in bss.
- Full wired core is a separate, already-measured quantity (worker 05 loader):
  ~40 KB wired-only / ~78 KB full wireless core, both under the loader's 4 MiB cap.
  The integration layer adds ~2.6 KB on top.
