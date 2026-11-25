# AmpJack OG — worker 03-halo: Halo 2 u803 exact-build input integration

Owner folder: `ogxbox/work/03-halo/` (work), `ogxbox/halo2/` (report home).
Target XBE verified: `H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe`,
sha256 `21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd` (re-checked).

Confidence labels used below: VERIFIED = observed XBE bytes / real execution;
INFERENCE = interpretation; UNKNOWN = missing hardware fact.

## 1. Baseline — what the title actually links (VERIFIED)

Halo 2 u803 does NOT import XInput/XGetDevices from the kernel. The entire XID
input driver is STATICALLY LINKED into the XBE, section `XPP`
(va 0x4127A0, vsize 0x8E5C, flags 0x7 = executable + writable + preload).
The .XTLID import table maps XAPI library ids (0x0100xx) to these in-title
functions (xtlid_dump.py cross-checked against `halo v1.5.xbe.orig.map`):

    XTLID id   VA        name (linker map)          prologue bytes
    0x010034   0x413964  XPeekDevices               56 57 FF 15 00 B7 41 00
    0x010033   0x4139A5  XGetDeviceChanges          55 8B EC
    0x010036   0x413A12  XInputOpen                 55 8B EC 51
    0x010037   0x413A68  XInputClose                8B 4C 24 04
    0x01003B   0x413A74  XInputGetCapabilities      55 8B EC
    0x010038   0x413C4C  XInputGetState             53 56
    0x01003A   0x413CBF  XInputSetState             8B 4C 24 04

The full XID driver is present under the same section (XID_Init 0x412B2C,
XID_fOpenDevice 0x414CD2, XID_fOpenEndpoints 0x41421B, XID_ProcessGamepadData
0x4144BD, XID_fSendDeviceReport 0x4149D2, XID_AddDevice 0x414F22, etc.).
XGetDevices is NOT called by the game at all — Halo 2 uses XGetDeviceChanges.

## 2. Calling conventions (VERIFIED from `ret N` + disassembly)

All stdcall (WINAPI). Device type is a `PXPP_DEVICE_TYPE` pointer, not an ordinal —
the game passes `&XDEVICE_TYPE_GAMEPAD_TABLE` = 0x4127D8 (XPP).

    XGetDeviceChanges(PXPP_DEVICE_TYPE, &insertions, &removals) -> BOOL, ret 12
    XInputOpen(PXPP_DEVICE_TYPE, DWORD port, DWORD slot, PXINPUT_POLLING_PARAMS)
               -> HANDLE, ret 16 (NULL on failure, sets last error 0x57)
    XInputClose(HANDLE) -> VOID, ret 4
    XInputGetCapabilities(HANDLE, PXINPUT_CAPABILITIES) -> DWORD, ret 8
    XInputGetState(HANDLE, PXINPUT_STATE) -> DWORD, ret 8
    XInputSetState(HANDLE, PXINPUT_FEEDBACK) -> DWORD, ret 8

Return-value semantics from XBE disassembly: XInputGetState returns error code in
eax — 0 = success, `0x57` (87, invalid/suspended param), `0x48F` (1167,
ERROR_DEVICE_NOT_CONNECTED). XInputGetCapabilities returns `0x48F` when the device
node is absent/removed.

The opaque HANDLE is actually a pointer to the internal open-device state:
XInputGetState reads `[handle]` (device node), `[handle+8]` (packet number),
`[handle+0x14]` (the XINPUT_GAMEPAD), `[handle+0xa3]` (live USB interrupt data).
This is the internal `_XID_OPEN_DEVICE` ("all linked-in") layout — a synthetic
handle must NOT be a bare integer.

## 3. The game's enumeration / hot-plug path (VERIFIED from call xrefs + disasm)

All input code lives in .text at 0x1273C0..0x127A9C. Globals: input flag byte
0x4F2A88, update timestamp 0x4F2A8C, controller HANDLEs `[0x4F2A9C + port*4]`.

    0x1273C0  init: USBD_Init(3, {gamepad 0x4127D8, XHV mic 0x412990, XHV hdph 0x41299C})
    0x127460  update loop: tick-delta -> 0x1275B0 (hotplug) -> 0x127710 (poll state)
    0x1275B0  hotplug:
                XGetDeviceChanges(0x4127D8,&ins,&rem)
                for port 0..3:
                  if rem & 1<<port : XInputClose(handle); handle = 0
                  if ins & 1<<port : handle = XInputOpen(0x4127D8, port, 0, 0)
                                     XInputGetCapabilities(handle,&caps)
                                     type = caps.SubType (1 = gamepad)
    0x127710  poll: for each non-null handle: XInputGetState(handle,&state)
                (then remaps bAnalogButtons[0..7] through table 0x44AD30 into the
                 game's player-input structs; sticks become controller deltas)

Single callers confirmed (find_xrefs.py --calls): XInputOpen @0x12762F,
XInputGetState @0x127744, XInputGetCapabilities @0x127640, XInputSetState
@0x127A68/@0x127A7C, XInputClose @0x127447/@0x127608, XGetDeviceChanges
@0x1275CB/@0x1276EE.

## 4. Minimal interception chain (INFERENCE, from VERIFIED facts above)

A GetState hook ALONE is insufficient, and the reason is structural: the game only
ever calls XInputGetState on HANDLES it received from XInputOpen, and it only calls
XInputOpen when XGetDeviceChanges reports an insertion edge for that port. A
plugged-in Xbox One controller will not satisfy the XID driver's descriptor test
(XID_EnumStage1/XID_AddDevice matches the classic XID vendor/report; the modern pad
speaks a different report format), so the insertion bit is never set.

Minimal chain (6 detours, all in writable+executable XPP — no page-protection change):

    1. XGetDeviceChanges 0x4139A5 — fabricate insertion edge (bit0) for the virtual
       port while the GIP adapter reports a connected device; else passthrough.
    2. XInputOpen 0x413A12 — for the virtual port return a synthetic HANDLE
       (&ampjack_virtual_handles[port]); else passthrough.
    3. XInputGetState 0x413C4C — if handle is a synthetic descriptor, copy the
       22-byte mapped XINPUT_STATE into *pState and return 0; else passthrough.
    4. XInputGetCapabilities 0x413A74 — synthetic handle -> SubType=1, Rumble=0xFFFF.
    5. XInputSetState 0x413CBF — synthetic handle -> rumble (out-of-scope; return 0).
    6. XInputClose 0x413A68 — synthetic handle -> no-op.

Disabled-by-default: with `ampjack_enable_flag == 0` every stub jumps to the
original code, so the game sees the unmodified driver and "no device". The flag and
the four snapshot slots are loader-placed (see contract-gip.md) — no emulator, no
runtime title is engaged this wave.

### Exact overwrite-byte requirements (VERIFIED, re-asserted by verify_hooks.py)

Detour primitive = 5-byte `E9 rel32`. For each site the trampoline must re-run the
full "displaced" instruction bytes verbatim before resuming at `va + displaced_len`
(the chain path):

    site        original 5 bytes      displaced (full instrs)          resume
    0x4139A5    55 8B EC 56 8B        55 8B EC 56 8B 75 08   (7B)      0x4139AC
    0x413A12    55 8B EC 51 8B        55 8B EC 51 8B 4D 08   (7B)      0x413A19
    0x413A68    8B 4C 24 04 E8        8B 4C 24 04 E8 CD 0E 00 00 (9B)  0x413A71
    0x413A74    55 8B EC 83 EC        55 8B EC 83 EC 48      (6B)      0x413A7A
    0x413C4C    53 56 33 DB FF        53 56 33 DB FF 15 00 B7 41 00 (10B) 0x413C56
    0x413CBF    8B 4C 24 04 8D        8B 4C 24 04 8D 81 A3 00 00 00 (10B) 0x413CC9

Note XInputGetState's displaced bytes include `call dword ptr [0x41B700]` (the XID
interrupt preemption lock) — the loader must reproduce it exactly on the chain path.
These byte strings are machine-checked by `verify_hooks.py` (asserts against the XBE).

## 5. Input model and mapping (VERIFIED: XDK header + 30 passing host tests)

`input_model.h/c` encodes the classic-Xbox `XINPUT_GAMEPAD`/`XINPUT_STATE` from
OXDK `xbox.h` lines 576-644 (packed): wButtons (18-byte gamepad), bAnalogButtons[8],
4 × sThumb. Key wire facts confirmed against XBInput.cpp SDK sample: face buttons
A/B/X/Y/Black/White are ANALOG ONLY (no wButtons bits), D-pad/Start/Back/sticks are
wButtons bits, triggers are bAnalogButtons[6..7].

Mapping (modern → classic):
  LB → bAnalogButtons[4]=Black,  RB → bAnalogButtons[5]=White
  A/B/X/Y (digital) → bAnalogButtons[0..3] = 0xFF/0x00   (full-on, >> crosstalk 30)
  LT/RT → bAnalogButtons[6..7]  0..255
  Start/Back/D-pad/stick-clicks → wButtons 0x10/0x20/0x1-8/0x40/0x80
  sticks → sThumbLX/LY/RX/RY  ±32767

## 6. What is implemented vs not

Implemented (this wave, host-verifiable only):
  - `input_model.h/.c`  —  backend-independent snapshot ↔ XINPUT_GAMEPAD mapping.
  - `hook_sites.h`      —  6 hook-site descriptors (constant, machine-checkable).
  - `hook_payload.S`    —  i386 detour stubs; ASSEMBLES with `gcc -m32 -c` (360B
                            text + 28B fixup slots).
  - `verify_hooks.py`   —  re-asserts every hook-site byte/address vs the XBE.
  - `test_mapping.c`    —  30 host tests: mapping, state packing, invalid handle,
                            disconnect, sizes/offsets. PASS.
  - `test_hook.c`       —  runtime E9-detour + stdcall + serve/chain on real i386.
                            PASS (must build with -no-pie -fno-pic: the Xbox title
                            uses absolute addressing; default PIC is not
                            representative and breaks the clone-based fixture).

Not implemented / UNKNOWN (explicitly out of this worker's scope):
  - USB transport for the Xbox One pad (worker 01/02), GIP parsing (worker 04).
  - Actual XBE patch application and code/data VA placement (worker 05).
  - Real Xbox/xemu execution. No hardware claim is made; the host tests exercise
    the mapping and the i386 detour mechanism, NOT USB enumeration or playability.

## 7. Smallest next physical test

1. Load u803 in xemu (or a debug Xbox) with a proactive `ampjack_enable_flag = 0`:
   confirm the title still shows "no controller" (proves passthrough is inert).
2. With flag = 1 and hand-written `ampjack_port_states[0]` + connected[0]=1:
   set a breakpoint at 0x127744 (XInputGetState call) and confirm the game receives
   a synthetic A=0xFF state and reaches the in-game "press Start" prompt.
3. Then attach the worker-04 GIP adapter and stop synthesizing; confirm the adapter
   can raise connected[0] on the actual USB enumeration (worker 01/02 boundary).
