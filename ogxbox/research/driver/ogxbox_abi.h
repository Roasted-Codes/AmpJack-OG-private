/*
 * ogxbox_abi.h - Platform ABI map for the original Xbox input (USB/OHCI/XID/XInput) stack.
 *
 * AmpJack OG research, worker 02 (driver). This is an ABI MAP ONLY: verified
 * structure layouts, offsets, hardware constants, kernel export ordinals and
 * the title-linked XAPI (XInput) call signatures. There is deliberately NO
 * driver/backend code here and nothing that "calls" these ABI points at runtime;
 * it exists so the parent/integrator can compile-check layout assumptions against
 * the sources they were read from.
 *
 * Confidence tags:
 *   VERIFIED   - read directly from source bytes in the pinned revisions below.
 *   INFERENCE  - interpretation of a VERIFIED source, not observed on hardware.
 *
 * Pinned sources (immutable revision + path):
 *   - Cxbx-Reloaded 585c49a (github.com/Cxbx-Reloaded/Cxbx-Reloaded):
 *       src/core/hle/XAPI/Xapi.h                             (XAPI structs/signatures)
 *       src/devices/usb/XidGamepad.cpp                       (XID descriptor + report wire format; ack. XQEMU)
 *       src/devices/usb/OHCI.h .cpp                          (OHCI register map, base/IRQ usage)
 *       src/devices/usb/USBDevice.cpp, src/devices/PCIDevice.h (USB0_BASE=0xFED00000, SIZE=0x1000, PCI id, IRQ)
 *       src/core/kernel/exports/KernelThunk.cpp              (379-entry kernel export table, BY ORDINAL)
 *       import/OpenXDK/include/xinput/ohci.h                 (packed HCCA / ohci_regs / ED / TD)
 *       import/OpenXDK/include/xinput/xinputdetails.txt      (only 3 kernel externs used by the OHCI/XID driver)
 *   - halo2-decomp-bundle (Bungie matched source), matched-src/unknown_1248b0.cpp: title's XInput layer.
 *
 * All layout assertions are re-checked by abi_check.cxx (see build output).
 */

#ifndef OGXBOX_ABI_H
#define OGXBOX_ABI_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---------------------------------------------------------------------------
 * x86 words as used by the XDK headers (`xbox::` typedefs in Cxbx)
 * ----------------------------------------------------------------------- */
typedef uint8_t  byte_xt;    /* xbox::byte_xt  */
typedef uint16_t word_xt;    /* xbox::word_xt  */
typedef int16_t  short_xt;   /* xbox::short_xt */
typedef uint32_t dword_xt;   /* xbox::dword_xt */
typedef uint32_t ulong_xt;   /* xbox::ulong_xt */
typedef uint16_t ushort_xt;  /* xbox::ushort_xt */
typedef uint8_t  uchar_xt;   /* xbox::uchar_xt */

/* Xbox ABI is strictly 32-bit: pointers/handles are 4 bytes. */
typedef uint32_t xh_handle;   /* HANDLE / PVOID on Xbox   */
typedef uint32_t xh_ptr;      /* generic 32-bit pointer   */

/* XAPI exports use the Windows stdcall convention on x86. */
#if defined(_MSC_VER)
#  define OGXBOX_STDCALL __stdcall
#elif defined(__i386__)
#  define OGXBOX_STDCALL __attribute__((stdcall))
#else
#  define OGXBOX_STDCALL
#endif

/* ---------------------------------------------------------------------------
 * 1. KERNEL EXPORT BOUNDARY (VERIFIED - Cxbx KernelThunk.cpp, ordinal == index)
 *
 * The 379-entry kernel thunk table contains NO XInput/USB/OHCI/USBD symbol.
 * Input is NOT a kernel export. The primitives a title-linked USB/XID driver
 * needs ARE kernel exports, at these ordinals (xboxkrnl.lib imports by ordinal):
 * ----------------------------------------------------------------------- */
enum ogxbox_kernel_export {
    KERN_KeConnectInterrupt           = 98,   /* 0x0062 */
    KERN_HalEnableSystemInterrupt     = 43,   /* 0x002B */
    KERN_MmAllocateContiguousMemory   = 165,  /* 0x00A5 */
    KERN_MmAllocateContiguousMemoryEx = 166,  /* 0x00A6 */
    KERN_MmFreeContiguousMemory       = 171,  /* 0x00AB */
    KERN_MmGetPhysicalAddress         = 173,  /* 0x00AD */
    KERN_MmLockUnlockBufferPages      = 175,  /* 0x00AF */
    KERN_MmMapIoSpace                 = 177,  /* 0x00B1 */
    KERN_MmUnmapIoSpace               = 183,  /* 0x00B7 */
};

/* The only external (kernel) calls the OpenXDK-independent XID/OHCI driver
 * makes, per xinputdetails.txt: MmAllocateContiguousMemory,
 * MmLockUnlockBufferPages, MmGetPhysicalAddress. INFERENCE: the whole OHCI +
 * USBD + hub + XID stack otherwise lives in the caller (title). */

/* ---------------------------------------------------------------------------
 * 2. OHCI HARDWARE (VERIFIED - Cxbx PCIDevice.h / USBDevice.cpp / OHCI.cpp)
 * ----------------------------------------------------------------------- */
#define OGXBOX_USB0_BASE 0xFED00000u  /* OHCI MMIO base      */
#define OGXBOX_USB0_SIZE 0x1000u      /* MMIO window size    */
#define OGXBOX_USB_PCI_VENDOR 0x10DEu /* PCI_VENDOR_ID_NVIDIA */
#define OGXBOX_USB_PCI_DEVICE 0x01C2u
#define OGXBOX_USB_PCI_PATH  "pci.0:02.0"  /* INFERENCE: Cxbx models it here */
#define OGXBOX_USB_IRQ 1             /* HalSystemInterrupts[1] drives it     */
#define OGXBOX_OHCI_ROOT_PORTS 4     /* 4 controller ports                   */

/* OHCI HCCA: 256 bytes, 256-byte aligned (OHCI 1.0 + OpenXDK xinput/ohci.h) */
typedef struct ogx_ohci_hcca {
    uint32_t int_table[32];   /* interrupt ED table */
    uint16_t frame_no;
    uint16_t pad1;
    uint32_t done_head;
    uint8_t  reserved[120];  /* 128+2+2+4+120 = 256 bytes (OHCI 1.0) */
} ogx_ohci_hcca;

/* Standard OHCI operational registers (matches OHCI 1.0 and the OpenXDK
 * ohci_regs; Cxbx's OHCI_Registers merges HcInterruptEnable/Disable into one
 * `HcInterrupt`, which is an emulator simplification). 4 root ports on Xbox. */
typedef struct ogx_ohci_regs {
    uint32_t revision;          /* 0x00 */
    uint32_t control;           /* 0x04 */
    uint32_t cmdstatus;         /* 0x08 */
    uint32_t intrstatus;        /* 0x0C */
    uint32_t intrenable;        /* 0x10 */
    uint32_t intrdisable;       /* 0x14 */
    uint32_t hcca;              /* 0x18 */
    uint32_t ed_periodcurrent;  /* 0x1C */
    uint32_t ed_controlhead;    /* 0x20 */
    uint32_t ed_controlcurrent; /* 0x24 */
    uint32_t ed_bulkhead;       /* 0x28 */
    uint32_t ed_bulkcurrent;    /* 0x2C */
    uint32_t donehead;          /* 0x30 */
    uint32_t fminterval;        /* 0x34 */
    uint32_t fmremaining;       /* 0x38 */
    uint32_t fmnumber;          /* 0x3C */
    uint32_t periodicstart;     /* 0x40 */
    uint32_t lsthresh;          /* 0x44 */
    uint32_t rh_descriptor_a;   /* 0x48 */
    uint32_t rh_descriptor_b;   /* 0x4C */
    uint32_t rh_status;         /* 0x50 */
    uint32_t rh_portstatus[OGXBOX_OHCI_ROOT_PORTS]; /* 0x54 */
} ogx_ohci_regs;

/* OHCI endpoint descriptor (16 bytes) and transfer descriptor (16 bytes) */
typedef struct ogx_ohci_ed {   /* VERIFIED OpenXDK s_Endpointdescriptor / Cxbx OHCI_ED */
    uint32_t flags;             /* FunctionAddress/EndpointNumber/Speed/... */
    uint32_t tailptr;
    uint32_t headptr;
    uint32_t next_ed;
} ogx_ohci_ed;

typedef struct ogx_ohci_td {   /* VERIFIED OpenXDK s_Transferdescriptor / Cxbx OHCI_TD */
    uint32_t flags;             /* BufferRounding/Direction/DelayInterrupt/ConditionCode/... */
    uint32_t buffer_ptr;        /* current buffer pointer */
    uint32_t next_td;
    uint32_t buffer_end;
} ogx_ohci_td;

/* OHCI transport viability (INFERENCE from XID descriptor, below):
 * the XID gamepad uses interrupt endpoints, not bulk. OHCI control (setup) +
 * interrupt (polled input/rumble) transfers are the transport path; bulk and
 * isochronous ED lists exist but are NOT used by the gamepad class. */

/* ---------------------------------------------------------------------------
 * 3. XID DEVICE / WIRE PROTOCOL (VERIFIED - Cxbx XidGamepad.cpp, ack. XQEMU)
 * ----------------------------------------------------------------------- */
#define OGXBOX_USB_CLASS_XID  0x58   /* bInterfaceClass  */
#define OGXBOX_USB_DT_XID     0x42   /* XID-specific descriptor type */
#define OGXBOX_XID_GAMEPAD_VID 0x045Eu
#define OGXBOX_XID_GAMEPAD_PID 0x0202u /* Controller S (Duke = 0x0200) */
#define OGXBOX_XID_GAMEPAD_BCD_USB 0x0110u
#define OGXBOX_XID_MAX_INPUT_REPORT  20
#define OGXBOX_XID_MAX_OUTPUT_REPORT 6
#define OGXBOX_XID_EP_IN  0x82        /* 0x80 | 2 : interrupt IN  */
#define OGXBOX_XID_EP_OUT 0x02        /* 2          : interrupt OUT */
#define OGXBOX_XID_HID_SET_REPORT 0x09
#define OGXBOX_XID_HID_GET_REPORT 0x01
#define OGXBOX_XID_GET_CAPABILITIES 0x01

/* XID class descriptor (16 bytes, returned by a vendor GET_DESCRIPTOR 0x4200) */
typedef struct ogx_xid_desc {
    uint8_t  bLength;
    uint8_t  bDescriptorType;   /* 0x42 */
    uint16_t bcdXid;            /* 0x100 */
    uint8_t  bType;             /* 1 */
    uint8_t  bSubType;          /* 1 */
    uint8_t  bMaxInputReportSize;   /* 20 */
    uint8_t  bMaxOutputReportSize;  /* 6  */
    uint16_t wAlternateProductIds[4];
} ogx_xid_desc;

/* Input report (20 bytes, GET_REPORT 0x0100 and interrupt-IN payload) */
typedef struct ogx_xid_input_report {
    uint8_t  bReportId;
    uint8_t  bLength;
    uint16_t wButtons;              /* digital buttons */
    uint8_t  bAnalogButtons[8];     /* X,Y,A,B,white,black,L/R trigger */
    int16_t  sThumbLX;
    int16_t  sThumbLY;
    int16_t  sThumbRX;
    int16_t  sThumbRY;
} ogx_xid_input_report;

/* Output report (6 bytes, SET_REPORT 0x0200 and interrupt-OUT payload) */
typedef struct ogx_xid_output_report {
    uint8_t  report_id;
    uint8_t  length;
    uint16_t left_actuator_strength;
    uint16_t right_actuator_strength;
} ogx_xid_output_report;

/* ---------------------------------------------------------------------------
 * 4. XAPI / XINPUT (VERIFIED - Cxbx Xapi.h; title-linked, NOT kernel exports)
 *
 * Every struct below is statically linked into each title via xapi.lib; the
 * signatures are __stdcall. Halo 2's use is confirmed by the decomped
 * matched-src/unknown_1248b0.cpp (XInitDevices, XGetDeviceChanges, XInputOpen,
 * XInputGetState, XInputSetState, XInputGetCapabilities).
 * ----------------------------------------------------------------------- */

/* Calling convention for XAPI: WINAPI == __stdcall (VERIFIED Xapi.h:38) */

/* XINPUT_POLLING_PARAMETERS (4 bytes) */
typedef struct ogx_xinput_polling_parameters {
    uint8_t fAutoPoll       : 1;
    uint8_t fInterruptOut   : 1;
    uint8_t ReservedMBZ1    : 6;
    uint8_t bInputInterval;
    uint8_t bOutputInterval;
    uint8_t ReservedMBZ2;
} ogx_xinput_polling_parameters;

/* XPP_DEVICE_TYPE (12 bytes) - the per-device-class connection bitmask. */
typedef struct ogx_xpp_device_type {
    uint32_t CurrentConnected;
    uint32_t ChangeConnected;
    uint32_t PreviousConnected;
} ogx_xpp_device_type;

/* XDEVICE_PREALLOC_TYPE (8 bytes on x86) - passed to XInitDevices. */
typedef struct ogx_xdevice_prealloc_type {
    xh_ptr    DeviceType;    /* XPP_DEVICE_TYPE * */
    uint32_t  dwPreallocCount;
} ogx_xdevice_prealloc_type;

/* XID_TYPE_INFORMATION (32-bit ABI: pointers 4 bytes) */
typedef struct ogx_xid_type_information {
    uint8_t  ucType;
    uint8_t  bRemainingHandles;
    uint8_t  ucUnknown[2];
    xh_ptr   XppType;            /* XPP_DEVICE_TYPE * */
    xh_ptr   pInputStateDesc;    /* XPP_DEVICE_INPUTSTATE_DESC * */
    xh_ptr   pFeedbackDesc;      /* XPP_DEVICE_FEEDBACK_DESC * */
    xh_ptr   pConstant;          /* dword_xt*; "always 0x0801" */
    xh_ptr   pFunction;          /* device-related function */
    uint32_t dwEndZero;
} ogx_xid_type_information;

/* XINPUT_GAMEPAD - #pragma pack(1) in the XDK (VERIFIED). 18 bytes. */
#pragma pack(push, 1)
typedef struct ogx_xinput_gamepad {
    uint16_t wButtons;
    uint8_t  bAnalogButtons[8];
    int16_t  sThumbLX;
    int16_t  sThumbLY;
    int16_t  sThumbRX;
    int16_t  sThumbRY;
} ogx_xinput_gamepad;
#pragma pack(pop)

/* XINPUT_STATE - not packed; Gamepad at offset 4 (VERIFIED Xapi.h:232). */
typedef struct ogx_xinput_state {
    uint32_t dwPacketNumber;
    union {
        ogx_xinput_gamepad Gamepad;
    };
} ogx_xinput_state;

/* XINPUT_RUMBLE (4 bytes) */
typedef struct ogx_xinput_rumble {
    uint16_t wLeftMotorSpeed;
    uint16_t wRightMotorSpeed;
} ogx_xinput_rumble;

/* XINPUT_CAPABILITIES */
typedef struct ogx_xinput_capabilities {
    uint8_t  SubType;
    uint16_t Reserved;
    union { ogx_xinput_gamepad Gamepad; } In;
    union { ogx_xinput_rumble   Rumble;  } Out;
} ogx_xinput_capabilities;

/* XINPUT_FEEDBACK_HEADER + XINPUT_FEEDBACK: #pragma pack(1) (VERIFIED). */
#pragma pack(push, 1)
typedef struct ogx_xinput_feedback_header {
    uint32_t dwStatus;           /* ERROR_SUCCESS / ERROR_IO_PENDING / ... */
    xh_handle hEvent;
    uint8_t   Unknown1[4];
    xh_ptr    IoCompletedEvent;  /* PKEVENT really */
    uint8_t   Unknown2[48];
    uint8_t   bReportId;
    uint8_t   bLength;
} ogx_xinput_feedback_header;

typedef struct ogx_xinput_feedback {
    ogx_xinput_feedback_header Header;
    union { ogx_xinput_rumble Rumble; };
} ogx_xinput_feedback;
#pragma pack(pop)

/* Device types / subtypes used by Halo 2 (VERIFIED Xapi.h + unknown_1248b0.cpp) */
#define OGXBOX_XINPUT_DEVTYPE_GAMEPAD        0x01
#define OGXBOX_XINPUT_DEVTYPE_STEELBATTALION 0x80
#define OGXBOX_XINPUT_DEVSUBTYPE_GC_GAMEPAD         0x01
#define OGXBOX_XINPUT_DEVSUBTYPE_GC_GAMEPAD_ALT     0x02
#define OGXBOX_XDEVICE_NO_SLOT        ((uint32_t)-1)

/* ---------------------------------------------------------------------------
 * 5. XAPI FUNCTION SIGNATURES (VERIFIED - Cxbx Xapi.h). __stdcall.
 * These are title-linked (static xapi.lib); a trainer hook patches the
 * in-title entry points, not a kernel table.
 * ----------------------------------------------------------------------- */
typedef void (OGXBOX_STDCALL *ogx_XInitDevices_t)(
    uint32_t dwPreallocTypeCount,
    xh_ptr   PreallocTypes /* XDEVICE_PREALLOC_TYPE * */);

typedef uint32_t (OGXBOX_STDCALL *ogx_XGetDevices_t)(
    xh_ptr DeviceType /* XPP_DEVICE_TYPE * */);

typedef uint8_t (OGXBOX_STDCALL *ogx_XGetDeviceChanges_t)(
    xh_ptr DeviceType,        /* XPP_DEVICE_TYPE * */
    xh_ptr pdwInsertions,
    xh_ptr pdwRemovals);

typedef xh_handle (OGXBOX_STDCALL *ogx_XInputOpen_t)(
    xh_ptr   DeviceType,            /* XPP_DEVICE_TYPE * (XDEVICE_TYPE_GAMEPAD) */
    uint32_t dwPort,
    uint32_t dwSlot,                /* XDEVICE_NO_SLOT */
    xh_ptr   pPollingParameters);   /* XINPUT_POLLING_PARAMETERS * */

typedef void (OGXBOX_STDCALL *ogx_XInputClose_t)(xh_handle hDevice);

typedef uint32_t (OGXBOX_STDCALL *ogx_XInputPoll_t)(xh_handle hDevice);

typedef uint32_t (OGXBOX_STDCALL *ogx_XInputGetCapabilities_t)(
    xh_handle hDevice, xh_ptr pCapabilities /* XINPUT_CAPABILITIES * */);

typedef uint32_t (OGXBOX_STDCALL *ogx_XInputGetState_t)(
    xh_handle hDevice, xh_ptr pState /* XINPUT_STATE * */);

typedef uint32_t (OGXBOX_STDCALL *ogx_XInputSetState_t)(
    xh_handle hDevice, xh_ptr pFeedback /* XINPUT_FEEDBACK * */);

#ifdef __cplusplus
}
#endif

#endif /* OGXBOX_ABI_H */
