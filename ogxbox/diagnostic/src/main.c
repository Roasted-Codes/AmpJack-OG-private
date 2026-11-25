/*
 * main.c — AmpJack-OG worker09 diagnostic: standalone original-Xbox title.
 *
 * What this measures (see ogxbox/diagnostic/README.md for the plain version):
 *   - Runs the TITLE-LINKED USBD (xapilib.lib) — the same USB stack the title
 *     links — NOT a raw OHCI driver. XInitDevices() performs the real
 *     enumeration.
 *   - ARMS a fail-closed E9 detour at USBD_LoadClassDriver so that every load
 *     of a class driver (including the unknown-device "no stock driver" path)
 *     pushes ONE bounded DIAG_EVT_MATCH into the pre-allocated ring, carrying
 *     the console-computed PNP_CLASS_ID (classId argument), speed, interface#,
 *     the device/interface/configuration descriptor fields, and the
 *     FindClassDriver result (NULL = no stock driver). The original
 *     LoadClassDriver is always called through, so the stock pad keeps working
 *     and an unknown device still gets the stock "no driver" treatment.
 *   - The detour is installed ONLY when (a) all four byte-signature pins match
 *     (PIN_ALL), (b) the first bytes at the target equal the displaced span
 *     PINNED_LOAD_SPAN derived from the BUILT XBE's bytes by
 *     ogxbox/work/09-diagnostic/gen_pinned_load.py, and (c) the section is
 *     XPP+writable (verified from the built XBE section headers by the same
 *     script).  Any mismatch => PINFAIL logged, no patch.
 *   - The capture handler runs at whatever context LoadClassDriver runs
 *     (treated as DPC): NO heap, NO file I/O, NO Sleep — only the pure getters
 *     and one ring push. Formatting + the file write happen in the main loop.
 *
 * Event labelling:
 *   MATCH    — from the LoadClassDriver capture (only when armed). Carries NO
 *              `port=` field: GetPort() reads device->port before the function's
 *              own SetExternalPort() call sets it, so it was garbage. The XID
 *              port comes from the STOCKPAD insertion-mask bit instead.
 *   STOCKPAD — XGetDeviceChanges: the STOCK XID gamepad surface only; NOT
 *              sufficient by itself to measure a GIP device's PNP_CLASS_ID.
 *   SYNTH    — synthetic/self-check lines (pin mask, armed yes/no, ABI probe,
 *              log path status).
 *   PINFAIL  — refuse-to-arm line (logged when a fail-closed check fails).
 *
 * This file is ORIGINAL code. It reproduces no proprietary XDK source; the
 * only facts it encodes (symbol names, offsets, descriptor layout, instruction
 * pins) are re-derived ABI from the BUILT XBE + ogxbox/research/binding, called
 * via lld-link /alternatename, never copied.
 */
#include <xtl.h>
#include <string.h>
#include "diag_util.h"
#include "pinned_load.h"

/* ---------------------------------------------------------------------
 * 1. Private USBD call surface, linked by exact symbol name (Makefile maps
 *    each via /alternatename). Descriptor structs are the public USB 1.1
 *    layout; _PNP_CLASS_ID is a 2-byte value (lo=SpecByte/MatchByte0,
 *    hi=Class). The GIP target FF/47/D0 means classId hi byte 0xFF.
 * ------------------------------------------------------------------- */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int  u32;

/* Full public USB 1.1 device descriptor (18 bytes). */
typedef struct { u8 bLength; u8 bDescriptorType; u16 bcdUSB; u8 bDeviceClass;
                 u8 bDeviceSubClass; u8 bDeviceProtocol; u8 bMaxPacketSize0;
                 u16 idVendor; u16 idProduct; u16 bcdDevice;
                 u8 iManufacturer; u8 iProduct; u8 iSerialNumber; u8 bNumConfigurations; }
    USB_DEVICE_DESCRIPTOR8;
typedef struct { u8 bLength; u8 bDescriptorType; u16 wTotalLength; u8 bNumInterfaces;
                 u8 bConfigurationValue; u8 iConfiguration; u8 bmAttributes;
                 u8 MaxPower; } USB_CONFIGURATION_DESCRIPTOR;
typedef struct { u8 bLength; u8 bDescriptorType; u8 bInterfaceNumber;
                 u8 bAlternateSetting; u8 bNumEndpoints; u8 bInterfaceClass;
                 u8 bInterfaceSubClass; u8 bInterfaceProtocol; u8 iInterface; }
    USB_INTERFACE_DESCRIPTOR;
typedef struct { u8 bLength; u8 bDescriptorType; u8 bEndpointAddress;
                 u8 bmAttributes; u16 wMaxPacketSize; u8 bInterval; }
    USB_ENDPOINT_DESCRIPTOR;

/* __thiscall methods ('self' in ECX). */
extern unsigned short __thiscall usbd_GetClassId(void *self);           /* addr-only; ABI = struct-return w/ hidden out ptr — NOT called at capture (derefs unset device->[0x10]) */
extern const USB_DEVICE_DESCRIPTOR8 *    __thiscall usbd_GetDeviceDescriptor(void *self);
extern const USB_CONFIGURATION_DESCRIPTOR* __thiscall usbd_GetConfigurationDescriptor(void *self);
extern const USB_INTERFACE_DESCRIPTOR *   __thiscall usbd_GetInterfaceDescriptor(void *self);
extern const USB_ENDPOINT_DESCRIPTOR *    __thiscall usbd_GetEndpointDescriptor(void *self, u8 iface, u8 index, u8 dir);
extern unsigned char __thiscall usbd_GetInterfaceNumber(void *self);
extern unsigned int  __thiscall usbd_GetPort(void *self);
extern unsigned char __thiscall usbd_GetLowSpeed(void *self);
extern unsigned char __thiscall usbd_IsHardwareConnected(void *self);

/* __stdcall(1): classId by value -> class-driver description* (NULL = no match) */
extern void * __stdcall usbd_FindClassDriver(unsigned short classId);
/* __fastcall decl used ONLY to take the entry address for pinning/detour.
 * NOTE the real ABI passes classId on the stack (a _PNP_CLASS_ID *union*, so
 * old MSVC fastcall pushes it); the trampoline reads it from [esp+4], never
 * through this prototype's EDX. */
extern void __fastcall usbd_LoadClassDriver(void *device, unsigned short classId);

/* Force the descriptor/getter ABI to LINK (address table kept reachable). */
static const void * const g_abi_probe[] = {
    (const void *)&usbd_GetClassId,
    (const void *)&usbd_GetDeviceDescriptor,
    (const void *)&usbd_GetConfigurationDescriptor,
    (const void *)&usbd_GetInterfaceDescriptor,
    (const void *)&usbd_GetEndpointDescriptor,
    (const void *)&usbd_GetInterfaceNumber,
    (const void *)&usbd_GetPort,
    (const void *)&usbd_GetLowSpeed,
    (const void *)&usbd_IsHardwareConnected,
};

/* ---------------------------------------------------------------------
 * 1b. Kernel drive-letter mapping. E: is NOT mounted for an OXDK/XDK title by
 *     default (a title only gets its launch dir / T: / U: / Z:), so the E:\
 *     log path fails unless we map it ourselves. IoCreateSymbolicLink is a
 *     kernel export the OXDK toolchain already aliases (__imp__IoCreateSymbolicLink
 *     -> __imp__IoCreateSymbolicLink@8); the Xbox kernel takes ANSI strings.
 * ------------------------------------------------------------------- */
typedef struct { u16 Length; u16 MaximumLength; char *Buffer; } DIAG_ANSI_STRING;
extern unsigned long __stdcall IoCreateSymbolicLink(DIAG_ANSI_STRING *name, DIAG_ANSI_STRING *target);
#define STATUS_OBJECT_NAME_COLLISION 0xC0000035u

/* ---------------------------------------------------------------------
 * 2. Trace state (global, pre-allocated, bounded).
 * ------------------------------------------------------------------- */
static diag_ring g_ring;
static const char kLogPath[]  = "E:\\AmpJack-OG\\usb-probe.log";
static const char kLogDir []  = "E:\\AmpJack-OG";
static const char kLogPathD[] = "D:\\usb-probe.log";   /* launch dir; needs no mapping */
static const char kHex[]      = "0123456789abcdef";

static volatile uint32_t g_seq = 0;          /* monotonic, shared by all events */
static volatile uint32_t g_match_count = 0;  /* MATCH events pushed            */
static volatile uint32_t g_unknown_count = 0;/* MATCH with no stock class driver (the device we are measuring) */

/* Trampoline re-encode targets, filled at arm time (read by the naked hook). */
static uint32_t g_resume_va      = 0;        /* &usbd_LoadClassDriver + RESUME_OFF  */
static uint32_t g_call_target_va = 0;        /* &usbd_LoadClassDriver + CALL_DELTA  */
static volatile int  g_armed = 0;

/* ---------------------------------------------------------------------
 * 3. Capture routine — called ONLY from the naked trampoline, in the same
 *    context LoadClassDriver runs. DPC-safe: pure getters + one ring push.
 * ------------------------------------------------------------------- */
static void __cdecl diag_capture_match(void *device, uint32_t classId);

static void __cdecl diag_capture_match(void *device, uint32_t classId) {
    diag_event ev;
    memset(&ev, 0, sizeof ev);
    ev.kind   = DIAG_EVT_MATCH;
    ev.device = (uint32_t)(u32)device;
    ev.a      = classId & 0xFFFF;               /* console-computed PNP_CLASS_ID */
    ev.speed  = usbd_GetLowSpeed(device);
    ev.iface  = usbd_GetInterfaceNumber(device);

    const USB_DEVICE_DESCRIPTOR8 *dd  = usbd_GetDeviceDescriptor(device);
    const USB_INTERFACE_DESCRIPTOR *ifd = usbd_GetInterfaceDescriptor(device);
    const USB_CONFIGURATION_DESCRIPTOR *cfd = usbd_GetConfigurationDescriptor(device);

    if (dd) {
        ev.dclass = dd->bDeviceClass;
        ev.dsub   = dd->bDeviceSubClass;
        ev.dproto = dd->bDeviceProtocol;
        if (dd->bLength >= 0x12) {             /* 18-byte descriptor => idVendor/Product present */
            ev.vendor  = dd->idVendor;
            ev.product = dd->idProduct;
        }
    }
    if (ifd) {
        ev.ifclass = ifd->bInterfaceClass;
        ev.ifsub   = ifd->bInterfaceSubClass;
        ev.ifproto = ifd->bInterfaceProtocol;
        ev.nep     = ifd->bNumEndpoints;
    }
    if (cfd) {
        ev.niface  = cfd->bNumInterfaces;
    }
    /* NULL => no stock class driver (the GIP FF/47 path we are measuring). */
    ev.find = (uint32_t)(u32)usbd_FindClassDriver((unsigned short)(classId & 0xFFFF));

    ev.seq = ++g_seq;
    if (diag_ring_push(&g_ring, &ev)) {
        g_match_count++;
        if (ev.find == 0) g_unknown_count++;
    }
}

/* ---------------------------------------------------------------------
 * 4. The E9 detour trampoline (naked). Entry state == LoadClassDriver entry:
 *    ECX = device, [esp] = caller ret, [esp+4] = classId (4-byte slot).
 *    Sequence: save regs+flags -> capture (device, classId) -> restore ->
 *    re-execute the displaced span (push esi; mov esi,ecx; call SetExternalPort
 *    re-encoded as mov eax,<abs>; call eax) -> jump to entry+resume.
 * ------------------------------------------------------------------- */
__declspec(naked) static void diag_loadclass_hook(void) {
    __asm {
        pushad                               ; EAX ECX EDX EBX ESP EBP ESI EDI
        pushfd
        movzx  eax, word ptr [esp+40]        ; classId (callers 4-byte stack slot)
        mov    ecx, dword ptr [esp+28]       ; device (saved ECX)
        push   eax                           ; arg2: classId
        push   ecx                           ; arg1: device
        call   diag_capture_match
        add    esp, 8                        ; __cdecl cleanup
        popfd
        popad
        push   esi                           ; displaced: push esi
        mov    esi, ecx                      ; displaced: mov esi, ecx
        mov    eax, g_call_target_va         ; displaced rel32 call, re-encoded
        call   eax
        mov    eax, g_resume_va              ; continue original code at +RESUME_OFF
        jmp    eax
    }
}

/* ---------------------------------------------------------------------
 * 5. Byte-signature pinning of OUR OWN built USBD functions (fail-closed).
 * ------------------------------------------------------------------- */
static const u8 SIG_FINDCLASSDRIVER[] = {0x3a,0x70,0x01,0x75,0x04,0x3a,0x10}; /* cmp dh,[eax+1];jne;cmp dl,[eax] */
static const u8 SIG_LOAD_PREFIX[]     = {0x56,0x8b,0xf1};                     /* push esi; mov esi,ecx        */
static const u8 SIG_LOAD_GATE[]       = {0x83,0x7e,0x14,0x20};                /* cmp [esi+0x14],0x20          */
static const u8 SIG_LOAD_ATTACH[]     = {0xff,0x50,0x08};                     /* call [eax+8] (Attach)        */

#define PIN_FINDCLASSDRIVER (1u<<0)
#define PIN_LOAD_PREFIX     (1u<<1)
#define PIN_LOAD_GATE       (1u<<2)
#define PIN_LOAD_ATTACH     (1u<<3)
#define PIN_ALL             (PIN_FINDCLASSDRIVER|PIN_LOAD_PREFIX|PIN_LOAD_GATE|PIN_LOAD_ATTACH)

static unsigned int diag_pin_usbd(void) {
    unsigned int pins = 0;
    const u8 *f = (const u8 *)(u32)&usbd_FindClassDriver;
    const u8 *l = (const u8 *)(u32)&usbd_LoadClassDriver;
    if (diag_sig_find(f, 0x40, SIG_FINDCLASSDRIVER, sizeof(SIG_FINDCLASSDRIVER)) >= 0) pins |= PIN_FINDCLASSDRIVER;
    if (diag_sig_find(l, 0x40, SIG_LOAD_PREFIX,     sizeof(SIG_LOAD_PREFIX))     >= 0) pins |= PIN_LOAD_PREFIX;
    if (diag_sig_find(l, 0x40, SIG_LOAD_GATE,       sizeof(SIG_LOAD_GATE))       >= 0) pins |= PIN_LOAD_GATE;
    if (diag_sig_find(l, 0x40, SIG_LOAD_ATTACH,     sizeof(SIG_LOAD_ATTACH))     >= 0) pins |= PIN_LOAD_ATTACH;
    return pins;
}

/*
 * Arm the E9 detour, fail-closed. Returns a bitmask describing exactly why it
 * did or did not arm; 0 => armed.
 */
#define ARM_OK            0
#define ARM_BAD_PINS      1   /* signature pins incomplete              */
#define ARM_BAD_PROLOGUE  2   /* target bytes != PINNED_LOAD_SPAN       */
#define ARM_NOT_WRITABLE  3   /* section not writable in the built XBE  */

static unsigned int diag_arm_detour(unsigned int pins) {
    u8 *target = (u8 *)(u32)&usbd_LoadClassDriver;

    if (pins != PIN_ALL)
        return ARM_BAD_PINS;
    /* exact displaced-span pin, derived from the built XBE at gen time */
    if (!diag_pin_span(target, PINNED_LOAD_SPAN, PINNED_LOAD_SPAN_LEN))
        return ARM_BAD_PROLOGUE;
    /* re-derive the span from the live bytes and cross-check the rel32 layout
     * against the gen-time PINNED_LOAD_* constants (fail closed on drift) */
    {
        size_t span_len = 0;
        long rel_ofs = -1, rel_target = 0;
        if (diag_span_analyze(target, PINNED_LOAD_SPAN_LEN + 8,
                              &span_len, &rel_ofs, &rel_target) != 0)
            return ARM_BAD_PROLOGUE;
        if (span_len != PINNED_LOAD_SPAN_LEN)
            return ARM_BAD_PROLOGUE;
        if ((rel_ofs >= 0) != (PINNED_LOAD_REL32_PRESENT != 0))
            return ARM_BAD_PROLOGUE;
        if (rel_ofs >= 0 && rel_ofs != PINNED_LOAD_REL32_OFFSET)
            return ARM_BAD_PROLOGUE;
    }
    /* section writability, verified from the built XBE section headers */
    if (!PINNED_LOAD_SECTION_WRITABLE)
        return ARM_NOT_WRITABLE;

    /* runtime targets for the trampoline re-encode / jump-back */
    g_call_target_va = (uint32_t)(u32)&usbd_LoadClassDriver + PINNED_LOAD_CALL_TARGET_DELTA;
    g_resume_va      = (uint32_t)(u32)&usbd_LoadClassDriver + PINNED_LOAD_RESUME_OFF;

    /* E9 rel32 -> trampoline */
    {
        uint32_t rel = (uint32_t)(u32)&diag_loadclass_hook - ((uint32_t)(u32)target + 5);
        u8 patch[5];
        patch[0] = 0xE9;
        patch[1] = (u8)(rel & 0xFF);
        patch[2] = (u8)((rel >> 8) & 0xFF);
        patch[3] = (u8)((rel >> 16) & 0xFF);
        patch[4] = (u8)((rel >> 24) & 0xFF);
        memcpy(target, patch, 5);
    }
    g_armed = 1;
    return ARM_OK;
}

/* ---------------------------------------------------------------------
 * 6. Small hex/text helpers (identical on host + Xbox).
 * ------------------------------------------------------------------- */
static size_t put_hex(char *o, size_t cap, size_t n, u32 v, int nibbles) {
    int sh = (nibbles - 1) * 4;
    for (; sh >= 0; sh -= 4) { if (n + 1 < cap) o[n++] = kHex[(v >> sh) & 15]; }
    return n;
}
static size_t put_str(char *o, size_t cap, size_t n, const char *s) {
    while (*s && n + 1 < cap) o[n++] = *s++;
    return n;
}
static size_t put_dec(char *o, size_t cap, size_t n, u32 v) {
    char tmp[11]; int t = 0;
    if (v == 0) { if (n + 1 < cap) o[n++] = '0'; return n; }
    while (v && t < 10) { tmp[t++] = (char)('0' + (v % 10)); v /= 10; }
    while (t > 0 && n + 1 < cap) o[n++] = tmp[--t];
    return n;
}

/* ---------------------------------------------------------------------
 * 7. File logging (normal loop context ONLY). Writes to BOTH:
 *      E:\AmpJack-OG\usb-probe.log  (mapped by us below)   — primary deliverable
 *      D:\usb-probe.log             (launch dir, no mapping needed) — fallback
 *    The first line reports which path actually opened, so a future run tells
 *    us which one worked.
 * ------------------------------------------------------------------- */
static BOOL   g_logOpen   = FALSE;
static HANDLE g_logHandle  = (HANDLE)0xFFFFFFFF;   /* E:\ primary  */
static BOOL   g_logOpenD  = FALSE;
static HANDLE g_logHandleD = (HANDLE)0xFFFFFFFF;   /* D:\ fallback */

/* log_write(LOG_LIT(s)) — length from sizeof, never a hand-counted number. */
#define LOG_LIT(s) log_write((s), DIAG_LIT_LEN(s))
static void log_write(const char *s, size_t len);   /* used by log_start below */


static void log_map_e(void) {
    DIAG_ANSI_STRING link, tgt;
    link.Buffer = "\\??\\E:"; link.Length = (u16)strlen(link.Buffer);
    link.MaximumLength = (u16)(link.Length + 1);
    tgt.Buffer  = "\\Device\\Harddisk0\\Partition1";
    tgt.Length = (u16)strlen(tgt.Buffer);
    tgt.MaximumLength = (u16)(tgt.Length + 1);
    /* already-mapped is fine (STATUS_OBJECT_NAME_COLLISION); ignore the result */
    IoCreateSymbolicLink(&link, &tgt);
}

static HANDLE log_open_file(const char *path, const char *dir) {
    if (dir != NULL)
        CreateDirectory(dir, NULL);
    HANDLE h = CreateFile(path, GENERIC_WRITE, FILE_SHARE_READ, NULL,
                          OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h != (HANDLE)0xFFFFFFFF && h != NULL) {
        SetFilePointer(h, 0, NULL, FILE_END);
        return h;
    }
    return (HANDLE)0xFFFFFFFF;
}

static void log_start(void) {
    log_map_e();
    g_logHandle  = log_open_file(kLogPath,  kLogDir);
    g_logHandleD = log_open_file(kLogPathD, NULL);
    g_logOpen  = (g_logHandle  != (HANDLE)0xFFFFFFFF);
    g_logOpenD = (g_logHandleD != (HANDLE)0xFFFFFFFF);

    /* report which path opened, in whatever handle(s) made it */
    {
        char line[64]; size_t n = 0;
        n = put_str(line, sizeof line, n, "SYNTH log=E ");
        n = put_str(line, sizeof line, n, g_logOpen  ? "ok" : "fail");
        n = put_str(line, sizeof line, n, " D ");
        n = put_str(line, sizeof line, n, g_logOpenD ? "ok" : "fail");
        n = put_str(line, sizeof line, n, "\n");
        log_write(line, n);
    }
}
static void log_write(const char *s, size_t len) {
    DWORD wrote = 0;
    if (g_logOpen)  WriteFile(g_logHandle,  s, (DWORD)len, &wrote, NULL);
    if (g_logOpenD) WriteFile(g_logHandleD, s, (DWORD)len, &wrote, NULL);
}
static void log_flush(void) {
    if (g_logOpen)  FlushFileBuffers(g_logHandle);
    if (g_logOpenD) FlushFileBuffers(g_logHandleD);
}

/* Drain the ring in normal context: OVERFLOW line (if any) FIRST, then each
 * event, then flush. Used both immediately after XInitDevices and each loop. */
static void drain_and_log(void) {
    uint32_t n = g_ring.count;
    uint32_t dropped = g_ring.overflow;
    if (dropped) {
        diag_event ev; memset(&ev, 0, sizeof ev);
        ev.kind = DIAG_EVT_OVERFLOW; ev.a = dropped; ev.seq = ++g_seq;
        char line[96]; size_t ln = diag_format_event(line, sizeof line, &ev);
        log_write(line, ln);
    }
    for (uint32_t i = 0; i < n; i++) {
        char line[256];
        size_t ln = diag_format_event(line, sizeof line, &g_ring.slots[i]);
        log_write(line, ln);
    }
    diag_ring_reset(&g_ring);
    log_flush();
}

/* ---------------------------------------------------------------------
 * 7b. Optional on-screen colour (cheap d3d8 Clear+Present). Solid colour:
 *     red=PINFAIL, yellow=armed/no MATCH, green=MATCH captured, blink on exit.
 *     If the device cannot be created it silently stays as a log-only run.
 * ------------------------------------------------------------------- */
static Direct3D  *g_pD3D = NULL;
static D3DDevice *g_pDev = NULL;

static void video_init(void) {
    g_pD3D = Direct3DCreate8(D3D_SDK_VERSION);
    if (g_pD3D == NULL)
        return;
    D3DPRESENT_PARAMETERS pp;
    memset(&pp, 0, sizeof pp);
    pp.BackBufferWidth  = 640;
    pp.BackBufferHeight = 480;
    pp.BackBufferFormat = D3DFMT_X8R8G8B8;
    pp.BackBufferCount  = 1;
    pp.SwapEffect = D3DSWAPEFFECT_DISCARD;
    pp.FullScreen_RefreshRateInHz = D3DPRESENT_RATE_DEFAULT;
    pp.FullScreen_PresentationInterval = D3DPRESENT_INTERVAL_ONE;
    if (FAILED(Direct3D_CreateDevice(0, D3DDEVTYPE_HAL, NULL,
                 D3DCREATE_HARDWARE_VERTEXPROCESSING, &pp, &g_pDev)))
        g_pDev = NULL;
}

static void video_clear(D3DCOLOR col) {
    if (g_pDev == NULL)
        return;
    D3DDevice_Clear(0, NULL, D3DCLEAR_TARGET, col, 1.0f, 0);
    D3DDevice_Swap(0);   /* Present (count=0 clears the whole viewport) */
}

/* ---------------------------------------------------------------------
 * 8. main
 * ------------------------------------------------------------------- */
int main(void) {
    XDEVICE_PREALLOC_TYPE prealloc[1];
    prealloc[0].DeviceType      = XDEVICE_TYPE_GAMEPAD;   /* keep stock pad live */
    prealloc[0].dwPreallocCount = 4;

    diag_ring_reset(&g_ring);
    log_start();

    /* 8a. Pin our built USBD by signature. */
    unsigned int pins = diag_pin_usbd();

    /* 8b. Prove the class-match ABI live. */
    void *xid_desc = usbd_FindClassDriver(0x5882);
    void *hub_desc = usbd_FindClassDriver(0x0981);

    /* 8c. Arm the LoadClassDriver E9 detour (fail-closed). Must happen BEFORE
     *     XInitDevices so enumeration hits the hook. */
    unsigned int arm = diag_arm_detour(pins);

    {
        char line[256]; size_t n = 0;
        const size_t abi_n = sizeof(g_abi_probe) / sizeof(g_abi_probe[0]);
        u32 abi_sum = 0;
        for (size_t k = 0; k < abi_n; k++) abi_sum += (u32)(u32)g_abi_probe[k];
        n = put_str(line, sizeof line, n, "SYNTH pin=0x"); n = put_hex(line, sizeof line, n, pins, 8);
        n = put_str(line, sizeof line, n, " armed=");      n = put_dec(line, sizeof line, n, g_armed ? 1 : 0);
        n = put_str(line, sizeof line, n, " armcode=");     n = put_dec(line, sizeof line, n, arm);
        n = put_str(line, sizeof line, n, " entry_va=0x"); n = put_hex(line, sizeof line, n, (u32)(u32)&usbd_LoadClassDriver, 8);
        n = put_str(line, sizeof line, n, " span_len=");    n = put_dec(line, sizeof line, n, PINNED_LOAD_SPAN_LEN);
        n = put_str(line, sizeof line, n, " rel32=");       n = put_dec(line, sizeof line, n, PINNED_LOAD_REL32_PRESENT);
        n = put_str(line, sizeof line, n, " writable=");    n = put_dec(line, sizeof line, n, PINNED_LOAD_SECTION_WRITABLE);
        n = put_str(line, sizeof line, n, " findclass_xid=0x"); n = put_hex(line, sizeof line, n, (u32)(u32)xid_desc, 8);
        n = put_str(line, sizeof line, n, " findclass_hub=0x"); n = put_hex(line, sizeof line, n, (u32)(u32)hub_desc, 8);
        n = put_str(line, sizeof line, n, " abi_syms=");    n = put_hex(line, sizeof line, n, (u32)abi_n, 2);
        n = put_str(line, sizeof line, n, " abi_sum=0x");   n = put_hex(line, sizeof line, n, abi_sum, 8);
        n = put_str(line, sizeof line, n, "\n");
        log_write(line, n);
    }

    if (arm != ARM_OK) {
        char line[128]; size_t n = 0;
        n = put_str(line, sizeof line, n, "PINFAIL armcode="); n = put_dec(line, sizeof line, n, arm);
        n = put_str(line, sizeof line, n, " pins=0x");         n = put_hex(line, sizeof line, n, pins, 8);
        n = put_str(line, sizeof line, n, "\n");
        log_write(line, n);
        log_flush();
    }

    /* 8d. Real enumeration via the title-linked USBD (hits the detour). */
    XInitDevices(1, prealloc);

    /* 8d2. Drain + flush immediately: the MATCH pushed during enumeration is
     *      the whole point, so don't wait for the first Sleep before writing it. */
    drain_and_log();

    /* 8e. Optional on-screen status colour (fails silently to log-only). */
    video_init();

    /* In-gamepad handles are opened/closed per-port from XGetDeviceChanges in
     * the loop (opening them once right after XInitDevices is too early). */
    HANDLE pads[4] = { (HANDLE)0, (HANDLE)0, (HANDLE)0, (HANDLE)0 };

    DWORD last_insert = 0xFFFFFFFF;   /* force first STOCKPAD emit */
    DWORD backstart_held = 0;

    for (;;) {
        DWORD ins = 0, rem = 0;
        XGetDeviceChanges(XDEVICE_TYPE_GAMEPAD, &ins, &rem);

        /* (Re)open/close per-port gamepad handles from the device-change surface. */
        for (int port = 0; port < 4; port++) {
            if ((rem & (1u << port)) && pads[port] != NULL) {
                XInputClose(pads[port]);
                pads[port] = NULL;
            }
            if ((ins & (1u << port)) && pads[port] == NULL) {
                pads[port] = XInputOpen(XDEVICE_TYPE_GAMEPAD, port,
                                        XDEVICE_NO_SLOT, NULL);
            }
        }

        /* Stock-controller surface (honest, labelled insufficient for GIP). */
        if (ins != last_insert) {
            diag_event ev; memset(&ev, 0, sizeof ev);
            ev.kind = DIAG_EVT_STOCKPAD; ev.b = ins; ev.seq = ++g_seq;
            diag_ring_push(&g_ring, &ev);
            last_insert = ins;
        }

        drain_and_log();

        /* BACK+START held ~1 s on an open stock pad => return to dashboard. */
        {
            int held = 0;
            for (int port = 0; port < 4 && !held; port++) {
                XINPUT_STATE st;
                if (pads[port] &&
                    XInputGetState(pads[port], &st) == ERROR_SUCCESS &&
                    (st.Gamepad.wButtons & (XINPUT_GAMEPAD_BACK | XINPUT_GAMEPAD_START)) ==
                        (XINPUT_GAMEPAD_BACK | XINPUT_GAMEPAD_START))
                    held = 1;
            }
            if (held) {
                backstart_held += 250;
                if (backstart_held >= 1000) {
                    LOG_LIT("SYNTH exit=dashboard\n");
                    log_flush();
                    XLaunchNewImage(NULL, NULL);
                    /* not reached in normal flow */
                }
            } else {
                backstart_held = 0;
            }
        }

        /* on-screen colour: red=PINFAIL, yellow=armed/no MATCH, green=MATCH,
         * blink while BACK+START is being held. */
        if (g_pDev != NULL) {
            D3DCOLOR col;
            if (arm != ARM_OK)
                col = 0xFFFF0000;              /* red    */
            else if (g_unknown_count > 0)
                col = 0xFF00FF00;              /* green: a device with NO stock driver was captured (the measurement) */
            else if (g_match_count > 0)
                col = 0xFF00FFFF;              /* cyan: armed, only stock devices (hubs / XID pad) seen so far */
            else
                col = 0xFFFFFF00;              /* yellow: armed, nothing enumerated yet */
            if (backstart_held > 0 && backstart_held < 1000)
                col = ((backstart_held / 250) & 1) ? 0xFF000000 : col;
            video_clear(col);
        }

        Sleep(250);
    }
    return 0;
}
