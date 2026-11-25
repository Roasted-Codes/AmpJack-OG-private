#!/usr/bin/env python3
"""Verify every URB byte-layout / completion / dispatch claim in
ogxbox/research/binding/ogxbox_urb_abi.h against the pinned u803 XBE bytes.

Read-only. Stdlib only. Exits non-zero on any mismatch. Each claim is re-derived
from the XBE here, never from memory.
"""
import struct
import sys

XBE_PATH = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe"
SHA256 = "21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd"

sys.path.insert(0, "/home/roasted/Desktop/Xbox/LAN_Stats/tools")
from xbe_va import XBE, U803_SHA256  # noqa: E402

x = XBE(XBE_PATH, expect_sha256=SHA256)
assert x.sha256 == U803_SHA256 == SHA256

def u8(va):
    return x.read(va, 1)[0]

def bytes_at(va, n):
    return x.read(va, n)

def u32(va):
    return struct.unpack("<I", x.read(va, 4))[0]

FAIL = 0
def check(name, cond, detail=""):
    global FAIL
    ok = "OK  " if cond else "FAIL"
    if not cond:
        FAIL += 1
    print(f"[{ok}] {name} {detail}")

# ---- 1. URB header: Function@+1, CompleteProc@+8, CompleteContext@+0xC -------
sr = bytes_at(0x4155BF, 0x50)
check("SubmitRequest Function byte @ [urb+1]", b"\x8a\x46\x01" in sr)
check("SubmitRequest CompleteProc cmp [urb+8]", b"\x39\x5e\x08" in sr)
check("SubmitRequest default ctx [urb+0xc]", b"\x89\x56\x0c" in sr)

# ---- 2. public dispatch ladder targets --------------------------------------
# 0x82 -> call 0x415383 (e8 @0x415628); 0xC3 -> call 0x415409 (e8 @0x415620)
def rel32_target(va):
    """va = address of the E8 opcode; return the call target."""
    r = struct.unpack("<i", bytes_at(va + 1, 4))[0]
    return (va + 5 + r) & 0xFFFFFFFF
check("0x82 -> OpenDefaultEndpoint 0x415383",
      bytes_at(0x415628, 1) == b"\xe8" and rel32_target(0x415628) == 0x415383,
      hex(rel32_target(0x415628)))
check("0xC3 -> CloseDefaultEndpoint 0x415409",
      bytes_at(0x415620, 1) == b"\xe8" and rel32_target(0x415620) == 0x415409,
      hex(rel32_target(0x415620)))

# ---- 3. OpenDefaultEndpoint 0x415383 rewrites Function to 0x02 ---------------
ode = bytes_at(0x415383, 0x80)
check("0x415383 rewrites [urb+1]=0x02", b"\xc6\x46\x01\x02" in ode)
check("0x415383 fills +0x14 from device->[5]", b"\x8a\x47\x05" in ode and b"\x88\x46\x14" in ode)
check("0x415383 fills +0x1E direction", b"\x88\x46\x1e" in ode)
check("0x415383 clears +0x15", b"\xc6\x46\x15\x00" in ode)
check("0x415383 clears +0x16", b"\xc6\x46\x16\x00" in ode)
check("0x415383 +0x1C = device->[6]", b"\x66\x8b\x47\x06" in ode or b"\x66\x0f\xb6\x47\x06" in ode)
check("0x415383 writes handle [edi+8]", b"\x89\x4f\x08" in ode)
check("0x415383 clears EndpointHandle +0x10", b"\x83\x66\x10\x00" in ode)

# ---- 4. CloseDefaultEndpoint 0x415409 rewrites to 0x43, handle from device[8] ----
cde = bytes_at(0x415409, 0x70)
check("0x415409 rewrites [urb+1]=0x43", b"\xc6\x40\x01\x43" in cde)
check("0x415409 EndpointHandle [urb+0x10]=handle", b"\x89\x78\x10" in cde)
check("0x415409 clears TransferBuffer +0x18", b"\x83\x60\x18\x00" in cde)

# ---- 5. OHCD_fOpenEndpoint 0x41782F consumes open-URB fields ----------------
foe = bytes_at(0x41782F, 0x150)
check("fOpenEndpoint reads +0x16 (type)", b"\x8a\x43\x16" in foe)
check("fOpenEndpoint reads +0x17 (interval)", b"\x8a\x43\x17" in foe)
check("fOpenEndpoint reads +0x1E (direction)", b"\x8a\x43\x1e" in foe)
check("fOpenEndpoint reads +0x1C (maxpacket)", b"\x66\x8b\x43\x1c" in foe)
check("fOpenEndpoint reads +0x14 (function addr)", b"\x8a\x43\x14" in foe)
check("fOpenEndpoint reads +0x15 (endpoint+direction)", b"\x0f\xb6\x43\x15" in foe)
check("fOpenEndpoint writes +0x10 (handle)", b"\x89\x73\x10" in foe)

# ---- 6. BULK_OR_INTERRUPT = function 0x41, TransferLength@+0x14 -------------
# XID_fOpenDevice builds: [urb]=0x28, [urb+1]=0x41, +0x18=buffer, +0x14=length
xod = bytes_at(0x414EB1, 0x20)
check("XID interrupt URB Length=0x28", b"\xc6\x00\x28" in xod)
check("XID interrupt URB Function=0x41", b"\xc6\x43\x53\x41" in xod)
check("XID interrupt URB CompleteProc=0x414377", struct.pack("<I", 0x414377) in xod)
check("XID interrupt URB TransferBuffer@+0x18", b"\x89\x4b\x6a" in xod)
check("XID interrupt URB Length@+0x14", b"\x89\x4b\x66" in xod)
# BuildTransfer @0x41A000 reads [urb+0x14] as transfer length
bte = bytes_at(0x41A000, 0x30)
check("BuildTransfer compares [urb+0x14]==0", b"\x39\x41\x14" in bte)
check("BuildTransfer loads [urb+0x14]", b"\x8b\x41\x14" in bte)
# fQueueTransferRequest routes 0x40/0x41, reads EndpointHandle@+0x10
fqt = bytes_at(0x41A502, 0x90)
check("fQueueTransfer reads EndpointHandle [urb+0x10]", b"\x8b\x7e\x10" in fqt)
check("fQueueTransfer writes TDcount [urb+0x20]", b"\x66\x89\x46\x20" in fqt)

# ---- 7. HCD completion reads TransferBuffer@+0x18, dispatches callback -------
fcr = bytes_at(0x419329, 0x70)
check("fCompleteRequest reads TransferBuffer [urb+0x18]", b"\x8b\x47\x18" in fcr)
check("fCompleteRequest calls MmLockUnlock [0x41b7c0]", b"\xc0\xb7\x41\x00" in fcr)
check("fCompleteRequest -> USBD_CompleteRequest 0x415120",
      bytes_at(0x41939A, 1) == b"\xe8" and rel32_target(0x41939A) == 0x415120,
      hex(rel32_target(0x41939A)))

# ---- 8. USBD_CompleteRequest dispatches CompleteProc(urb, ctx) --------------
cr = bytes_at(0x415120, 0x14)
check("CompleteProc(urb,ctx): push[urb+0xc];push urb;call",
      b"\xff\x70\x0c\x50\xff\xd1" in cr)

# ---- 9. default completion 0x4145C6 = KeSetEvent(ctx,0,0) -------------------
dpc = bytes_at(0x4145C6, 0x11)
check("default complete push 0;push 0;push ctx;call [0x41b710];ret 8",
      dpc.startswith(b"\x6a\x00\x6a\x00") and b"\x10\xb7\x41\x00" in dpc and dpc.endswith(b"\xc2\x08\x00"))

# ---- 10. IRQL: HCD raises to DISPATCH_LEVEL (ordinal 129) / lowers (161) ----
th = dict(x.thunks())
check("import 0x41b700 = ordinal 129 (KeRaiseIrqlToDpcLevel)", th.get(0x41B700) == 129, str(th.get(0x41B700)))
check("import 0x41b6fc = ordinal 161 (KfLowerIrql)", th.get(0x41B6FC) == 161, str(th.get(0x41B6FC)))
check("import 0x41b710 = ordinal 145 (KeSetEvent)", th.get(0x41B710) == 145, str(th.get(0x41B710)))
check("import 0x41b718 = ordinal 159 (KeWaitForSingleObject)", th.get(0x41B718) == 159, str(th.get(0x41B718)))
check("import 0x41b7c0 = ordinal 175 (MmLockUnlockBufferPages)", th.get(0x41B7C0) == 175, str(th.get(0x41B7C0)))
# fCloseEndpoint raises at [0x41b700] and lowers at [0x41b6fc]
fce = bytes_at(0x417C38, 0x60)
check("fCloseEndpoint raises IRQL [0x41b700]", b"\x00\xb7\x41\x00" in fce)
check("fCloseEndpoint lowers IRQL [0x41b6fc]", b"\xfc\xb6\x41\x00" in fce)
check("fQueueTransfer raises IRQL [0x41b700]", b"\x00\xb7\x41\x00" in fqt)
check("fQueueTransfer lowers IRQL [0x41b6fc]", b"\xfc\xb6\x41\x00" in fqt)

# ---- 11. XID close-endpoint URB build (Length 0x1c, Fn 0xC3/0x43, +0x10) ----
xc = bytes_at(0x4142C6, 0x70)
check("XID close URB Length=0x1c", b"\xc6\x00\x1c" in xc)
check("XID close URB Function=0xc3", b"\xc6\x40\x01\xc3" in xc)
check("XID close URB Function=0x43", b"\xc6\x40\x01\x43" in xc)
check("XID close URB +0x10 = handle", b"\x89\x50\x10" in xc)

# ---- 12. XID control GET_DESCRIPTOR setup packet @ +0x28..0x2F -------------
# XID_fOpenDevice control URB: [urb+0x28]=0xa1 (bmRequestType), +0x29=bRequest
xa = bytes_at(0x414E17, 0x30)
check("XID control URB Length=0x30", b"\xc6\x07\x30" in xa)
check("XID control URB Function=0x40", b"\xc6\x43\x53\x40" in xa)
check("XID control setup bmRequestType@+0x28 = 0xa1", b"\xc6\x43\x7a\xa1" in xa)

print("-" * 60)
print(f"RESULT: {'ALL CHECKS PASSED' if FAIL == 0 else str(FAIL) + ' CHECKS FAILED'}")
sys.exit(1 if FAIL else 0)
