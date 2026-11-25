# Worker 13 — title-side USB enumeration (from our own xapilib bytes)

Owner: ogxbox/research/enum/ + work/13-enum/. Method: symbol VAs from our own
built maps (ogxbox/diagnostic/bin/AmpJackProbe.map, ogxbox/gipdriver/bin/AmpJackGip.map)
→ objdump disassembly of the linked `xapilib.lib` code. No hardware, no emulator,
no firmware/host changes; gipdriver untouched.

VAs in this report are from the diagnostic build `AmpJackProbe.exe` (preferred load
0x10000, XPP section); the gipdriver build places the same objects at different VAs
but the instruction bytes are identical. u803 (title) equivalents from worker07/09
are noted in parentheses. Byte citations are the actual disassembled instruction
bytes.

Confidence: VERIFIED = instruction/data bytes in our own XBE/objdump, or the
console log (work/09-diagnostic/real-usb-probe.log). INFERENCE = named reading of a
VERIFIED value. UNKNOWN = not established statically.

## TLDR

1. PNP_CLASS_ID = (USB class byte << 8) | 0x81 or 0x82. The high byte is a real
   descriptor class byte; the low byte is a hardcoded per-code-path marker: 0x81 =
   the class came from the DEVICE descriptor (bDeviceClass), 0x82 = from an
   INTERFACE descriptor (bInterfaceClass). GIP pad => bDeviceClass 0xFF => 0xFF81.
2. 0x81 vs 0x82 is neither interface-class nor interface-count nor "composite";
   it is a source marker. Any pad advertising device class 0xFF gets 0xFF81
   deterministically, so the class id is stable across firmware/pads.
3. At LoadClassDriver time only the DEVICE descriptor is valid. Config and
   interface descriptors are single shared statics the device-level path never
   fetches, so for the GIP pad they alias the previous (XID) device's data.
4. `cmp [device+0x14],0x20` in LoadClassDriver is the "unsupported PORT" gate
   (0x20 = SetExternalPort's sentinel for "port >= 5 / behind a hub"), not an
   "already-driven" flag (a worker07 misread). The GIP pad passes it.
5. No stock entry for 0xFF81 => AddComplete(0x80000400) => re-queued and
   re-enumerated from stage 0 on the SAME device object (it is not freed) => the
   4 observed LoadClassDriver calls. A matching Attach sets device->[0x10] != 0 and
   ends the loop.
6. The stock XID Attach does NOT open endpoints NOR SET_CONFIGURATION: it only
   reads endpoints and submits a GET_DESCRIPTOR(report 0x22) control URB; the
   endpoints are opened later (XID_EnumStage1 -> fOpenDevice -> fOpenEndpoints).
   SET_CONFIGURATION is done by the stack (Stage5) but ONLY on the interface-level
   (bDeviceClass == 0) path — the GIP device-level path SKIPS both config fetch and
   SET_CONFIGURATION, so our Attach must do both itself.
7. Interrupt completion runs at DISPATCH_LEVEL (from the OHCI DPC), and
   XID_NewInterruptData re-submits the SAME URB — our gip_in_complete re-submit is
   correct.

## Q1 — How PNP_CLASS_ID is built, and what 0x81 means

The class id argument given to `USBD_LoadClassDriver` is assembled in TWO source
locations (both write a literal low byte, never derive it):

Device-level path — `USBD_fDeviceEnumStage4` @ 0x2afa9 (u803 ~0x415xxx):
```
2afce: a0 10 5b 02 00    mov    0x25b10,%al      ; bDeviceClass  (device desc @0x25b0c,+4)
2afd3: 3a c3             cmp    %bl,%al
2afd5: 74 34             je     0x2b00b          ; bDeviceClass==0 -> interface path
2afd7: 3c 09             cmp    $0x9,%al
2afd9: 0f 95 c0          setne  %al
2afdc: fe c0             inc    %al              ; al = 1 (hub) / 2 (other)
2afde: 88 06             mov    %al,(%esi)       ; device->[0] = type
2afe0: a0 10 5b 02 00    mov    0x25b10,%al      ; bDeviceClass
2afe5: 88 45 fd          mov    %al,-0x3(%ebp)   ; classId byte1 = bDeviceClass
2afe8: a0 11 5b 02 00    mov    0x25b11,%al      ; bDeviceSubClass
2afed: 88 45 fe          mov    %al,-0x2(%ebp)   ; classId byte2
2aff0: a0 12 5b 02 00    mov    0x25b12,%al      ; bDeviceProtocol
2aff5: 88 45 ff          mov    %al,-0x1(%ebp)   ; classId byte3
2aff8: c6 45 fc 81       movb   $0x81,-0x4(%ebp) ; classId byte0 = 0x81   <-- LITERAL
2affc: ff 75 fc          push   -0x4(%ebp)
2afff: 8b ce             mov    %esi,%ecx        ; device
2b001: e8 94 fb ff ff    call   0x2ab9a         ; USBD_LoadClassDriver
```

Interface-level path — `USBD_DeviceEnumStage6` @ 0x2aca9 and `AddComplete` @ 0x2aa0e
(for a composite's next interface), where the class bytes come from the interface
descriptor (offset +5/+6/+7) and the low byte is 0x82:

Stage6 @ 0x2ad9e:
```
2ada3: 8a 40 02          mov    0x2(%eax),%al     ; bInterfaceNumber
2adac: 8a 48 05          mov    0x5(%eax),%cl     ; bInterfaceClass
2adb1: 88 4d 0d          mov    %cl,0xd(%ebp)     ; classId byte1
2adb4: 8a 48 06          mov    0x6(%eax),%cl     ; bInterfaceSubClass
2adb7: 8a 40 07          mov    0x7(%eax),%al     ; bInterfaceProtocol
2adc0: c6 45 0c 82       movb   $0x82,0xc(%ebp)   ; classId byte0 = 0x82   <-- LITERAL
2adc4: ff 75 0c          push   0xc(%ebp)
2adc9: e8 cc fd ff ff    call   0x2ab9a          ; LoadClassDriver
```
(AddComplete's twin is at 0x2ab15 `c6 45 08 82` then `call 0x2ab9a` @0x2ab1e.)

The match itself — `USBD_FindClassDriver` @ 0x29da5 (u803 0x41517D):
```
29da6: b8 14 80 02 00    mov    $0x28014,%eax     ; BeginClassDescriptionTable
29dab: be 20 80 02 00    mov    $0x28020,%esi     ; EndClassDescriptionTable
...
29dc0: 3a 70 01          cmp    0x1(%eax),%dh     ; classId>>8  == desc->MatchByte1
29dc3: 75 04             jne    ...
29dc5: 3a 10             cmp    (%eax),%dl        ; classId&0xff == desc->MatchByte0
29dc7: 74 0d             je     found
```

So: `MatchByte1` = the USB class byte (bDeviceClass for 0x81 entries, bInterfaceClass
for 0x82 entries). `MatchByte0` = the 0x81/0x82 source marker. The two bytes are
matched independently (dh then dl), so a table entry (class, source) uniquely keys
the match.

Meaning of 0x81 (VERIFIED constant, INFERENCE on intent):
- It is NOT bInterfaceClass (the GIP interface class is FF/47/D0, and on the aliased
  line it was 0x58).
- It is NOT the interface count (niface read 1 on both the XID and GIP lines).
- It is a code-path constant: 0x81 = "class taken from device descriptor"
  (bDeviceClass), 0x82 = "class taken from an interface descriptor"
  (bInterfaceClass). This is why the stock table is {hub 0x09/0x81} vs
  {XID 0x58/0x82, HID 0x03/0x82, MS 0x08/0x82, ?/0x79 and 0x78}.
- Stability: 0xFF81 is derived purely from (a) the literal 0x81 in Stage4 and
  (b) bDeviceClass==0xFF on the wire. A GIP pad must advertise 0xFF/0x47/0xD0 on
  the device descriptor (the USB "vendor-specific / class is in the interfaces"
  code, and the GIP descriptor convention), so the class id is deterministic and
  stable across pads/firmware. It does NOT depend on the pad's interface layout.

Correction to worker07: `GetClassId` is the post-attach accessor, not the producer.
`IUsbDevice::GetClassId` @ 0x2a132 reads `device->[7]`; if it == 0xFF it returns
0xFFFFFFFF; otherwise it loads the already-stored class description DWORD from
`device->[0x10]` and overwrites its low byte with `device->[7]`. It dereferences
device->[0x10], which only LoadClassDriver sets (`89 46 10`, 0x2abb3) — so it is
only meaningful AFTER a match. (This is exactly why the diagnostic does not call it
at capture time; see work/09-diagnostic/REPORT.md.)

## Q2 — Which descriptors are fetched before LoadClassDriver; why the alias

The three getters return SHARED STATICS, not per-device storage (VERIFIED):

```
GetDeviceDescriptor      @ 0x29edf:  b8 0c 5b 02 00   mov $0x25b0c,%eax ; ret
GetConfigurationDescriptor @ 0x29ee5: b8 14 5b 02 00   mov $0x25b14,%eax ; ret
GetInterfaceDescriptor   @ 0x29eeb:  a1 64 5b 02 00   mov 0x25b64,%eax  ; ret  (a cursor)
```

- 0x25b0c = single 18-byte device-descriptor buffer (bDeviceClass at +4 = 0x25b10).
- 0x25b14 = single config-descriptor buffer (stage 6 walks it).
- [0x25b64] = running pointer to the "current interface descriptor" cursor inside
  that config buffer.

Enumeration order (VERIFIED from the tree.obj state machine, stage byte @0x25b00,
dispatch table in `USBD_DeviceEnumTimerProc` @ 0x2b0f4):
0. port reset / debounce (Stage0 @0x2a5db);
1. GET_DESCRIPTOR(device) — fills 0x25b0c — then address assign
   (Stage1/2; Stage2 @0x2abfc already reads bMaxPacketSize0 `0x25b13` and requires
   `<= 0x40`, so the device descriptor is present and valid here);
2. class match. Two branches:
   - bDeviceClass != 0 (hub 0x09, GIP 0xFF): Stage4 @0x2afd7 does the match
     IMMEDIATELY, from the DEVICE descriptor only. NO config fetch, NO
     SET_CONFIGURATION.
   - bDeviceClass == 0 (XID/HID/MS): Stage4 @0x2b00b opens the default control
     endpoint (URB len 0x20 fn 0x02) then GET_DESCRIPTOR(config, type 2, 0x50 bytes)
     with setup `80 06 00 02 00 00 50 00` (@0x2b0b9..0x2b0c7), completes into
     Stage5 @0x2aef0 which issues SET_CONFIGURATION (`c6 05 b5 5a 02 00 09` =
     setup bRequest 0x09 @0x2af73), completing into Stage6 @0x2aca9 which parses
     the interface descriptors (the "find bDescriptorType==4" loop @0x2acfe) and
     calls LoadClassDriver.

When GetInterfaceDescriptor becomes valid: only after the interface-path
GET_DESCRIPTOR(config) completes and Stage6 has advanced the cursor [0x25b64] to an
interface descriptor (bDescriptorType==4). For a 0xFF81 device that path never runs,
so [0x25b64] and 0x25b14 retain whatever the PREVIOUS device (the stock XID pad,
class 0x5882) left there. That is exactly the aliasing the console log records
(ifclass 0x58 / ifsub 0x42 / nep 2 / niface 1 / vendor 0x0209 / product 0x0020 on the
0xFF81 lines). The device descriptor (0x25b0c) was refreshed, so dclass/dsub/dproto
(FF/47/D0) are correct. VERIFIED mechanism, matching the CAVEAT in
REAL-CONSOLE-RESULT.md.

## Q3 — Why LoadClassDriver ran 4 times; what an unmatched device does

Failure chain (VERIFIED):
- `USBD_LoadClassDriver` @ 0x2ab9a: `SetExternalPort` (@0x2ab9d) → gate
  `cmp dword [esi+0x14],0x20` (@0x2aba2) → `FindClassDriver` (@0x2abac) → store
  `device->[0x10] = desc` (@0x2abb3) → if desc `call [desc+8]` Attach (@0x2abb9),
  else push 0x80000400 / `AddComplete` (@0x2abbe..0x2abc5).
- `AddComplete` @ 0x2aa0e: reads `device->[0]` (type). For the GIP pad Stage4 wrote
  device->[0]=2 (@0x2afde, `setne/inc`), so it takes the type 1/2 branch
  (`cmp $0x2` @0x2aa61 -> 0x2ab74), which falls to `cmp 0,[ebp+8]` (status < 0),
  `jge 0x2ab8c` -> `call 0x2a70a` = `USBD_DeviceEnumNextPending` (@0x2ab8e).
- `USBD_DeviceEnumNextPending` @0x2a70a: dequeues `device` from the pending list
  (head @0x25b04), then if the retry deadline (device+0x18/0x1c vs KeQuerySystemTime)
  has passed it calls `USBD_DeviceEnumStage0` @0x2a5db (@0x2a791) — i.e. re-enumerates
  the SAME device from scratch; otherwise it re-arms a timer and returns.

What happens to an unmatched device:
- Types 1/2 (hub / device-level class) are NOT freed, NOT closed, and NOT dropped
  from the pending list in AddComplete; only type-5 (a composite's interface child)
  with device->[0x10]==0 is released (`test [esi+0x10]` @0x2aaaa -> RemoveChild/
  FreeDevice @0x2ab0..0x2abd). So a 0xFF81 device (type 2, no table entry) stays on
  the list and is re-enumerated on each timer/watchdog cycle -> repeated
  LoadClassDriver(0xFF81). The 4 attempts (seq 5,7,8,9) are four such cycles for the
  same object 0x800004ec.

Does a matching Attach stop it: yes. LoadClassDriver writes a non-NULL
device->[0x10] BEFORE calling Attach (@0x2abb3), so afterwards AddComplete's
`test [esi+0x10],0 / jne` (@0x2aaaa) takes the claimed path (no free), and — for a
real class driver — the Attach-submitted URB chain (e.g. XID's GET_DESCRIPTOR 0x22
via XID_AddDevice, then XID_EnumStage1 -> fOpenDevice -> fOpenEndpoints -> interrupt
URBs) transitions the device out of the enumeration pending list into a connected
state. The XID pad shows exactly ONE LoadClassDriver call (seq 3). (The precise
"device leaves the pending list" transition is INFERENCE; the non-free and the single
XID match are VERIFIED.)

## Q4 — What the stock XID Attach does, in order; what it must return

`XID_AddDevice` @ 0x29b4a (u803 0x414F22) is the XID Attach. Full order:

1. Allocate a free XID device node in the global node array `XID_Globals.devices`
   @0x259cc (22-byte nodes), guarded by count @0x259ca vs limit @0x259c8; overflow
   -> `AddComplete(0x80000100)` (@0x29c8c..0x29c95).
2. `device->SetExtension(node)` @0x29e3e (stores node ptr at device+0x1c) — the
   extension is how the XID completion callbacks recover their node/context.
3. Record: node->[0]=device, node->[4] flags |= 1 (in-use), interface number
   `GetInterfaceNumber` @0x29e63 stored at node->[5].
4. Read the endpoints by descriptor, NOT by hardcoded address:
   `GetEndpointDescriptor(device, 0, 1 /*IN*/, 3 /*interrupt*/)` @0x29bbf ->
   bEndpointAddress (node->[8]) + wMaxPacketSize (node->[6]);
   then `GetEndpointDescriptor(device, 0, 0 /*OUT*/, 3)` @0x29bd6 -> node->[9]/[7]
   (zeroed if absent).
5. Build a CONTROL URB (Length 0x30, Function 0x40) with:
   `CompleteProc = XID_EnumStage1` (@0x29c05 -> 0x29806), context = node,
   TransferBuffer 0x259d4, setup bytes `c1 06 42 00 <iface#> 00 10 00`
   (@0x29c3e..0x29c6b) = IN|class|interface, GET_DESCRIPTOR, wValue 0x4200 (XID
   report descriptor, type 0x42), wIndex = interface number, wLength 0x10.
6. `XID_SetEnumWatchdog` (@0x29c77 -> 0x28fcf) then `SubmitRequest(device, &urb)`
   (@0x29c83). Returns void (`ret 4`). The endpoint OPEN and the interrupt URBs are
   done LATER, in XID_EnumStage1 -> fOpenDevice -> fOpenEndpoints, driven by this
   URB's completion — NOT inside Attach.

What the stack needs from Attach (the claim contract):
- Attach is `__stdcall(device)`, returns nothing (void). The "claim" is the
  non-NULL `device->[0x10]` that LoadClassDriver stored BEFORE the call. There is no
  return-code check; Attach does not need to write device->[0x14] or any status.
- On success the driver is expected to move the device out of the enum state (its
  submitted URBs / SetExtension do the bookkeeping). Returning with nothing set
  leaves the device claimed-but-idle, hence the stack treating device->[0x10]!=0 as
  "driver is in charge".

What the stack already did vs did NOT do before Attach:
- Did: port reset, GET_DESCRIPTOR(device), USB address assignment.
- Did (interface path only): GET_DESCRIPTOR(config) + SET_CONFIGURATION.
- Did NOT (device-level / 0xFF81 path): config fetch, SET_CONFIGURATION, any
  endpoint open. Therefore for the GIP pad our Attach must perform config fetch +
  SET_CONFIGURATION itself (below).

## Q5 — Completion IRQL and re-submit

DISPATCH_LEVEL: CONFIRMED (structure VERIFIED in worker09, carried forward and
re-confirmed here via the same XBE). Completion is delivered from the OHCI DPC:
OHCD_IsrDpc -> OHCD_fCompleteRequest -> USBD_CompleteRequest @0x29d48 ->
CompleteProc. The HCD submit/close paths bracket their critical sections with
KeRaiseIrqlToDpcLevel (ordinal 129 @ import 0x1e7d0-family slot) / KfLowerIrql
(ordinal 161). CompleteProc is `__stdcall(URB*, void* context)`. Exact numeric IRQL
value (2) remains INFERENCE (no hardware capture).

Re-submit: the stock XID interrupt-IN completion `XID_NewInterruptData` @ 0x291e4
(u803 0x414377) re-submits the SAME URB:
```
29212: ff 50 24          call *0x24(%eax)      ; device->[0xe] vtable -> XID_ProcessGamepadData
29223: 0f b6 47 0c       movzbl 0xc(%edi),%eax  ; device->[0xc] (report/transfer size)
29227: 89 46 14          mov  %eax,0x14(%esi)   ; urb->TransferLength = size  (RESET)
2922a: f6 83 a2 00 00 00 08  testb $0x8,0xa2(%ebx) ; openDevice still open?
29231: 74 08             je   0x2923b            ; no -> return (no re-submit)
29233: 8b 0f             mov  (%edi),%ecx
29235: 56                push  %esi
29236: e8 93 0f 00 00    call 0x2a1ce            ; SubmitRequest(device, urb)  <-- SAME URB
```
It resets the transfer length from `device->[0xc]` and re-submits the original URB,
guarded by the open flag (skip on unplug/stall: `testb $1,0xa2(%ebx)` @0x291e9 and
`test $2,device->[4]` @0x291f8). On a negative URB status it builds a 0x40
clear-stall control URB instead (0x291da..0x2929e, CompleteProc XID_ClearInputStall
@0x292a0). So our gip_in_complete's "ring push then re-submit g_in_urb" exactly
mirrors the stock pattern and is DPC-safe (ring only).

## Required changes to ogxbox/gipdriver Attach (do not modify gipdriver here)

1. STOP opening endpoint 0x82/0x02 immediately. The GIP match is the DEVICE-level
   path (0xFF81): the stack has fetched only the device descriptor and has NOT
   issued SET_CONFIGURATION (VERIFIED — Stage5's SET_CONFIGURATION and Stage6's
   interface walk run only on the bDeviceClass==0 branch). Opening endpoints now
   reads stale/garbage endpoint descriptors and targets an unconfigured device.
2. In Attach, first open the DEFAULT control endpoint (URB fn 0x82), then issue
   GET_DESCRIPTOR(CONFIGURATION) via a 0x40 control URB (setup `80 06 00 02 00 00
   wTotalLength`) — model Stage4 @0x2b00b..0x2b0c7.
3. From the fetched config descriptor, locate the GIP interface
   (bInterfaceClass==0xFF) and its interrupt IN/OUT descriptors (bDescriptorType==5),
   then SET_CONFIGURATION via a 0x40 control URB (setup bmRequestType 0x00,
   bRequest 0x09, wValue = bConfigurationValue) — model Stage5 @0x2af73.
   Alternatively: after SET_CONFIGURATION, let GetEndpointDescriptor(device, iface,
   dir, 3) supply the addresses/packet sizes (it walks the now-valid config buffer).
4. THEN OPEN_ENDPOINT (fn 0x02) for IN/OUT using bEndpointAddress (offset +2) and
   wMaxPacketSize (offset +4) from the endpoint descriptor, TransferType 3
   (interrupt), interval from bInterval — not hardcoded 0x82/0x02/64/4. (Mirror
   XID's GetEndpointDescriptor reads @0x29bbf/@0x29bd6.)
5. Do endpoint opens and the first interrupt IN submission ASYNCHRONOUSLY (drive
   them from a completion callback / KEVENT wait, as XID does via XID_EnumStage1 ->
   fOpenDevice -> fOpenEndpoints -> XID_fWaitForUrb), rather than assuming
   SubmitRequest has synchronously filled EndpointHandle/Status by the time it
   returns.
6. The FindClassDriver hook + description shape are already correct (MatchByte0
   0x81, MatchByte1 0xFF, Attach = gip_attach). Attach must leave device->[0x10]
   non-NULL (LoadClassDriver already set it) and return void. Keep the persistent IN
   URB re-submit and DPC-safe ring (Q5) as-is.

## Files

- ogxbox/research/enum/REPORT.md — this document.
- Sources of the VA/byte claims: ogxbox/diagnostic/bin/AmpJackProbe.exe + .map and
  ogxbox/gipdriver/bin/AmpJackGip.exe + .map (objdump disassembly), consistent with
  ogxbox/work/07-binding/symbols_full.txt and the console log
  ogxbox/work/09-diagnostic/real-usb-probe.log.
- work/13-enum/ notes (git-excluded) hold the raw disassembly dump referenced here.
