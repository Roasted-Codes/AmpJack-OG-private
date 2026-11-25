# Worker 07 — Halo 2 u803 USB class-driver binding, URB/submit ABI

Owner: ogxbox/research/binding/ + ogxbox/work/07-binding/. Target: u803
default.xbe (SHA256 21b207e7…). Method: symbol/relocation mining of XDK 5849
`xapilib.lib` (COFF) → FID byte-match into the XBE → disassemble → re-assert every
claim via `verify_binding.py`. No hardware, no emulator, no firmware/host changes.

Confidence: VERIFIED = XBE instruction/data bytes or xapilib.lib symbol table;
INFERENCE = reading of a VERIFIED value; UNKNOWN = not established (no hardware).

## Bottom line

The title-linked XAPILIB USB stack is fully recoverable by symbol. The class-driver
registration table, the class-match criteria, the attach contract, the URB header and
the submit/complete call surface are now pinned to exact u803 VAs and instruction
bytes. A GIP (FF/47/D0) device matches nothing in the stock table and is completed
with 0x80000400, so input requires injecting one GIP class-driver description and
hooking the title's existing USBD at two small, writable XPP sites — NOT a second
OHCI/USBD stack. The transport-module step is STOPPED: the interrupt-transfer URB
variant and completion IRQL are not yet byte-proven, so no fake driver is shipped.

## 1. Init → table → enumerate → match → attach (VERIFIED trace)

Entry chain (all VAs are u803 XPP section, flags 0x7 = writable+executable+preload):

- `XInitDevices(dwPreallocTypeCount, PreallocTypes)` __stdcall(2) = thunk at
  **0x4139A0**: `E9 rel32` → **0x412D37** (`USBD_Init`). (Symbol `_XInitDevices@8`;
  FID re-located it; bytes `e9 92 f3 ff ff`.)
- `USBD_Init@8` **0x412D37**:
  1. `call 0x415076` = `IUsbInit::IUsbInit(count, types)` (ctor stores prealloc
     ptr @ obj+0x98, count @ obj+0x9C — VERIFIED `UseDefaultCount @0x412E64`
     tests +0x9C==0).
  2. Walk the class table **[0x4127B4..0x4127CC)**, stride 4, skip NULL, and for
     each entry `mov eax,[edi]; call [eax+4]` → `desc->Register(&IUsbInit)`
     (VERIFIED `USBD_Init @0x412D62-0x412D6C`).
  3. `call 0x413072` = `IUsbInit::Process` (the enumerate/watch loop).
  4. `call 0x41325e` (HCD resource probe) then `CDeviceTree::Init(byte,byte)`
     **0x4131BB** with singleton `g_DeviceTree @0x4908B0`; zero flag @0x4908A8.

- **Registration timing:** Register runs inside `USBD_Init`, *before* `Process`
  → `HCD_EnumHardware`. So a new driver's Register fires before the first
  enumeration — but only if its description is already reachable by the table walk,
  which is compile-time fixed (below). There is no runtime "add driver" API.

- **Table form:** counted-by-bounds, not sentinel. Walk is `for(p=Begin; p<End; p+=4)`
  with hard-coded immediates `Begin=0x4127B4`, `End=0x4127CC` baked into
  `USBD_Init` (0x412D52/0x412D57) AND `FindClassDriver` (0x41517E/0x415183).
  **Writable:** the table lives in XPP (flags 0x7), so entries can be patched and
  the `End` immediate can be bumped. `XAPILIB` builds it from linker-ordered
  sections `.XPP$ClassA`(begin)/`.XPP$ClassXID`/`ClassMU`/`ClassZZHub`/`ClassZZZ`
  (end) — i.e. a section-group idiom, confirmed from lib section names.

- **Match → attach** (VERIFIED `USBD_LoadClassDriver @0x416B1E` + `FindClassDriver`):
  ```
  FindClassDriver(classId) @0x41517D  (stdcall(1), ret 4):
      for (p=0x4127B4; p<0x4127CC; p+=4)
          d = *p; if (!d) continue;
          if ((BYTE)classId     == d->MatchByte0 &&
              (BYTE)(classId>>8) == d->MatchByte1) return d;   // cmp dh,[eax+1]; cmp dl,[eax]
      return 0;
  LoadClassDriver(device /*ecx*/, classId):
      if (device->[0x14] == 0x20) -> AddComplete(0x80000400)   // already-driven gate
      d = FindClassDriver(classId); device->[0x10] = d;
      if (!d) device->AddComplete(0x80000400);                 // USBD unsupported
      else    call d->[+8](device)                              // Attach  (ff 50 08)
  ```
  The six stock descriptions (VERIFIED, read from the XBE table):
  | class | lo-field | Register | Attach | role |
  |---|---|---|---|---|
  | 0x79 | 0x82 | 0x41383D | 0x41A588 | (unidentified; 2nd entry 0x78) |
  | 0x78 | 0x82 | 0x41383D | 0x41A588 | (same driver) |
  | 0x08 | 0x82 | 0x412A20 | 0x413D35 | mass-storage/MU |
  | 0x58 | 0x82 | 0x412B2C | 0x414F22 | XID gamepad |
  | 0x03 | 0x82 | 0x412B2C | 0x414F22 | HID keyboard/mouse |
  | 0x09 | 0x81 | 0x413427 | 0x418A0B | hub |

  `MatchByte1` is the standard USB interface class (0x58/0x09/0x08/0x03 — VERIFIED
  semantics). `MatchByte0` (0x82/0x81) is a second XPP-internal byte; its derivation
  from the raw descriptor (bInterfaceSubClass=0x42 for XID) is **UNKNOWN** — not
  a plain subclass. For a GIP match the exact PNP_CLASS_ID the console computes for
  interface class 0xFF subclass 0x47 must be measured (see §7).

## 2. URB / submit / cancel / close / open (VERIFIED subset + UNKNOWNs)

`IUsbDevice::SubmitRequest(LONG, __thiscall, URB*)` **0x4155BF** (ret 4), dispatching
on the byte `urb->Function` (`mov al,[esi+1]`):

- `_URB_HEADER` (16 B, VERIFIED offsets from SubmitRequest + CompleteRequest):
  `Length +0`, `Function +1` (single bytes), `reserved +2..3`, `Status +4`,
  `CompleteProc +8`, `CompleteContext +0xC`. Then `EndpointHandle +0x10`,
  `TransferBuffer +0x18`, direction byte `+0x1E`, an interrupt/delay byte `+0x29`,
  and a `Status`-reload at +4 on completion.
- Function values handled by SubmitRequest (VERIFIED dispatch sequence):
  0x02, 0x09 (BULK_OR_INTERRUPT, = Windows 0x0009), 0x40 (control; `test al,0x40`
  groups the async family), 0x43, **0x82 OPEN_ENDPOINT** (`call 0x415383`),
  **0xC3 CLOSE_ENDPOINT** (`call 0x415409`).
- Submit tail: `HCD_SubmitRequest(device->[+0xC]+0x18, urb)` **0x417CF2** (ret 8).
- Completion: `USBD_CompleteRequest(URB*)` **0x415120** (ret 4) does
  `CompleteProc(urb, urb->CompleteContext)` — callback is `__stdcall(2)`.
  The default callback installed when the caller leaves +8 NULL is **0x4145C6**
  (`push 0;push 0;push urb; call [0x41B710]; ret 8`), i.e. the stack signals an
  event object rather than a client callback.

UNKNOWN (honest): the exact per-variant byte layouts of `BulkOrInterruptTransfer` /
`OpenEndpoint` / `CloseEndpoint` beyond the shared header+common fields; the
completion **IRQL**/lock context (INFERENCE: title-owned dispatch, non-PASSIVE;
360 analog runs on Usbd's DPC, this xapilib path has not been IRQL-traced); and
cancel (`USBD_DeviceAbortEnum`/pipe cancel @ tree.obj exists by symbol but its
u803 VA and contract are not pinned here).

## 3. Transport module — STOPPED (ABI not complete)

Not shipped: a GIP attach module would need the `BulkOrInterruptTransfer`/
`OpenEndpoint` variant byte layouts and the completion IRQL, which §2 shows are
only partially proven. Shipping a module that guessed those offsets would violate
"no fake functions". Instead `ogxbox/research/binding/ogxbox_binding_abi.h` is the
compile-checkable VERIFIED subset (struct layouts + call signature typedefs + VAs),
and `binding_abi_check.cxx` static-asserts it (both host and `-m32`).

## 4. Tests actually executed

- `python3 ogxbox/work/07-binding/verify_binding.py` → re-reads the XBE, asserts
  every VA/byte claim in §1–2. **ALL CHECKS PASSED** (exit 0).
- `g++ -std=c++11 -Wall -Wextra binding_abi_check.cxx && ./a.out` → layout static
  asserts + FindClassDriver match replay (XID/hub/HID/MS match; GIP FF/47 matches
  nothing). **ALL CHECKS PASSED** (exit 0).
- `g++ -m32 -std=c++11 -fsyntax-only` → clean (true 32-bit pointer ABI).

These prove layout/encoding/calling-convention, not hardware.

## 5. Not: "no kernel USB API ⇒ no firmware patch". Least-invasive route

The kernel has no USB/XInput export surface (worker 02), but that does not make a
firmware patch useless — it makes it unnecessary and strictly more invasive. From
the boundary actually measured here, the least-invasive input route is:

1. Trainer (XBTF, title-ID gated) runs at title entry BEFORE `XInitDevices`
   (0x4139A0) enumerates. Do NOT build a second OHCI stack (title owns 0xFED00000
   MMIO and IRQ1; a second init would reset the controller/steal interrupts).
2. Hook `USBD_LoadClassDriver` **0x416B1E** (or `FindClassDriver` **0x41517D**),
   5-byte E9 detour like worker 03's XInput hooks: if classId == GIP, run GIP
   Attach; else tail-call original. (The table itself is writable, but adding a
   7th entry requires bumping the baked `End=0x4127CC` immediate in two functions —
   the class-match hook is smaller and touches one site.)
3. GIP Attach receives the title's `IUsbDevice*` and must open the interrupt IN/OUT
   endpoints by filling the (partly-proven) `BulkOrInterrupt/OpenEndpoint` URBs and
   calling `SubmitRequest` at 0x4155BF — the missing-variant-layout gap in §2.

## 6. Composite / hub treatment, physical port mapping

- USBD has explicit composite support by symbol: `IUsbInit::GetMaxCompositeInterfaces`
  and `IUsbDevice::GetInterfaceNumber` (lib). LoadClassDriver gates on
  `device->[0x14]==0x20` before matching. A GIP pad is a 3-interface composite
  (data/audio/chatpad) with NO hub (worker 01). Whether the title's enumeration
  reaches interface 0 (FF/47/D0) of that composite and what PNP_CLASS_ID it derives
  is **UNKNOWN** until a diagnostic XBE reads it on real OHCI (worker 06 T1).
- Physical port mapping: XID Attach 0x414F22 derives the port from the XID device
  node array `@0x49080C` (22-byte nodes, count words @0x490808/0x49080A, current
  port byte @0x490858); `IUsbDevice::GetPort()` exists by symbol. Exact port-number
  → front-port wiring for a non-hub GIP device is UNKNOWN on this box.

## 7. Precise remaining gaps (next diagnostic)

1. One real descriptor capture of the owner's pad (class FF/47/D0, 64-B interrupt
   IN/OUT) on a USB 1.1/full-speed host — closes speed + endpoint legality (worker 01/06).
2. A diagnostic XBE (nxdk libusbohci) that runs on the console, enumerates, and prints
   the PNP_CLASS_ID the console computes for the GIP interface + whether a non-hub
   composite reaches LoadClassDriver — this single measurement calibrates MatchByte0/
   MatchByte1 for FF/47 and resolves the composite gate (§6).
3. Pin the `BulkOrInterruptTransfer`/`OpenEndpoint` URB variant layouts and the
   completion IRQL (continue disassembly at 0x415383/0x415409 and their callers;
   FID the functions from tree.obj/usbdev.obj). Only then is §3's module sound.

## Files

- ogxbox/research/binding/ogxbox_binding_abi.h — VERIFIED ABI subset (compile-checkable).
- ogxbox/research/binding/binding_abi_check.cxx — layout/match tests (run, exit 0).
- ogxbox/research/binding/REPORT.md — this document.
- ogxbox/work/07-binding/verify_binding.py — XBE re-derivation + assertion (run, exit 0).
- ogxbox/work/07-binding/xapilib_extract.py, fid_match.py — COFF symbol miner + FID tool.
- ogxbox/work/07-binding/symbols_full.txt — full xapilib.lib symbol dump (evidence).
- ogxbox/work/07-binding/status.json — machine status.
