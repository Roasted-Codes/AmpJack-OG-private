/*
 * ogxbox_urb_abi.h — Per-variant URB byte layouts for Halo 2 u803 (Xbox) XAPILIB.
 *
 * AmpJack-OG worker 09 (URB follow-up). This is the COMPILE-CHECKABLE extension
 * of ogxbox_binding_abi.h: the exact per-variant layouts of the title-linked
 * XAPILIB URBs beyond the shared 16-byte header, plus the completion/dispatch
 * contracts. Every offset below is read from the pinned binary
 * (halo2-tu15-u803/default.xbe, sha256 21b207e7...) and cross-checked against the
 * xapilib.lib (XDK 5849) symbol table; verify_urb.py re-derives each from the XBE
 * bytes and asserts it at run time.
 *
 * Confidence:
 *   VERIFIED    - XBE instruction/disassembly bytes and xapilib.lib symbols.
 *   INFERENCE   - semantic reading of a VERIFIED value (naming of a byte).
 *   UNKNOWN     - not established statically (no hardware/emulator).
 *
 * The Xbox URB is a UNION after byte 0x10: each Function code uses a different
 * field layout. This header only pins the variants the transport layer needs.
 */

#ifndef OGXBOX_URB_ABI_H
#define OGXBOX_URB_ABI_H

#include <stdint.h>
#include "ogxbox_binding_abi.h" /* shared canonical callback ABI + data-function code */

#ifdef __cplusplus
extern "C" {
#endif

typedef uint32_t xb_ptr;
typedef uint8_t  xb_byte;

/* ============================================================================
 * 0. URB function codes — VERIFIED from IUsbDevice::SubmitRequest @0x4155BF and
 *    HCD_SubmitRequest @0x417CF2 dispatch (instruction bytes).
 *
 * Public SubmitRequest ladder (0x4155FF..0x41561D): dec;dec->0x02, sub7->0x09,
 * sub0x37->0x40, sub3->0x43, sub0x3f->0x82, sub0x41->0xC3. Everything else
 * (0x05/0x0B/0x0C/0x0D/0x41/0x46/0x4A) falls through to HCD unnormalized.
 *
 * NOTE (correction to worker 07): BULK_OR_INTERRUPT *transfer* is 0x41, NOT 0x09.
 * 0x09 is "open endpoint + allocate TD pool" (HCD 0x09 -> 0x419958, which builds
 * an OHCI endpoint descriptor + periodic TD array). 0x40 is control transfer,
 * 0x41 is the data (bulk/interrupt) transfer; both reach HCD fQueueTransferRequest.
 * ======================================================================== */
enum ogx_urb_function_urb {
    XB_URB_OPEN_ENDPOINT            = 0x02, /* open a specific endpoint (VERIFIED)  */
    XB_URB_SET_FEATURE              = 0x05, /* clear ENDPOINT_HALT (VERIFIED XID)   */
    XB_URB_OPEN_ENDPOINT_POOL       = 0x09, /* open endpoint + TD pool (VERIFIED)   */
    XB_URB_GET_DESCRIPTOR_DEV       = 0x0B, /* HCD @0x419BD2 (VERIFIED)            */
    XB_URB_GET_DESCRIPTOR_IFACE     = 0x0C, /* HCD @0x419D39 (VERIFIED)            */
    XB_URB_CONTROL_TRANSFER         = 0x40, /* control transfer (VERIFIED)          */
    /* XB_URB_BULK_OR_INTERRUPT = 0x41 is declared in the shared binding header. */
    XB_URB_CLOSE_ENDPOINT           = 0x43, /* close a specific endpoint (VERIFIED) */
    XB_URB_OPEN_DEFAULT_ENDPOINT    = 0x82, /* -> 0x415383, rewrites to 0x02        */
    XB_URB_CLOSE_DEFAULT_ENDPOINT   = 0xC3  /* -> 0x415409, rewrites to 0x43        */
};

/* ============================================================================
 * 1. _URB_HEADER — 16 bytes (VERIFIED worker 07 + re-verified here).
 *    Length/Function are single BYTES; +2/+3 reserved. SubmitRequest reads
 *    Function at [urb+1] (`8a 46 01`), CompleteProc at [urb+8] (`39 5e 08`),
 *    CompleteContext at [urb+0xc] (`89 56 0c`).
 * ======================================================================== */
typedef struct ogx_urb_header_urb {
    xb_byte  Length;          /* +0x00 total URB length in bytes (VERIFIED) */
    xb_byte  Function;        /* +0x01 function code (VERIFIED)             */
    xb_byte  Reserved[2];     /* +0x02                                       */
    uint32_t Status;          /* +0x04 result, written on completion         */
    xb_ptr   CompleteProc;    /* +0x08 __stdcall(URB*,PVOID) or NULL         */
    xb_ptr   CompleteContext; /* +0x0C passed to CompleteProc as 2nd arg     */
} ogx_urb_header_urb;

/* ============================================================================
 * 2. OPEN_ENDPOINT — Function 0x02 / 0x82, Length = 0x20 (32 B) (VERIFIED).
 *
 * Consumer OHCD_fOpenEndpoint @0x41782F reads:
 *   +0x14 &0x7f -> ED FunctionAddress bits0-6   (device USB address)
 *   +0x15 (<<7)&0x780 -> ED EndpointNumber bits7-10;  bit0x80 -> direction D
 *   0x15 test 0x80 -> direction; 0x16 -> [esi+0x11] transfer type;
 *   0x17 -> [esi+0x13] interval;  0x1C (word) -> ED MaxPacketSize bits16-26;
 *   0x1E -> direction/speed.  On success writes the pipe into [urb+0x10].
 *
 * SubmitRequest (0x415655, the 0x02 branch) fills for the caller:
 *   +0x14 = device->[5] (function address), +0x18 = &device->[0x18],
 *   +0x1E = device->[4]>>7 (direction).  So the CALLER only sets +0x15/+0x16/
 *   +0x17/+0x1C.  (0x82 -> 0x415383 fills all from the default control EP.)
 * ======================================================================== */
typedef struct ogx_urb_open_endpoint_urb {
    ogx_urb_header_urb Hdr;        /* +0x00 Length=0x20, Function=0x02|0x82  */
    uint32_t EndpointHandle;       /* +0x10 OUT: pipe handle (fOpenEndpoint) */
    xb_byte  FunctionAddress;      /* +0x14 device address (SubmitRequest)   */
    xb_byte  EndpointAddress;      /* +0x15 ep# (low nibble) | dir (0x80)    */
    xb_byte  TransferType;         /* +0x16 0=ctrl 2=bulk 3=interrupt (byte) */
    xb_byte  Interval;             /* +0x17 bInterval                        */
    xb_ptr   TransferBuffer;       /* +0x18 (SubmitRequest sets device buf)  */
    uint16_t MaxPacketSize;        /* +0x1C wMaxPacketSize (word)            */
    xb_byte  Direction;            /* +0x1E (SubmitRequest sets direction)   */
} ogx_urb_open_endpoint_urb;

/* ============================================================================
 * 3. TRANSFER — shared by CONTROL (0x40, Length=0x30) and
 *    BULK_OR_INTERRUPT (0x41, Length=0x28) (VERIFIED).
 *
 * BuildTransfer @0x41A000: [urb+0x14] as DWORD = transfer length (div by
 * endpoint maxpacket -> #TDs). HCD writes #TDs to +0x20, state to +0x22.
 * HCD completion OHCD_fCompleteRequest @0x419329 reads +0x18 as TransferBuffer
 * and flushes it via MmLockUnlockBufferPages (ordinal 175 @[0x41B7C0]) with the
 * length in +0x20, then dispatches the callback. Control setup packet (8 B,
 * bmRequestType/bRequest/wValue/wIndex/wLength) lives at +0x28..+0x2F and is
 * built by the CLASS DRIVER (e.g. XID GET_DESCRIPTOR @0x414FCF), never by HCD.
 * ======================================================================== */
typedef struct ogx_urb_transfer_urb {
    ogx_urb_header_urb Hdr;        /* +0x00 Length 0x30(ctrl)/0x28(data)     */
    uint32_t EndpointHandle;       /* +0x10 pipe handle                       */
    uint32_t TransferLength;       /* +0x14 bytes to move (BuildTransfer)    */
    xb_ptr   TransferBuffer;       /* +0x18 data buffer (read/write)         */
    xb_byte  FlagB0;               /* +0x1C (XID sets 2)                     */
    xb_byte  FlagB1;               /* +0x1D (XID sets 1)                     */
    xb_byte  Direction;            /* +0x1E (VERIFIED worker 07 + XID=0..)   */
    xb_byte  unused_1F;
    uint16_t ByteCount;            /* +0x20 HCD writes #TDs/bytes (VERIFIED) */
    uint16_t State;                /* +0x22 HCD transfer state (VERIFIED)    */
    uint32_t TransferStatus;       /* +0x24 HCD completion status (VERIFIED) */
    xb_byte  SetupPacket[8];       /* +0x28..0x2F control setup (VERIFIED)   */
} ogx_urb_transfer_urb;

/* ============================================================================
 * 4. CLOSE_ENDPOINT — Function 0x43 / 0xC3, Length = 0x1C (28 B) (VERIFIED).
 *
 * XID_CloseEndpointStateMachine @0x4142C6 builds exactly:
 *   [urb]=0x1C, [urb+1]=0xC3|0x43, [urb+8]=CompleteProc, [urb+0xc]=ctx,
 *   [urb+0x10]=EndpointHandle.
 * Consumer OHCD_fCloseEndpoint @0x417C38 reads only [urb+0x10] (the handle),
 * removes it from the schedule, returns STATUS_PENDING (0x40000000); the
 * completion arrives later via the callback. 0xC3 -> 0x415409 (CloseDefault)
 * overwrites +0x10 with device->[8] (default ep handle) and +0x18=0; 0x43
 * (CloseEndpoint) keeps the caller's +0x10.
 * ======================================================================== */
typedef struct ogx_urb_close_endpoint_urb {
    ogx_urb_header_urb Hdr;        /* +0x00 Length=0x1C, Function=0x43|0xC3  */
    uint32_t EndpointHandle;       /* +0x10 pipe to close                    */
    uint32_t ReservedTail[2];       /* +0x14..1B: allocate full declared 0x1C span;
                                    * specific/default close clears +0x18. */
} ogx_urb_close_endpoint_urb;

/* ============================================================================
 * 5. Completion contract (VERIFIED).
 *
 * USBD_CompleteRequest(URB*) __stdcall @0x415120:
 *     mov ecx,[urb+8]; test; push [urb+0xc]; push urb; call ecx; ret 4
 *   => CompleteProc is __stdcall(URB*, void* CompleteContext).
 * Default callback when CompleteProc==NULL is @0x4145C6:
 *     push 0; push 0; push ctx; call [0x41B710](KeSetEvent, ordinal 145); ret 8
 *   i.e. it signals the local KEVENT SubmitRequest installed as CompleteContext.
 * ======================================================================== */
/* ogx_urb_complete_t comes from ogxbox_binding_abi.h: real i386 __stdcall(2). */

/* ============================================================================
 * 6. u803 VAs re-derived here (VERIFIED; see verify_urb.py).
 * ======================================================================== */
#define XB_VA_SUBMIT_REQUEST            0x004155BF
#define XB_VA_OPEN_DEFAULT_ENDPOINT     0x00415383   /* 0x82 handler */
#define XB_VA_CLOSE_DEFAULT_ENDPOINT    0x00415409   /* 0xC3 handler */
#define XB_VA_HCD_SUBMIT_REQUEST        0x00417CF2
#define XB_VA_OHCD_fOpenEndpoint        0x0041782F
#define XB_VA_OHCD_fCloseEndpoint       0x00417C38
#define XB_VA_HCD_BULK_INTERRUPT        0x00419958   /* 0x09 handler */
#define XB_VA_BuildTransfer             0x0041A000
#define XB_VA_OHCD_fProgramInterruptTr  0x0041A36A
#define XB_VA_OHCD_fProgramBulkTr       0x0041A3BD
#define XB_VA_OHCD_fProgramControlTr    0x0041A40A
#define XB_VA_OHCD_fQueueTransferReq    0x0041A502
#define XB_VA_OHCD_fCompleteRequest     0x00419329
#define XB_VA_OHCD_IsrDpc               0x00419830
#define XB_VA_USBD_CompleteRequest      0x00415120
#define XB_VA_DefaultCompleteProc       0x004145C6
#define XB_VA_XID_fOpenEndpoints        0x0041421B
#define XB_VA_XID_NewInterruptData      0x00414377
#define XB_VA_XID_CloseEndpointState    0x004142C6
#define XB_VA_XID_fOpenDevice           0x00414CD2
#define XB_VA_XID_Attach                0x00414F22

/* Kernel import slots + ordinals (VERIFIED from the XBE thunk table 0x41B600): */
#define XB_IMPORT_KeRaiseIrqlToDpcLevel 0x0041B700   /* ordinal 129            */
#define XB_IMPORT_KfLowerIrql           0x0041B6FC   /* ordinal 161            */
#define XB_IMPORT_KeSetEvent            0x0041B710   /* ordinal 145            */
#define XB_IMPORT_KeWaitForSingleObject 0x0041B718   /* ordinal 159            */
#define XB_IMPORT_MmLockUnlockBufferPg  0x0041B7C0   /* ordinal 175            */
#define XB_IMPORT_MmGetPhysicalAddress  0x0041B7BC   /* ordinal 173            */

#ifdef __cplusplus
}
#endif

#endif /* OGXBOX_URB_ABI_H */
