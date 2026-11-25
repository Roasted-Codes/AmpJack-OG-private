/*
 * ogxbox_binding_abi.h — Verified USB-class-binding ABI for Halo 2 u803 (Xbox).
 *
 * AmpJack-OG worker 07 (binding). This is the COMPILE-CHECKABLE VERIFIED SUBSET
 * of the title-linked XAPILIB USB stack: the class-driver registration table,
 * the class-match criteria, the attach/register/completion call signatures, and
 * the _URB header. Every offset/VA/branch below was read directly from the
 * pinned binary (halo2-tu15-u803/default.xbe, sha256 21b207e7...) and from the
 * symbol/relocation record of xapilib.lib (XDK 5849); see verify_binding.py,
 * which re-derives each from the XBE and asserts it at run time.
 *
 * Confidence tags:
 *   VERIFIED    - read from XBE instruction bytes / xapilib.lib symbols.
 *   INFERENCE   - naming/semantic interpretation of a VERIFIED value.
 *   UNKNOWN     - not established (no hardware, no further decomp).
 *
 * Everything here is DATA/ABI, not a driver. There is deliberately no runtime
 * code that calls into the title; offsets are asserted by binding_abi_check.c.
 */

#ifndef OGXBOX_BINDING_ABI_H
#define OGXBOX_BINDING_ABI_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef uint32_t xb_ptr;   /* 32-bit Xbox pointer / handle */
typedef int32_t  xb_long;
typedef uint8_t  xb_byte;

#if defined(_MSC_VER)
#  define XB_STDCALL __stdcall
#  define XB_THISCALL
#elif defined(__i386__)
#  define XB_STDCALL __attribute__((stdcall))
#  define XB_THISCALL __attribute__((thiscall))
#else
#  define XB_STDCALL
#  define XB_THISCALL
#endif

/* ============================================================================
 * 1. URB function codes  (VERIFIED - IUsbDevice::SubmitRequest dispatch @0x4155BF)
 *
 * SubmitRequest decodes the FUNCTION byte (URB+0x01) into these branches:
 *   dec;dec -> je  (==0x02)   sub 0x37 -> je (==0x40)   sub 0x3f -> je (==0x82)
 *   sub 7  -> je  (==0x09)   sub 0x03 -> je (==0x43)   sub 0x41 -> jne(==0xC3)
 * Correction from worker09 byte tracing: 0x09 opens an endpoint with a TD pool;
 * bulk/interrupt DATA transfers are 0x41. Xbox URBs are not Windows URB codes.
 * 0x40 grouped by `test al,0x40` as the async family (control/iso, see below).
 * ======================================================================== */
enum ogxbox_urb_function {
    XB_URB_FUNCTION_2            = 0x02, /* open/setup family (VERIFIED code path) */
    XB_URB_OPEN_ENDPOINT_POOL_LEGACY = 0x09, /* open + TD pool (worker09) */
    XB_URB_BULK_OR_INTERRUPT     = 0x41, /* data transfer (worker09 XID producer) */
    XB_URB_FUNCTION_CONTROL      = 0x40, /* VERIFIED: `test al,0x40` async family   */
    XB_URB_FUNCTION_43           = 0x43, /* VERIFIED code path                       */
    XB_URB_FUNCTION_OPEN_ENDP    = 0x82, /* VERIFIED (0x82 -> call 0x415383)         */
    XB_URB_FUNCTION_CLOSE_ENDP   = 0xC3  /* VERIFIED (0xC3 -> call 0x415409)         */
};

/* ============================================================================
 * 2. _URB_HEADER  (VERIFIED - SubmitRequest @0x4155BF: reads [urb+1] as Function,
 *    [urb+4] as Status, [urb+8] as CompleteProc, [urb+0xC] as CompleteContext;
 *    EndpointHandle at +0x10, TransferBuffer at +0x18, direction byte at +0x1E).
 * NOTE (INFERENCE): Length/Function are single BYTES (not USHORTs) in this XAPILIB
 * header; +2/+3 are reserved. Size = 16 bytes.
 * ======================================================================== */
typedef struct ogx_urb_header {
    xb_byte  Length;          /* +0x00 (VERIFIED: 0x30 for a 48B control URB) */
    xb_byte  Function;        /* +0x01 (VERIFIED: function code, byte)        */
    xb_byte  Reserved[2];     /* +0x02                                          */
    uint32_t Status;          /* +0x04 (VERIFIED)                               */
    xb_ptr   CompleteProc;    /* +0x08 (VERIFIED) __stdcall(URB*,PVOID)         */
    xb_ptr   CompleteContext; /* +0x0C (VERIFIED)                               */
} ogx_urb_header;

/* URB control-transfer variant (VERIFIED offsets from SubmitRequest + darkone83):
 * Hdr, EndpointHandle(+0x10), TransferBuffer(+0x18), direction byte(+0x1E). */
typedef struct ogx_urb_common {
    ogx_urb_header Hdr;      /* +0x00 */
    uint32_t EndpointHandle; /* +0x10 */
    uint8_t  unused_14[4];
    xb_ptr   TransferBuffer; /* +0x18 */
    uint16_t TransferBufferLength_unverified; /* INFERENCE, not byte-verified here */
    uint8_t  Direction;      /* +0x1E (VERIFIED) */
} ogx_urb_common;

/* ============================================================================
 * 3. _PNP_CLASS_ID and _USB_CLASS_DRIVER_DESCRIPTION
 *
 * Match semantics (VERIFIED - USBD_FindClassDriver @0x41517D):
 *     mov dl, LowByte(classId); mov dh, HighByte(classId)
 *     if (dh == desc[+1] && dl == desc[+0]) return desc;
 * So in-memory the description stores the match SECOND byte at +1 (the USB
 * interface class: 0x58 XID, 0x09 hub, 0x08 MS, 0x03 HID — VERIFIED) and the
 * match FIRST byte at +0 (0x82 for those, 0x81 for the hub — VERIFIED bytes;
 * the derivation of this 0x82/0x81 SECOND byte from the USB descriptor is
 * UNKNOWN, it is not the raw bInterfaceSubClass==0x42).
 * ======================================================================== */
typedef struct ogx_pnp_class_id {
    xb_byte SubClassField;   /* low byte  (VERIFIED match vs desc[+0]) */
    xb_byte ClassId;         /* high byte (VERIFIED match vs desc[+1]) */
} ogx_pnp_class_id;

typedef struct ogx_usb_class_driver_description {
    xb_byte MatchByte0;      /* +0x00 (VERIFIED: compared with dl)  */
    xb_byte MatchByte1;      /* +0x01 (VERIFIED: compared with dh)  */
    uint8_t pad[2];          /* +0x02 (0xFF 0xFF observed)           */
    xb_ptr  Register;        /* +0x04 (VERIFIED: called by USBD_Init)*/
    xb_ptr  Attach;          /* +0x08 (VERIFIED: called by LoadClassDriver) */
} ogx_usb_class_driver_description;

/* Register callback: __stdcall, 1 arg = pointer to the IUsbInit temp object.
 * VERIFIED call shape in USBD_Init @0x412D62: `push ecx; call [eax+4]`. */
typedef void (XB_STDCALL *ogx_class_register_t)(xb_ptr iUsbInit);

/* Attach callback: __stdcall, 1 arg = IUsbDevice*. VERIFIED call shape in
 * USBD_LoadClassDriver @0x416B3C: `push esi; call [eax+8]`. */
typedef void (XB_STDCALL *ogx_class_attach_t)(xb_ptr iUsbDevice);

/* Completion callback: __stdcall, 2 args. VERIFIED in USBD_CompleteRequest
 * @0x415120: `push [urb+0xC]; push urb; call [urb+8]`. Runs in the title's
 * USB completion context (INFERENCE: dispatch/lock-held; exact IRQL UNKNOWN). */
typedef void (XB_STDCALL *ogx_urb_complete_t)(xb_ptr urb, xb_ptr context);

/* ============================================================================
 * 4. The call surface a driver uses (VERIFIED signatures + u803 VAs)
 * ======================================================================== */
/* IUsbDevice::SubmitRequest: __thiscall, LONG return, 1 URB* arg. @0x4155BF.
 * The submit path is HCD_SubmitRequest(controller_q, urb) @0x417CF2 (ret 8). */
typedef xb_long (XB_THISCALL *ogx_submit_request_t)(xb_ptr self, xb_ptr urb);

/* USBD_CompleteRequest(URB*) __stdcall @0x415120 (ret 4): dispatches callback. */
typedef void (XB_STDCALL *ogx_usbd_complete_request_t)(xb_ptr urb);

/* ============================================================================
 * 5. Verified u803 VAs (see verify_binding.py for re-derivation) — VERIFIED
 * ======================================================================== */
#define XB_VA_XInitDevices           0x004139A0  /* jmp 0x412D37 (thunk) */
#define XB_VA_USBD_Init              0x00412D37  /* __stdcall(2)          */
#define XB_VA_IUsbInit_Ctor          0x00415076
#define XB_VA_IUsbInit_Process       0x00413072
#define XB_VA_CDeviceTree_Init       0x004131BB
#define XB_VA_CDeviceTree_AllocDev   0x004150D0
#define XB_VA_USBD_FindClassDriver   0x0041517D  /* __stdcall(1) -> desc* */
#define XB_VA_USBD_LoadClassDriver   0x00416B1E  /* desc->Attach fires here */
#define XB_VA_IUsbDevice_SubmitReq   0x004155BF
#define XB_VA_HCD_SubmitRequest      0x00417CF2
#define XB_VA_USBD_CompleteRequest   0x00415120
#define XB_VA_DefaultCompleteProc    0x004145C6  /* set when CompleteProc==NULL */
#define XB_VA_USBD_UnsupportedStatus 0x80000400  /* AddComplete when no match */

/* Class-driver registration table (VERIFIED - walked by USBD_Init @0x412D52 and
 * FindClassDriver @0x41517D). 6 pointer entries, stride 4, NULL-skipped, bounds
 * [begin,end), begin=0x4127B4 end=0x4127CC. XPP section is writable (flags 0x7),
 * so the pointers are patchable in-memory. */
#define XB_VA_CLASS_TABLE_BEGIN 0x004127B4
#define XB_VA_CLASS_TABLE_END   0x004127CC
#define XB_CLASS_TABLE_STRIDE   4u
#define XB_CLASS_TABLE_ENTRIES  6u   /* 6 non-NULL descriptions (VERIFIED) */

/* The 6 descriptions' verified (class, matchbyte0) pairs and callbacks:
   (0x79,0x82)(0x78,0x82) -> Reg 0x41383D Attach 0x41A588
   (0x08,0x82)             -> Reg 0x412A20 Attach 0x413D35   (mass storage/MU)
   (0x58,0x82)             -> Reg 0x412B2C Attach 0x414F22   (XID gamepad)
   (0x03,0x82)             -> Reg 0x412B2C Attach 0x414F22   (HID keyb/mouse)
   (0x09,0x81)             -> Reg 0x413427 Attach 0x418A0B   (hub)
   There is NO FF/47/D0 entry (GIP) — a GIP device matches nothing and the title
   completes it with 0x80000400. */

/* IUsbInit object field offsets (VERIFIED - ctor @0x415076 / UseDefaultCount): */
#define XB_IUSBINIT_PREALLOC_TYPES  0x98  /* __v  prealloc array ptr */
#define XB_IUSBINIT_PREALLOC_COUNT  0x9C  /*      0 => use default count */

#ifdef __cplusplus
}
#endif

#endif /* OGXBOX_BINDING_ABI_H */
