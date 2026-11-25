/*
 * gipdrive.h — shared, dependency-free core of the AmpJack-OG GIP class-driver
 * transport proof (worker 11).
 *
 * HEADER-ONLY on purpose: the SAME code compiles into (a) the Xbox title
 * (ogxbox/gipdriver/src/main.c) and (b) the host test harness
 * (ogxbox/work/11-gipdriver/test_gipdriver.c), so the logic the Xbox runs is
 * literally the logic the host tests exercise.
 *
 * Four parts:
 *   1. URB ABI        — the title-linked XAPILIB _URB variants, re-declared here
 *                       at the exact byte offsets pinned by worker 07/09. No
 *                       proprietary XDK code is copied; these are struct layouts
 *                       asserted against the XBE bytes.
 *   2. TRACE RING     — bounded, pre-allocated. The URB completion callback runs
 *                       at DISPATCH_LEVEL (worker 09) and may ONLY push one
 *                       bounded event (a raw IN packet, or a status/error) and
 *                       re-submit the interrupt URB. No malloc, no file I/O, no
 *                       Sleep. The main loop drains, formats and writes.
 *   3. GIP FRAMES     — the exact power-on / LED / rumble / identify / announce
 *                       / input / status frames of the wired no-auth GIP path,
 *                       byte-for-byte the packet core/gip.c (the hardened parser
 *                       this worker mirrors) emits/consumes.
 *   4. PIN HELPERS    — byte-signature / shape-pin helpers used to fail-closed
 *                       arm the FindClassDriver detour.
 *
 * No proprietary XDK source is reproduced. Descriptor/URB structs are the
 * public USB 1.1 / XAPILIB ABI layouts re-derived from the built XBE and
 * ogxbox/research/binding; the GIP bytes are from core/gip.c.
 */
#ifndef GIPDRIVE_H
#define GIPDRIVE_H

#include <stddef.h>   /* size_t */
#include <string.h>   /* memset */
#if defined(_MSC_VER) && _MSC_VER < 1600
/* Xbox XDK (VC7.1-era) ships no <stdint.h>; provide exact-width types. */
typedef unsigned char  uint8_t;
typedef unsigned short uint16_t;
typedef unsigned int   uint32_t;
typedef signed char    int8_t;
typedef signed short   int16_t;
typedef int            int32_t;
#else
#include <stdint.h>
#endif

typedef uint8_t  u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef int16_t  s16;

#define GDR_LIT_LEN(s) (sizeof(s) - 1u)

/* ------------------------------------------------------------------ */
/* 1. URB ABI — byte offsets VERIFIED in worker 07/09                  */
/* ------------------------------------------------------------------ */

/* _URB_HEADER: Length +0, Function +1, reserved +2..3, Status +4,
 * CompleteProc +8 (__stdcall(URB*,void*)), CompleteContext +0xC. */
typedef struct gdr_urb_header {
    u8  Length;
    u8  Function;
    u8  Reserved[2];
    u32 Status;
    u32 CompleteProc;
    u32 CompleteContext;
} gdr_urb_header;

/* OPEN_ENDPOINT (Function 0x02 / 0x82), Length 0x20 = 32 B. Caller sets
 * +0x15 (endpoint addr, bit0x80=IN), +0x16 (0=ctrl 2=bulk 3=interrupt),
 * +0x17 (bInterval), +0x1C (wMaxPacketSize). SubmitRequest fills +0x14 (func
 * addr), +0x18 (&device->[0x18]), +0x1E (direction); HCD writes the pipe
 * handle OUT to +0x10 on success. */
typedef struct gdr_urb_open {
    gdr_urb_header Hdr;         /* +0x00 */
    u32 EndpointHandle;         /* +0x10 OUT */
    u8  FunctionAddress;        /* +0x14 */
    u8  EndpointAddress;        /* +0x15 */
    u8  TransferType;           /* +0x16 */
    u8  Interval;               /* +0x17 */
    u32 TransferBuffer;         /* +0x18 */
    u16 MaxPacketSize;          /* +0x1C */
    u8  Direction;              /* +0x1E */
} gdr_urb_open;

/* BULK_OR_INTERRUPT transfer (Function 0x41), Length 0x28 = 40 B.
 *
 * TRUE field semantics, independently traced from the linked XAPILIB XBE by
 * the Sol audit (completion/program-transfer/transfer-sizing disassembly) —
 * do NOT trust the historical field names below:
 *   +0x04 Hdr.Status     = REAL URB completion status. status0 does NOT mean
 *                          "sent"; errors are written here (completion @2ed24).
 *   +0x14 TransferLength = requested bytes set by the producer at submit; the
 *                          HCD ACCUMULATES the actual completed bytes here at
 *                          completion (completion @2ed12: add [urb+14],eax).
 *                          MUST be snapshotted BEFORE it is reset for re-arm.
 *   +0x18 TransferBuffer = data buffer.
 *   +0x20 ByteCount      = ORIGINAL MAPPED LENGTH, saved by the HCD at submit
 *                          (program-transfer @2fbfa..2fc02: movzx WORD+14 then
 *                          mov WORD+20, then zeroes +14). It is NOT the bytes
 *                          actually received. The field name is historical
 *                          and misleading — production code MUST NOT read it
 *                          as a byte count. Referred to as "mapped length".
 *   +0x22 State           = HCD internal state bits.
 *   +0x24 TransferStatus  = HCD LINKED-LIST linkage (completion @2ec3d/2ec4c/
 *                          2ec57 walk +0x24 as a list pointer and clear it),
 *                          NOT a transfer status. Field name is historical
 *                          and misleading — production code MUST NOT read it
 *                          as a status code. Referred to as "linkage".
 *
 * The typedef shape and byte offsets are unchanged (the read-only host suites
 * assert them by name); only the use/meaning is corrected above. */
typedef struct gdr_urb_transfer {
    gdr_urb_header Hdr;         /* +0x00 */
    u32 EndpointHandle;         /* +0x10 */
    u32 TransferLength;         /* +0x14 requested@submit / actual@completion */
    u32 TransferBuffer;         /* +0x18 */
    u8  FlagB0;                 /* +0x1C: IN data = 2, OUT data = 1 (XID) */
    u8  FlagB1;                 /* +0x1D: IN data = 1, OUT data = 0 (XID) */
    u8  Direction;              /* +0x1E: 0 for BOTH IN and OUT transfer (XID) */
    u8  unused_1F;
    u16 ByteCount;              /* +0x20 HCD: ORIGINAL MAPPED length (NOT received) */
    u16 State;                  /* +0x22 HCD state */
    u32 TransferStatus;         /* +0x24 HCD LINKAGE (NOT status) */
} gdr_urb_transfer;
/* Flag evidence (VERIFIED, worker16 xid.obj disasm): XID_fOpenDevice builds the
 * persistent interrupt-IN URB with 2,1,0 (worker09 §3); XID_fSendDeviceReport
 * builds the interrupt-OUT URB with 1,0,0 (`c6 46 2c 01`, `88 5e 2d`,
 * `88 5e 2e`). Direction is 0 in both — the HCD selects TD direction from
 * FlagB0 (2=IN, 1=OUT), NOT from the Direction byte. */

/* USB_CLASS_DRIVER_DESCRIPTION (VERIFIED worker 07 + slice2 disassembly).
 * MatchByte0 compared with the low byte of the console-computed PNP_CLASS_ID,
 * MatchByte1 with the high byte. For the measured GIP class id 0xFF81:
 * MatchByte0=0x81, MatchByte1=0xFF.
 *
 * The description is 0x18 (24) bytes, NOT the 12 this drove in slice1. Slice2
 * re-derived the full layout from the linked xapilib in bin/AmpJackGip.exe:
 *   - _XID_Description @0x2d0d8 (24 B): 82 58 ff ff <Reg> <Attach> <RmDv>
 *     <1> <0>  — Register@+0x04, Attach@+0x08, RemoveDevice@+0x0C,
 *     TypeInfo@+0x10 = 1, DispatchTable@+0x14 = 0.
 *   - RemoveDevice is the __stdcall(1 device) remove callback the tree invokes
 *     on disconnect: tree.obj `mov 0x10(%esi),%eax; call *0xc(%eax)` @0x2f68c
 *     (after `test eax,eax / je` -> NULL RemoveDevice is skipped, so a NULL
 *     here is tolerated by the stack but leaves no cleanup).
 *   - DispatchTable (+0x14) is a type-dispatch table indexed by device->[7]
 *     (class byte); AddComplete @0x2f9bb skips it when device->[7]==0xFF, so
 *     the GIP pad never dereferences it and 0 (NULL) is safe.
 *
 * Slice1 populated only the first 12 bytes, leaving +0x0C (RemoveDevice) and
 * beyond as adjacent .bss — on an unplug the tree would read/call garbage there.
 * Slice2 pins the full 24-byte layout and a real remove callback. */
typedef struct gdr_class_desc {
    u8  MatchByte0;             /* +0x00 */
    u8  MatchByte1;             /* +0x01 */
    u8  pad[2];                 /* +0x02 (0xFF 0xFF observed) */
    u32 Register;               /* +0x04 __stdcall(1) no-op here */
    u32 Attach;                 /* +0x08 __stdcall(1) = our attach */
    u32 RemoveDevice;           /* +0x0C __stdcall(1) remove callback (VERIFIED) */
    u32 TypeInfo;               /* +0x10 = 1 for XID/hub (flag; 0 ok for GIP)  */
    u32 DispatchTable;          /* +0x14 type dispatch table (NULL; 0xFF skips) */
} gdr_class_desc;

/* GIP target class id measured on the real console (REAL-CONSOLE-RESULT.md). */
#define GDR_PNP_GIP 0xFF81u

/* ------------------------------------------------------------------ */
/* 2. TRACE RING                                                       */
/* ------------------------------------------------------------------ */

#define GDR_RING_CAP   128u
#define GDR_PKT_MAX    64u     /* one USB interrupt IN = 64 bytes          */
#define GDR_TX_SLOTS   8u      /* bounded OUT frame queue (single pad)     */

enum {
    GDR_EVT_PACKET  = 1,   /* legacy raw packet (worker11 tests)           */
    GDR_EVT_ATTACH  = 2,   /* our Attach fired (a = device ptr)            */
    GDR_EVT_OPEN    = 3,   /* interrupt IN/OUT open (a=ep_in|ep_out<<8,     */
                           /*  b=in_handle, c=out_handle)                    */
    GDR_EVT_SUBMIT  = 4,   /* submit result (a=in_status, b=out_status)     */
    GDR_EVT_ERR     = 5,   /* failure (a = reason code)                    */
    GDR_EVT_STATE   = 6,   /* decoded input state (text in data[0..len))   */
    GDR_EVT_LOG     = 7,   /* legacy DPC text line (worker14; no longer used)*/
    GDR_EVT_RX      = 8,   /* interrupt-IN completion: a=status, len=bytes, */
                           /*  data[0..len) = raw payload                    */
    GDR_EVT_TXDONE  = 9,   /* interrupt-OUT completion: a=status, len=frame,*/
                           /*  b = command byte of the frame just sent       */
    GDR_EVT_IDENTIFY= 10,  /* we queued an IDENTIFY (data[0..len) = frame)  */
    GDR_EVT_ACK     = 11,  /* we queued an ACK (data[0..len) = frame)       */
    GDR_EVT_CFG     = 12,  /* config parsed: a=iface|ep_in<<8|ep_out<<16|    */
                           /*  cfg<<24, b=mps_in|mps_out<<16,                */
                           /*  c=int_in|int_out<<8                            */
    GDR_EVT_OPENCTRL= 13,  /* default control pipe opened (a = handle)      */
    GDR_EVT_STEPFAIL= 14,  /* mandatory step failed (a=step, b=status)      */
    GDR_EVT_CFGFAIL = 15,  /* no 0xFF interface (claimed-idle)              */
    GDR_EVT_CB      = 16,  /* completion discriminator (a=1 IN / 2 OUT; cb_*)*/
    GDR_EVT_DETACH  = 17,  /* RemoveDevice fired: a=generation, b=device     */
    GDR_EVT_REMOVED = 18,  /* RemoveComplete acked: a=generation, b=cancels  */
    GDR_EVT_ADDCOMPLETE = 19, /* AddComplete signalled: a=status (sign)      */
};

struct gdr_evt {
    u32 kind;
    u32 a, b, c, d;             /* kind-specific small params (handles/status) */
    u32 len;                    /* byte count in data[] (RX/TXDONE/IDENTIFY/ACK/STATE) */
    u32 seq;                    /* event sequence (monotonic, main-loop visible)  */
    u32 req_id;                 /* URB request id this event belongs to (0=n/a)   */
    u32 tick;                   /* coarse main-loop tick (ms) at completion time  */
    /* completion discriminator — which URB actually arrived and its raw fields,
     * so one run shows whether an OUT is routed to the IN callback or a buffer
     * is crossed. Filled only for RX/TXDONE events; zero otherwise. */
    u32 cb_urb;                 /* URB identity 1=in 2=tx 3=open 4=ctrl 0=other   */
    u32 cb_fn;                  /* Hdr.Function                                  */
    u32 cb_eh;                  /* EndpointHandle (+0x10)                        */
    u32 cb_buf;                 /* TransferBuffer identity 1=rx 2=tx 3=cfg 0=other*/
    u32 cb_flags;               /* FlagB0 | FlagB1<<8 | Direction<<16            */
    u32 cb_len14;               /* TransferLength (+0x14) at completion           */
    u32 cb_len20;               /* mapped length (+0x20) at completion            */
    u8  data[GDR_PKT_MAX];      /* raw packet bytes / state-line bytes       */
};

struct gdr_ring {
    struct gdr_evt slots[GDR_RING_CAP];
    volatile u32 head;          /* producer (DPC) append index — never reset     */
    volatile u32 tail;          /* consumer (main) pop index                      */
    volatile u32 overflow;      /* producer drop counter (incremented on full)    */
    volatile u32 count;         /* LEGACY mirror of head-tail, for old host tests */
};

static void gdr_ring_reset(struct gdr_ring *r) {
    r->head = 0; r->tail = 0; r->overflow = 0; r->count = 0;
}

/* Single-producer (DPC) bounded handoff. The producer owns `head`, the consumer
 * owns `tail`; neither resets the other's index, so a completion can never
 * overwrite an event the main loop has not yet consumed. Returns 1 recorded,
 * 0 dropped (counted in overflow). No allocation, no calls. */
static int gdr_ring_push(struct gdr_ring *r, const struct gdr_evt *e) {
    u32 h = r->head;
    if (h - r->tail >= GDR_RING_CAP) { r->overflow++; return 0; }
    r->slots[h % GDR_RING_CAP] = *e;
    r->head = h + 1;
    r->count = r->head - r->tail;    /* legacy mirror only */
    return 1;
}

/* Consumer (main loop) pop: copy one event out, advance tail. Returns 1 if a
 * slot was returned, 0 if empty. Never resets head. */
static int gdr_ring_pop(struct gdr_ring *r, struct gdr_evt *out) {
    u32 t = r->tail;
    if (t == r->head) return 0;
    *out = r->slots[t % GDR_RING_CAP];
    r->tail = t + 1;
    return 1;
}

static u32 gdr_ring_pending(const struct gdr_ring *r) { return r->head - r->tail; }

/* Read and clear the producer's drop counter. A drop that races this read is
 * only a cosmetic lost overflow count, never lost payload. */
static u32 gdr_ring_take_overflow(struct gdr_ring *r) {
    u32 o = r->overflow; r->overflow = 0; return o;
}

/* LEGACY drain, retained ONLY so the read-only worker11/15 host suites keep
 * compiling. It hard-resets the ring (head=tail=0), which is UNSAFE under a
 * concurrent producer; production code (main.c) uses gdr_ring_pop. */
static void gdr_ring_drain(struct gdr_ring *r, u32 *count_out, u32 *overflow_out) {
    *count_out = r->head - r->tail;
    *overflow_out = r->overflow;
    gdr_ring_reset(r);
}

/* ------------------------------------------------------------------ */
/* 3. hex / text formatting                                            */
/* ------------------------------------------------------------------ */

static const char GDR_HEX[] = "0123456789abcdef";

static size_t gdr_hex_u(char *o, size_t cap, size_t n, u32 v, int nibbles) {
    int sh = (nibbles - 1) * 4;
    for (; sh >= 0; sh -= 4) { if (n + 1 < cap) o[n++] = GDR_HEX[(v >> sh) & 15]; }
    return n;
}
static size_t gdr_str(char *o, size_t cap, size_t n, const char *s) {
    while (*s && n + 1 < cap) o[n++] = *s++;
    return n;
}
static size_t gdr_dec(char *o, size_t cap, size_t n, u32 v) {
    char tmp[11]; int t = 0;
    if (v == 0) { if (n + 1 < cap) o[n++] = '0'; return n; }
    while (v && t < 10) { tmp[t++] = (char)('0' + (v % 10)); v /= 10; }
    while (t > 0 && n + 1 < cap) o[n++] = tmp[--t];
    return n;
}

/* "PACKET seq=NNN n=LL 41 05 20 ... " — a raw packet dump (<= 64 bytes). */
static size_t gdr_format_packet(char *o, size_t cap, const u8 *data, u32 len, u32 seq) {
    size_t n = 0;
    n = gdr_str(o, cap, n, "PACKET seq="); n = gdr_dec(o, cap, n, seq);
    n = gdr_str(o, cap, n, " n=");         n = gdr_dec(o, cap, n, len);
    n = gdr_str(o, cap, n, " ");
    for (u32 i = 0; i < len && i < GDR_PKT_MAX; i++) {
        n = gdr_hex_u(o, cap, n, data[i], 2);
        if (n + 1 < cap) o[n++] = ' ';
    }
    n = gdr_str(o, cap, n, "\n");
    if (n < cap) o[n] = '\0';
    return n;
}

/* Format the completion discriminator as " CB urb=.. fn=.. eh=0x.. buf=..
 * flags=a,b,c l14=.. l20=..". Only RX/TXDONE events populate these fields. */
static size_t gdr_format_cb(char *o, size_t cap, size_t n, const struct gdr_evt *e) {
    static const char *URB[] = { "?", "in", "tx", "open", "ctrl" };
    static const char *BUF[] = { "?", "rx", "tx", "cfg", "stage" };
    u32 uu = e->cb_urb < 5 ? e->cb_urb : 0;
    u32 bb = e->cb_buf < 5 ? e->cb_buf : 0;
    n = gdr_str(o, cap, n, " urb="); n = gdr_str(o, cap, n, URB[uu]);
    n = gdr_str(o, cap, n, " fn="); n = gdr_dec(o, cap, n, e->cb_fn);
    n = gdr_str(o, cap, n, " eh=0x"); n = gdr_hex_u(o, cap, n, e->cb_eh, 8);
    n = gdr_str(o, cap, n, " buf="); n = gdr_str(o, cap, n, BUF[bb]);
    n = gdr_str(o, cap, n, " flags=");
    n = gdr_dec(o, cap, n, e->cb_flags & 0xFF);
    n = gdr_str(o, cap, n, ","); n = gdr_dec(o, cap, n, (e->cb_flags >> 8) & 0xFF);
    n = gdr_str(o, cap, n, ","); n = gdr_dec(o, cap, n, (e->cb_flags >> 16) & 0xFF);
    n = gdr_str(o, cap, n, " l14="); n = gdr_dec(o, cap, n, e->cb_len14);
    n = gdr_str(o, cap, n, " l20="); n = gdr_dec(o, cap, n, e->cb_len20);
    return n;
}

/* Render ONE raw ring event into a '\n'-terminated line. Formatting happens
 * HERE, at drain time (the DPC completion only pushes the
 * raw event). cap MUST be >= 256 so a full 64-byte packet + every prefix fits;
 * the result always ends with '\n'. Returns bytes written (incl. the newline). */
static size_t gdr_format_event(char *o, size_t cap, const struct gdr_evt *e) {
    size_t n = 0; u32 i;
    switch (e->kind) {
    case GDR_EVT_RX:
        n = gdr_str(o, cap, n, "RX seq="); n = gdr_dec(o, cap, n, e->seq);
        n = gdr_str(o, cap, n, " status=0x"); n = gdr_hex_u(o, cap, n, e->a, 8);
        n = gdr_str(o, cap, n, " req="); n = gdr_dec(o, cap, n, e->b);
        n = gdr_str(o, cap, n, " id="); n = gdr_dec(o, cap, n, e->req_id);
        n = gdr_str(o, cap, n, " n="); n = gdr_dec(o, cap, n, e->len);
        n = gdr_str(o, cap, n, " ");
        for (i = 0; i < e->len && i < GDR_PKT_MAX; i++) {
            n = gdr_hex_u(o, cap, n, e->data[i], 2);
            if (n + 1 < cap) o[n++] = ' ';
        }
        n = gdr_str(o, cap, n, "\n");
        break;
    case GDR_EVT_CB:
        n = gdr_str(o, cap, n, "CB kind=");
        n = gdr_str(o, cap, n, (e->a == 2) ? "tx" : "in");
        n = gdr_format_cb(o, cap, n, e);
        n = gdr_str(o, cap, n, "\n");
        break;
    case GDR_EVT_TXDONE:
        n = gdr_str(o, cap, n, "TXDONE seq="); n = gdr_dec(o, cap, n, e->seq);
        n = gdr_str(o, cap, n, " status=0x"); n = gdr_hex_u(o, cap, n, e->a, 8);
        n = gdr_str(o, cap, n, " req="); n = gdr_dec(o, cap, n, e->d);
        n = gdr_str(o, cap, n, " id="); n = gdr_dec(o, cap, n, e->req_id);
        n = gdr_str(o, cap, n, " len="); n = gdr_dec(o, cap, n, e->len);
        n = gdr_str(o, cap, n, " cmd=0x"); n = gdr_hex_u(o, cap, n, e->b, 2);
        n = gdr_str(o, cap, n, "\n");
        break;
    case GDR_EVT_IDENTIFY:
        n = gdr_str(o, cap, n, "IDENTIFY seq="); n = gdr_dec(o, cap, n, e->seq);
        n = gdr_str(o, cap, n, " ");
        for (i = 0; i < e->len && i < GDR_PKT_MAX; i++) { n = gdr_hex_u(o, cap, n, e->data[i], 2); if (n + 1 < cap) o[n++] = ' '; }
        n = gdr_str(o, cap, n, "\n");
        break;
    case GDR_EVT_ACK:
        n = gdr_str(o, cap, n, "ACK seq="); n = gdr_dec(o, cap, n, e->seq);
        n = gdr_str(o, cap, n, " ");
        for (i = 0; i < e->len && i < GDR_PKT_MAX; i++) { n = gdr_hex_u(o, cap, n, e->data[i], 2); if (n + 1 < cap) o[n++] = ' '; }
        n = gdr_str(o, cap, n, "\n");
        break;
    case GDR_EVT_ATTACH:
        n = gdr_str(o, cap, n, "GIP_ATTACH dev=0x"); n = gdr_hex_u(o, cap, n, e->a, 8);
        n = gdr_str(o, cap, n, " seq="); n = gdr_dec(o, cap, n, e->seq);
        n = gdr_str(o, cap, n, "\n");
        break;
    case GDR_EVT_OPENCTRL:
        n = gdr_str(o, cap, n, "OPENCTRL hnd=0x"); n = gdr_hex_u(o, cap, n, e->a, 8);
        n = gdr_str(o, cap, n, "\n");
        break;
    case GDR_EVT_CFG: {
        u32 iface = e->a & 0xFF, ep_in = (e->a >> 8) & 0xFF, ep_out = (e->a >> 16) & 0xFF, cfgv = (e->a >> 24) & 0xFF;
        u32 mps_in = e->b & 0xFFFF, mps_out = (e->b >> 16) & 0xFFFF;
        u32 int_in = e->c & 0xFF, int_out = (e->c >> 8) & 0xFF;
        n = gdr_str(o, cap, n, "CFG iface="); n = gdr_dec(o, cap, n, iface);
        n = gdr_str(o, cap, n, " ep_in=0x"); n = gdr_hex_u(o, cap, n, ep_in, 2);
        n = gdr_str(o, cap, n, " ep_out=0x"); n = gdr_hex_u(o, cap, n, ep_out, 2);
        n = gdr_str(o, cap, n, " mps_in="); n = gdr_dec(o, cap, n, mps_in);
        n = gdr_str(o, cap, n, " mps_out="); n = gdr_dec(o, cap, n, mps_out);
        n = gdr_str(o, cap, n, " int_in="); n = gdr_dec(o, cap, n, int_in);
        n = gdr_str(o, cap, n, " int_out="); n = gdr_dec(o, cap, n, int_out);
        n = gdr_str(o, cap, n, " cfgval="); n = gdr_dec(o, cap, n, cfgv);
        n = gdr_str(o, cap, n, "\n");
        break; }
    case GDR_EVT_OPEN: {
        u32 ep_in = e->a & 0xFF, ep_out = (e->a >> 8) & 0xFF;
        n = gdr_str(o, cap, n, "OPEN in=0x"); n = gdr_hex_u(o, cap, n, ep_in, 2);
        n = gdr_str(o, cap, n, " out=0x"); n = gdr_hex_u(o, cap, n, ep_out, 2);
        n = gdr_str(o, cap, n, " in_hnd=0x"); n = gdr_hex_u(o, cap, n, e->b, 8);
        n = gdr_str(o, cap, n, " out_hnd=0x"); n = gdr_hex_u(o, cap, n, e->c, 8);
        n = gdr_str(o, cap, n, " out_flags=1,0,0");
        n = gdr_str(o, cap, n, "\n");
        break; }
    case GDR_EVT_STEPFAIL:
        n = gdr_str(o, cap, n, "STEPFAIL step="); n = gdr_dec(o, cap, n, e->a);
        n = gdr_str(o, cap, n, " status=0x"); n = gdr_hex_u(o, cap, n, e->b, 8);
        n = gdr_str(o, cap, n, "\n");
        break;
    case GDR_EVT_CFGFAIL:
        n = gdr_str(o, cap, n, "CFGFAIL no_ff_iface\n");
        break;
    case GDR_EVT_ERR:
        n = gdr_str(o, cap, n, "ERROR code="); n = gdr_dec(o, cap, n, e->a);
        n = gdr_str(o, cap, n, " seq="); n = gdr_dec(o, cap, n, e->seq);
        n = gdr_str(o, cap, n, "\n");
        break;
    case GDR_EVT_DETACH:
        n = gdr_str(o, cap, n, "DETACH gen="); n = gdr_dec(o, cap, n, e->a);
        n = gdr_str(o, cap, n, " dev=0x");    n = gdr_hex_u(o, cap, n, e->b, 8);
        n = gdr_str(o, cap, n, "\n");
        break;
    case GDR_EVT_REMOVED:
        n = gdr_str(o, cap, n, "REMOVED gen="); n = gdr_dec(o, cap, n, e->a);
        n = gdr_str(o, cap, n, " closes=");     n = gdr_dec(o, cap, n, e->b);
        n = gdr_str(o, cap, n, "\n");
        break;
    case GDR_EVT_ADDCOMPLETE:
        n = gdr_str(o, cap, n, "ADDCOMPLETE status=0x");
        n = gdr_hex_u(o, cap, n, e->a, 8);
        n = gdr_str(o, cap, n, "\n");
        break;
    case GDR_EVT_STATE:
    case GDR_EVT_LOG:
    default:
        for (i = 0; i < e->len && i < GDR_PKT_MAX; i++) { if (n + 1 < cap) o[n++] = e->data[i]; }
        if (n == 0 || o[n - 1] != '\n') { if (n + 1 < cap) o[n++] = '\n'; }
        break;
    }
    if (n < cap) o[n] = '\0';
    return n;
}

/* ------------------------------------------------------------------ */
/* 3b. GIP constants + frame builders (byte-for-byte from core/gip.c)  */
/* ------------------------------------------------------------------ */

#define GIP_CMD_ACK       0x01
#define GIP_CMD_ANNOUNCE  0x02
#define GIP_CMD_STATUS    0x03
#define GIP_CMD_IDENTIFY  0x04
#define GIP_CMD_POWER     0x05
#define GIP_CMD_RUMBLE    0x09
#define GIP_CMD_LED       0x0a
#define GIP_CMD_INPUT     0x20

#define GIP_OPT_ACK         0x10   /* receiver must ACK (core/gip.c GIP_OPT_ACKNOWLEDGE) */
#define GIP_OPT_INTERNAL    0x20
#define GIP_OPT_CHUNK_START 0x40
#define GIP_OPT_CHUNK       0x80
#define GIP_CLIENT_ID       0x0fu

/* LEB128 varint (core/gip.c encode_varint). */
static int gdr_varint(u8 *buf, u32 val) {
    int i;
    for (i = 0; i < 4; i++) {
        buf[i] = (u8)val;
        if (val > 0x7f) buf[i] |= 0x80;
        val >>= 7;
        if (!val) break;
    }
    return i + 1;
}

/* Build one small unchunked GIP command frame into out[64]; returns length.
 * Header = command, options(client-id 0), sequence, LEB128(packet_length). */
static int gdr_gip_frame(u8 *out, u8 command, u8 options, u8 sequence,
                         const u8 *payload, u32 plen) {
    int n = 0;
    out[n++] = command;
    out[n++] = (u8)((options & ~GIP_CLIENT_ID) | 0);
    out[n++] = sequence;
    n += gdr_varint(out + n, plen);
    if (payload && plen) {
        for (u32 i = 0; i < plen; i++) out[n++] = payload[i];
    }
    return n;
}

static int gdr_build_power_on(u8 *out, u8 seq) {
    static const u8 p[1] = { 0x00 };
    return gdr_gip_frame(out, GIP_CMD_POWER, GIP_OPT_INTERNAL, seq, p, 1);
}
static int gdr_build_led(u8 *out, u8 seq) {
    static const u8 p[3] = { 0x00, 0x01, 20 };   /* GIP_LED_BRIGHTNESS_DEFAULT */
    return gdr_gip_frame(out, GIP_CMD_LED, GIP_OPT_INTERNAL, seq, p, 3);
}
static int gdr_build_rumble_stop(u8 *out, u8 seq) {
    /* all motors off; required by some gamepads before input. Uses xpad's
     * quiet rumbleend form (repeat byte 0x00), not core/gip.c's 0xeb spin-down. */
    static const u8 p[9] = { 0x00, 0x0f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };
    return gdr_gip_frame(out, GIP_CMD_RUMBLE, 0, seq, p, 9);
}
static int gdr_build_identify(u8 *out, u8 seq) {
    return gdr_gip_frame(out, GIP_CMD_IDENTIFY, GIP_OPT_INTERNAL, seq, 0, 0);
}
/* core/gip.c acknowledge(): ACK, INTERNAL, echo the incoming frame's sequence,
 * payload = 00 <cmd> 20 <le16 (chunk_offset+packet_length)> 00 00 00 00. */
static int gdr_build_ack(u8 *out, u8 seq, u8 ack_cmd, u16 ack_len) {
    u8 p[9] = { 0x00, ack_cmd, GIP_OPT_INTERNAL, 0, 0, 0, 0, 0, 0 };
    p[3] = (u8)(ack_len & 0xFF);
    p[4] = (u8)((ack_len >> 8) & 0xFF);
    return gdr_gip_frame(out, GIP_CMD_ACK, GIP_OPT_INTERNAL, seq, p, 9);
}
/* S-init lives in section 5 (built after the S0..S5 chain); forward-declare it
 * so the wired state machine above can enqueue it in start_gamepad. */
static int gdr_build_s_init(u8 *out, u8 seq);

/* ------------------------------------------------------------------ */
/* 3c. GIP RX decoder + wired no-auth state machine (mirror core/gip.c)*/
/* ------------------------------------------------------------------ */

#define GDR_LE16(p) ((u16)((p)[0] | ((p)[1] << 8)))

/* Fixed 18-byte OG XINPUT_GAMEPAD snapshot (og_gamepad.h). */
struct gdr_snapshot {
    u16 buttons;                /* dpad/start/back/thumb (OG_GP_* bits) */
    u8  analog[8];              /* A B X Y BLACK WHITE LT RT            */
    s16 lx, ly, rx, ry;
};

struct gdr_gip {
    int  started;
    int  identified;
    int  gamepad;
    int  ready;
    int  fallback;              /* qualified first-party wired fallback       */
    int  s_init_pending;        /* power-on sent; S-init follows on completion */
    u8   sequence;              /* next tx sequence (never 0) */
    u16  vendor, product, version;
    int  did_announce;
    struct gdr_snapshot snap;
    int  snapshot_valid;
    u32  input_reports;
    u32  unknown_cmds;
    u8   tx[8][64];
    u8   txlen[8];
    u32  txh, txt, tx_dropped;
    int  turned_off;
    u32  announces;             /* W63: every ANNOUNCE frame seen (any len)   */
    u32  rehandshakes;          /* W63: wired re-handshakes started by ANNOUNCE */
};

/* init: activate the state machine. Power-on is sent on the first poll tick
 * (gdr_gip_poll), mirroring xpad's power_on-at-open; identify is only ever
 * sent in reply to an announce (gdr_rx_announce). */
static void gdr_gip_init(struct gdr_gip *m, u32 now_ms) {
    u32 i;
    (void)now_ms;
    for (i = 0; i < 8; i++) m->txlen[i] = 0;
    m->txh = m->txt = m->tx_dropped = 0;
    m->started = 1;
    m->identified = m->gamepad = m->ready = 0;
    m->fallback = m->s_init_pending = 0;
    m->did_announce = m->snapshot_valid = m->turned_off = 0;
    m->sequence = 0;
    m->vendor = m->product = m->version = 0;
    m->input_reports = m->unknown_cmds = 0;
    m->snap.buttons = 0;
    for (i = 0; i < 8; i++) m->snap.analog[i] = 0;
    m->snap.lx = m->snap.ly = m->snap.rx = m->snap.ry = 0;
}

static u8 gdr_next_seq(struct gdr_gip *m) {
    u8 s = ++m->sequence;
    return s ? s : ++m->sequence;
}

/* enqueue one outgoing packet (backpressure: drop-and-count the NEW packet) */
static int gdr_tx_send(struct gdr_gip *m, const u8 *data, int len) {
    u32 s;
    if (!data || len <= 0 || len > 64) return 0;
    if (m->txh - m->txt >= 8) { m->tx_dropped++; return 0; }
    s = m->txh % 8;
    for (int i = 0; i < len; i++) m->tx[s][i] = data[i];
    m->txlen[s] = (u8)len;
    m->txh++;
    return 1;
}

/* pop the oldest queued packet; >0 = length, 0 = empty, never truncates */
static int gdr_tx_drain(struct gdr_gip *m, u8 *out, int max) {
    u32 s; int n;
    if (m->txh == m->txt) return 0;
    s = m->txt % 8;
    n = m->txlen[s];
    if (n > max) return -1;
    for (int i = 0; i < n; i++) out[i] = m->tx[s][i];
    m->txt++;
    return n;
}

static void gdr_start_gamepad(struct gdr_gip *m) {
    u8 buf[64];
    int n;
    /* xpad/tusb init order for a first-party wired pad: power-on -> S-init
     * (force USB mode) -> LED -> rumble-off. Monotonic non-zero sequence.
     * This full 4-frame order is retained ONLY for the announce->identify
     * path; the no-announce wired path uses the minimal serialized startup
     * (gdr_gip_qualify_wired), where LED/rumble are out of scope. */
    n = gdr_build_power_on(buf, gdr_next_seq(m));    gdr_tx_send(m, buf, n);
    n = gdr_build_s_init(buf, gdr_next_seq(m));      gdr_tx_send(m, buf, n);
    n = gdr_build_led(buf, gdr_next_seq(m));         gdr_tx_send(m, buf, n);
    n = gdr_build_rumble_stop(buf, gdr_next_seq(m)); gdr_tx_send(m, buf, n);
    m->ready = 1;
}

/* Qualified first-party wired startup (no announce, no identify): by the time
 * this is called the fetched config descriptor confirmed a 0xFF/47/D0 interface
 * with an interrupt IN+OUT pair and both endpoints are open — sufficient
 * first-party identity for 045e:0b12, mirroring the hardened core fallback
 * (core/gip.c:721-725 sets identified/gamepad/fallback before decoding).
 *
 * Sets gamepad so gdr_rx_input decodes a following 0x20 frame (the prior bug
 * left gamepad=0 on the no-identify path and silently discarded real input),
 * and enqueues the MINIMAL startup: power-on only now; S-init is sent later,
 * serialized on power-on's actual successful OUT completion
 * (gdr_gip_on_power_done). LED/rumble are excluded for this slice. Does NOT
 * touch snapshot_valid — that stays false until a real completed input frame. */
static void gdr_gip_qualify_wired(struct gdr_gip *m) {
    u8 buf[64];
    int n;
    if (m->gamepad) return;                 /* already qualified */
    m->gamepad = 1;
    m->identified = 1;
    m->fallback = 1;
    n = gdr_build_power_on(buf, gdr_next_seq(m));
    if (gdr_tx_send(m, buf, n)) {
        m->ready = 1;
        m->s_init_pending = 1;              /* S-init follows power-on done */
    }
}

/* Send the follow-up S-init (05 20 ss 0f 06 .. 55 53) exactly once, after the
 * power-on OUT frame has completed successfully. Serialized on completion, not
 * time. Called from the main loop when a successful POWer OUT completion is
 * observed. */
static void gdr_gip_on_power_done(struct gdr_gip *m) {
    u8 buf[64];
    int n;
    if (!m->s_init_pending) return;
    n = gdr_build_s_init(buf, gdr_next_seq(m));
    if (gdr_tx_send(m, buf, n)) m->s_init_pending = 0;
}

static void gdr_rx_announce(struct gdr_gip *m, const u8 *data, u32 len) {
    u8 buf[64]; int n;
    m->announces++;                         /* W63: count BEFORE the len check */
    if (m->fallback && m->identified) {
        /* W63 (W1): a wired pad qualified at attach that later wakes and
         * ANNOUNCES got no reply before (identified already set), so it kept
         * flashing. Re-run the minimal wired startup: a fresh power-on now,
         * S-init on its successful OUT completion (gdr_gip_on_power_done).
         * The snapshot is kept; no timer, no periodic resend. */
        n = gdr_build_power_on(buf, gdr_next_seq(m));
        if (gdr_tx_send(m, buf, n)) m->s_init_pending = 1;
        m->ready = 1;
        m->rehandshakes++;
        m->did_announce = 1;
        return;
    }
    if (len != 28) return;
    if (!m->vendor && !m->product) {
        m->vendor  = GDR_LE16(data + 8);
        m->product = GDR_LE16(data + 10);
        m->version = (u16)(GDR_LE16(data + 12) << 8 | GDR_LE16(data + 14));
    }
    m->did_announce = 1;
    if (!m->identified) {
        n = gdr_build_identify(buf, gdr_next_seq(m));
        gdr_tx_send(m, buf, n);
    }
}

static int gdr_rx_identify_class(const char *s, int len, const char *needle, int nlen) {
    int i;
    if (len != nlen) return 0;
    for (i = 0; i < nlen; i++) if (s[i] != needle[i]) return 0;
    return 1;
}

static void gdr_rx_identify(struct gdr_gip *m, const u8 *data, u32 len) {
    const u8 *base = data + 16;
    u32 blen, off;
    u8 count;
    if (len < 32 || m->identified) return;
    blen = len - 16;
    off = GDR_LE16(data + 26);
    if (off + 1 > blen) return;
    count = base[off++];
    for (u8 i = 0; i < count; i++) {
        u16 sl;
        if (off + 2 > blen) return;
        sl = GDR_LE16(base + off); off += 2;
        if (!sl || off + sl > blen) return;
        if (gdr_rx_identify_class((const char *)base + off, sl,
                                  "Windows.Xbox.Input.Gamepad", 26))
            m->gamepad = 1;
        off += sl;
    }
    m->identified = 1;
    if (m->gamepad && !m->ready)
        gdr_start_gamepad(m);
}

static void gdr_rx_status(struct gdr_gip *m, const u8 *data, u32 len) {
    if (len < 4) return;
    if (!(data[0] & 0x80) && m->identified) {
        m->turned_off = 1;
        m->identified = m->gamepad = m->ready = 0;
        m->snapshot_valid = 0;
        m->snap.buttons = 0;
    }
}

static void gdr_snap_from_input(struct gdr_snapshot *g, const u8 *data) {
    u16 b = GDR_LE16(data);
    u16 lt = GDR_LE16(data + 2), rt = GDR_LE16(data + 4);
    u16 bits = 0;
    g->buttons = 0;
    /* dpad / start / back / thumb */
    if (b & (1u<<2)) bits |= 0x0010;         /* MENU    -> OG START  */
    if (b & (1u<<3)) bits |= 0x0020;         /* VIEW    -> OG BACK   */
    if (b & (1u<<14)) bits |= 0x0040;        /* STICK_L -> OG LTHUMB */
    if (b & (1u<<15)) bits |= 0x0080;        /* STICK_R -> OG RTHUMB */
    if (b & (1u<<8))  bits |= 0x0001;        /* DPAD_UP */
    if (b & (1u<<9))  bits |= 0x0002;        /* DPAD_DOWN */
    if (b & (1u<<10)) bits |= 0x0004;        /* DPAD_LEFT */
    if (b & (1u<<11)) bits |= 0x0008;        /* DPAD_RIGHT */
    g->buttons = bits;
    g->analog[0] = (b & (1u<<4))  ? 0xff : 0x00;   /* A */
    g->analog[1] = (b & (1u<<5))  ? 0xff : 0x00;   /* B */
    g->analog[2] = (b & (1u<<6))  ? 0xff : 0x00;   /* X */
    g->analog[3] = (b & (1u<<7))  ? 0xff : 0x00;   /* Y */
    g->analog[4] = (b & (1u<<12)) ? 0xff : 0x00;   /* BUMPER_L -> BLACK */
    g->analog[5] = (b & (1u<<13)) ? 0xff : 0x00;   /* BUMPER_R -> WHITE */
    g->analog[6] = (u8)((lt > 1023 ? 1023 : lt) * 255 / 1023);  /* LTRIG */
    g->analog[7] = (u8)((rt > 1023 ? 1023 : rt) * 255 / 1023);  /* RTRIG */
    g->lx = (s16)GDR_LE16(data + 6);
    g->ly = (s16)GDR_LE16(data + 8);
    g->rx = (s16)GDR_LE16(data + 10);
    g->ry = (s16)GDR_LE16(data + 12);
}

static void gdr_rx_input(struct gdr_gip *m, const u8 *data, u32 len) {
    if (len < 14 || !m->gamepad) return;
    gdr_snap_from_input(&m->snap, data);
    m->snapshot_valid = 1;
    m->input_reports++;
}

/* returns 1 if the frame consumed (dispatch handled it), 0 if unknown/ignored */
static int gdr_dispatch(struct gdr_gip *m, u8 command, u8 options,
                        const u8 *data, u32 len) {
    if (options & GIP_OPT_INTERNAL) {
        switch (command) {
        case GIP_CMD_ANNOUNCE: gdr_rx_announce(m, data, len); return 1;
        case GIP_CMD_STATUS:   gdr_rx_status(m, data, len);   return 1;
        case GIP_CMD_IDENTIFY: gdr_rx_identify(m, data, len); return 1;
        default: return 1;   /* POWER/RUMBLE/LED/ACK from pad: ignore safely */
        }
    }
    if (command == GIP_CMD_INPUT) { gdr_rx_input(m, data, len); return 1; }
    return 0;
}

static int gdr_decode_varint(const u8 *data, int len, u32 *val, int *consumed) {
    u32 v = 0; int i;
    *consumed = 0;
    for (i = 0; i < 4 && i < len; i++) {
        v |= (u32)(data[i] & 0x7f) << (i * 7);
        (*consumed)++;
        if (!(data[i] & 0x80)) { break; }
    }
    *val = v;
    return i + 1;
}

/* Feed one collected interrupt-IN buffer (which may carry several coalesced
 * GIP frames, as gip_rx does). Updates m (state machine + tx queue + snapshot).
 * Returns number of frames dispatched. */
static int gdr_gip_rx(struct gdr_gip *m, const u8 *data, int len) {
    int frames = 0;
    while (len > 3) {
        u8 command = data[0];
        u8 options = data[1];
        u8 seqb    = data[2];
        u32 pktlen; int clen, hdr;
        if (gdr_decode_varint(data + 3, len - 3, &pktlen, &clen) < 1)
            return frames;
        hdr = 3 + clen;
        if (options & GIP_OPT_CHUNK) {
            u32 off; int olen;
            gdr_decode_varint(data + hdr, len - hdr, &off, &olen);
            hdr += olen;
        }
        if (len < hdr + (int)pktlen) return frames;   /* truncated: stop */
        /* warn on out-of-range command (mirrors og_gip.cmd_known) */
        switch (command) {
        case GIP_CMD_ACK: case GIP_CMD_ANNOUNCE: case GIP_CMD_STATUS:
        case GIP_CMD_IDENTIFY: case GIP_CMD_POWER: case GIP_CMD_RUMBLE:
        case GIP_CMD_LED: case GIP_CMD_INPUT:
            break;
        default:
            m->unknown_cmds++;
            break;
        }
        /* core/gip.c process_pkt: a frame that sets the acknowledge bit must be
         * ACKed or the pad can stall (chunked transfers / mode reports). */
        if (options & GIP_OPT_ACK) {
            u8 ab[64];
            int an = gdr_build_ack(ab, seqb, command, (u16)pktlen);
            gdr_tx_send(m, ab, an);
        }
        gdr_dispatch(m, command, options, data + hdr, pktlen);
        frames++;
        data += hdr + pktlen;
        len  -= hdr + (int)pktlen;
    }
    return frames;
}

/* wired start: startup is now driven by ONE of two explicit paths, never a
 * blind poll-tick. (a) announce->identify -> gdr_start_gamepad (full 4-frame
 * order); (b) no-announce qualified wired -> gdr_gip_qualify_wired (minimal
 * power-on, S-init serialized on completion). This poll hook is retained only
 * as a future rumble/keepalive tick and does not start anything by itself. */
static void gdr_gip_poll(struct gdr_gip *m, u32 now_ms) {
    (void)m;
    (void)now_ms;
}

/* "buttons=0x0010 lx=-123 ly=456 rx=0 ry=0 lt=0 rt=0 A=255 B=0 X=0 Y=0 Black=0 White=0"
 * state line — ALL required input fields (face/bumper analog bytes + triggers
 * + sticks), no silent truncation of any control. Return bytes written
 * (excluding NUL). The buffer cap must be >= 96. */
static size_t gdr_format_state(char *o, size_t cap, const struct gdr_snapshot *g) {
    size_t n = 0;
    s16 v;
    n = gdr_str(o, cap, n, "buttons=0x"); n = gdr_hex_u(o, cap, n, g->buttons, 4);
    v = g->lx; if (v < 0) { n = gdr_str(o, cap, n, " lx=-"); n = gdr_dec(o, cap, n, (u32)(-(int)v)); }
              else        { n = gdr_str(o, cap, n, " lx=");  n = gdr_dec(o, cap, n, (u32)v); }
    v = g->ly; if (v < 0) { n = gdr_str(o, cap, n, " ly=-"); n = gdr_dec(o, cap, n, (u32)(-(int)v)); }
              else        { n = gdr_str(o, cap, n, " ly=");  n = gdr_dec(o, cap, n, (u32)v); }
    v = g->rx; if (v < 0) { n = gdr_str(o, cap, n, " rx=-"); n = gdr_dec(o, cap, n, (u32)(-(int)v)); }
              else        { n = gdr_str(o, cap, n, " rx=");  n = gdr_dec(o, cap, n, (u32)v); }
    v = g->ry; if (v < 0) { n = gdr_str(o, cap, n, " ry=-"); n = gdr_dec(o, cap, n, (u32)(-(int)v)); }
              else        { n = gdr_str(o, cap, n, " ry=");  n = gdr_dec(o, cap, n, (u32)v); }
    n = gdr_str(o, cap, n, " lt=");       n = gdr_dec(o, cap, n, g->analog[6]);
    n = gdr_str(o, cap, n, " rt=");       n = gdr_dec(o, cap, n, g->analog[7]);
    n = gdr_str(o, cap, n, " A=");        n = gdr_dec(o, cap, n, g->analog[0]);
    n = gdr_str(o, cap, n, " B=");        n = gdr_dec(o, cap, n, g->analog[1]);
    n = gdr_str(o, cap, n, " X=");        n = gdr_dec(o, cap, n, g->analog[2]);
    n = gdr_str(o, cap, n, " Y=");        n = gdr_dec(o, cap, n, g->analog[3]);
    n = gdr_str(o, cap, n, " Black=");    n = gdr_dec(o, cap, n, g->analog[4]);
    n = gdr_str(o, cap, n, " White=");    n = gdr_dec(o, cap, n, g->analog[5]);
    if (n < cap) o[n] = '\0';
    return n;
}

static int gdr_snap_equal(const struct gdr_snapshot *a, const struct gdr_snapshot *b) {
    if (a->buttons != b->buttons) return 0;
    if (a->lx != b->lx || a->ly != b->ly || a->rx != b->rx || a->ry != b->ry) return 0;
    for (int i = 0; i < 8; i++) if (a->analog[i] != b->analog[i]) return 0;
    return 1;
}

/* ------------------------------------------------------------------ */
/* 4. PIN HELPERS (fail-closed)                                        */
/* ------------------------------------------------------------------ */

/* Find first occurrence of pattern (0xFF == wildcard) in [mem, mem+mem_len). */
static long gdr_sig_find(const u8 *mem, size_t mem_len,
                         const u8 *pattern, size_t pattern_len) {
    size_t i, j;
    if (pattern_len == 0 || mem_len < pattern_len) return -1;
    for (i = 0; i + pattern_len <= mem_len; i++) {
        for (j = 0; j < pattern_len; j++)
            if (pattern[j] != 0xFF && mem[i + j] != pattern[j]) break;
        if (j == pattern_len) return (long)i;
    }
    return -1;
}

/* FindClassDriver shape-pin: verify the prologue is `push esi; mov eax,imm32`
 * (0x56 0xB8) and that the imm32 equals the pinned class-table begin address.
 * Returns a bitmask: 0x1 = shape ok, 0x2 = begin-imm matches. *begin_out gets
 * the live imm32 (the class-table begin) for the trampoline to re-execute.
 * Used by both main.c (fail-closed arm) and the host tests (synthetic bytes). */
static unsigned int gdr_pin_findclass(const u8 *t, u32 pinned_begin, u32 *begin_out) {
    unsigned int pins = 0;
    if (t[0] == 0x56 && t[1] == 0xB8) pins |= 0x1u;
    *begin_out = *(const u32 *)(t + 2);
    if (*begin_out == pinned_begin) pins |= 0x2u;
    return pins;
}

/* ------------------------------------------------------------------ */
/* 4b. FindClassDriver arm gate + loop policy (SHARED Xbox/host)       */
/*                                                                     */
/* The pin BITS produced by gdr_pin_findclass (shape 0x1, begin 0x2)   */
/* and the bits the arm gate requires MUST be numbered in ONE place,   */
/* or the Xbox title and the host harness disagree and the hook        */
/* fail-closes on a valid target. main.c consumes these constants,     */
/* never its own local #defines.                                       */
/* ------------------------------------------------------------------ */

#define GDR_PIN_SHAPE      (1u<<0)   /* prologue `push esi; mov eax,imm32`   */
#define GDR_PIN_BEGIN      (1u<<1)   /* begin imm equals the pinned table    */
#define GDR_PIN_WRITABLE   (1u<<2)   /* section writable per XBE headers     */
#define GDR_PIN_ALL        (GDR_PIN_SHAPE|GDR_PIN_BEGIN|GDR_PIN_WRITABLE)

/* 0 => armed, 1 => refused (fail-closed). */
static int gdr_gip_arm_gate(unsigned int pins) { return (pins == GDR_PIN_ALL) ? 0 : 1; }

/* Loop cadence — shared so the host can drive simulated time and assert the
 * fail-closed path exits on time and never touches the device. GDR_EXIT_AFTER_MS
 * is the bounded auto-return watchdog: 6 minutes for the slice2 lifecycle probe
 * so a 5-min / 3-cycle unplug-replug session fits in one run (manual BACK+START
 * on a stock pad still exits sooner). */
#define GDR_TICK_MS         250u
#define GDR_EXIT_AFTER_MS   360000u   /* 6 min auto-return (lifecycle probe) */
#define GDR_HB_PERIOD_MS    30000u    /* backstop liveness (LIVE line is per-second) */
#define GDR_LIVE_PERIOD_MS  1000u     /* per-second LIVE line cadence */

/* Transport-live guard: active GIP work (poll + OUT submit) is allowed ONLY
 * when Attach ran AND the interrupt IN endpoint opened. When the hook fails
 * to arm, Attach never runs, so both are 0 and this returns 0 — the loop then
 * never submits a URB through a NULL device/handle (the worker 11 console
 * hang: PINFAIL -> blind-start queued OUT -> NULL IUsbDevice submit). */
static int gdr_transport_live(int attached, u32 in_handle) {
    return attached && (in_handle != 0u);
}

/* ------------------------------------------------------------------ */
/* 5. Attach state machine (worker 14)                                 */
/*                                                                     */
/* Worker 13 (ogxbox/research/enum/REPORT.md) proved the stage-1 Attach*/
/* is wrong: 0xFF81 is a DEVICE-level class, so the stack has NOT      */
/* fetched the config descriptor and has NOT sent SET_CONFIGURATION    */
/* (Stage5 @0x2aef0 / Stage6 @0x2aca9 run only on the bDeviceClass==0  */
/* branch). Opening 0x81/0x01 immediately reads stale alias data on an */
/* unconfigured device. Our Attach must do, in order, what Stage4      */
/* @0x2b00b..0x2b0c7 (open default control EP + GET_DESCRIPTOR config) */
/* + Stage5 (SET_CONFIGURATION) + XID_EnumStage1 -> fOpenDevice        */
/* @0x414CD2 -> fOpenEndpoints @0x41421B do — and every step must be   */
/* driven from the URB completion (SubmitRequest is asynchronous,      */
/* completes at DISPATCH_LEVEL, worker09 §5).                          */
/*                                                                     */
/* S0 Attach           -> open DEFAULT CONTROL endpoint (fn 0x82),     */
/*                        then GET_DESCRIPTOR(config, len 9)           */
/* S1  9-byte header   -> read wTotalLength, GET_DESCRIPTOR(full)      */
/* S2  full config     -> gdr_cfg_parse (find the 0xFF interface + its */
/*                        interrupt IN/OUT), SET_CONFIGURATION         */
/* S3  SET_CONFIG done -> OPEN_ENDPOINT IN (fn 0x02)                   */
/* S4  IN open         -> OPEN_ENDPOINT OUT (fn 0x02)                  */
/* S5  OUT open        -> persistent interrupt-IN URB + handshake OUTs */
/*                                                                     */
/* Every DPC step: no heap, no file I/O, no Sleep; bounded static      */
/* buffers; negative URB Status => ring-log STEPFAIL and stop.         */
/* ------------------------------------------------------------------ */

/* Portable __stdcall for the URB completion callbacks (matches
 * ogx_urb_complete_t in ogxbox_binding_abi.h). */
#if defined(_MSC_VER)
#  define GDR_STDCALL __stdcall
#elif defined(__i386__)
#  define GDR_STDCALL __attribute__((stdcall))
#else
#  define GDR_STDCALL
#endif

typedef long (*gdr_submit_fn)(void *device, void *urb);
typedef void (GDR_STDCALL *gdr_complete_fn)(void *urb, void *ctxv);

/* Slice2 lifecycle seams. These are the Xbox __thiscall IUsbDevice methods the
 * actual title must call (AddComplete / CancelRequest / RemoveComplete); main.c
 * wires wrappers, the host harness injects fakes. Signatures re-derived from
 * map symbols ?AddComplete@IUsbDevice@@QAEXJ@Z / ?CancelRequest@IUsbDevice@@
 * QAEJPAT_URB@@@Z / ?RemoveComplete@IUsbDevice@@QAEXXZ (bin/AmpJackGip.map). */
typedef void (*gdr_add_complete_fn)(void *device, long status);
typedef long (*gdr_cancel_fn)(void *device, void *urb);
typedef void (*gdr_remove_complete_fn)(void *device);

/* Lifecycle states for one attach generation (single static ctx = one GIP pad). */
enum {
    GDR_LIFE_IDLE      = 0,  /* no attach yet / after full detach ack          */
    GDR_LIFE_ATTACHING = 1,  /* Attach ran; S0..S5 config chain in progress     */
    GDR_LIFE_LIVE      = 2,  /* S5 done, IN streaming; AddComplete(0) signalled */
    GDR_LIFE_FAILED    = 3,  /* STEPFAIL/CFGFAIL; AddComplete(<0) signalled     */
    GDR_LIFE_REMOVING  = 4   /* RemoveDevice ran; cancelling, awaiting quiesce  */
};

/* Pointer -> u32: URB CompleteProc/CompleteContext/TransferBuffer are 32-bit
 * fields on the Xbox (xb_ptr). On a 64-bit host the truncation is intentional
 * (test fixture only); route through uintptr_t so the host build stays clean. */
#if defined(_MSC_VER)
#  define GDR_P2U32(p) ((u32)(size_t)(p))
#else
#  define GDR_P2U32(p) ((u32)(uintptr_t)(p))
#endif

/* CONTROL transfer URB (Function 0x40, Length 0x30 = 48 B). Setup packet
 * (bmRequestType/bRequest/wValue/wIndex/wLength) at +0x28..0x2F is built by
 * the CLASS DRIVER (worker09 §6; ogxbox_urb_abi.h ogx_urb_transfer_urb). */
typedef struct gdr_urb_control {
    gdr_urb_header Hdr;         /* +0x00 Length=0x30, Function=0x40 */
    u32 EndpointHandle;         /* +0x10 control pipe */
    u32 TransferLength;         /* +0x14 */
    u32 TransferBuffer;         /* +0x18 */
    u8  FlagB0;                 /* +0x1C */
    u8  FlagB1;                 /* +0x1D */
    u8  Direction;              /* +0x1E */
    u8  unused_1F;
    u16 ByteCount;              /* +0x20 */
    u16 State;                  /* +0x22 */
    u32 TransferStatus;         /* +0x24 */
    u8  SetupPacket[8];         /* +0x28..+0x2F */
} gdr_urb_control;

/* CLOSE URB (VERIFIED _XID_RemoveDevice close chain, XID_CloseEndpointStateMachine
 * @0x2f133): Length 0x1c (28 B) = header + EndpointHandle@+0x10 + two reserved
 * words. Function 0xc3 closes the DEFAULT control pipe (handle @+0x10 NOT set);
 * Function 0x43 closes an explicit endpoint (handle @+0x10 from the opened pipe).
 * Submitted via SubmitRequest; each close completion is chained to close the next
 * endpoint, and the LAST close completion releases the device (RemoveComplete).
 * The class driver owns these closes: the stack's RemoveComplete frees only the
 * device ADDRESS (VERIFIED @0x305ef), never the opened endpoints. */
typedef struct gdr_urb_close {
    gdr_urb_header Hdr;         /* +0x00 Length=0x1c, Function=0xc3|0x43 */
    u32 EndpointHandle;         /* +0x10 (fn 0x43 only)                 */
    u32 Reserved14;             /* +0x14                                */
    u32 Reserved18;             /* +0x18                                */
} gdr_urb_close;

/* S-init "S" power-on frame (worker12 prior-art #6): forces a pad previously
 * paired in Bluetooth back into USB mode. Sent unconditionally (tusb_xinput
 * sends the full 19-byte form to every Xbox One pad). */
static int gdr_build_s_init(u8 *out, u8 seq) {
    static const u8 p[15] = { 0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                              0x55, 0x53, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };
    return gdr_gip_frame(out, GIP_CMD_POWER, GIP_OPT_INTERNAL, seq, p, 15);
}

/* Result of walking a fetched config descriptor. */
struct gdr_cfg_result {
    int  found;                 /* 1 if an interface with bClass 0xFF found */
    u8   iface;                 /* bInterfaceNumber of the GIP interface   */
    u8   ep_in, ep_out;         /* bEndpointAddress of interrupt IN / OUT  */
    u16  mps_in, mps_out;       /* wMaxPacketSize                          */
    u8   interval_in, interval_out;  /* bInterval                          */
    u8   cfg_value;             /* bConfigurationValue (config desc +5)    */
};

/* Walk [buf,len): find the first interface with bInterfaceClass==0xFF and its
 * interrupt (bmAttributes&3 == 3) IN/OUT endpoint descriptors. Pure: no heap,
 * no calls. Returns via *r (found=0 when none). */
static void gdr_cfg_parse(const u8 *buf, int len, struct gdr_cfg_result *r) {
    int pos = 0;
    u8  cur_class = 0;
    int in_sel = 0;          /* 1 while inside the SELECTED interface+alt-setting */
    r->found = 0; r->iface = 0;
    r->ep_in = r->ep_out = 0;
    r->mps_in = r->mps_out = 0;
    r->interval_in = r->interval_out = 0;
    r->cfg_value = 0;
    if (len >= 9) r->cfg_value = buf[5];

    while (pos + 2 <= len) {
        u8 blen = buf[pos];
        u8 btype = buf[pos + 1];
        if (blen < 2 || pos + blen > len) break;      /* malformed -> stop */
        if (btype == 4) {                             /* interface desc      */
            cur_class = buf[pos + 5];
            /* Select the FIRST 0xFF interface whose alt-setting has endpoints
             * (bNumEndpoints at +4). Real pads (045e:0b12) list every interface
             * as FF/47/D0 with several alt-settings; only IF0 alt0 is the data
             * pipe pair we want, and later alt-settings must not overwrite it. */
            in_sel = 0;
            if (cur_class == 0xFF && !r->found && buf[pos + 4] >= 2) {
                r->found = 1;
                r->iface = buf[pos + 2];
                in_sel = 1;
            }
        } else if (btype == 5 && in_sel) {            /* endpoint desc       */
            u8  addr = buf[pos + 2];
            u8  attr = buf[pos + 3];
            u16 mps  = (u16)(buf[pos + 4] | ((u16)buf[pos + 5] << 8));
            u8  intv = buf[pos + 6];
            if ((attr & 0x03u) == 0x03u) {            /* interrupt only      */
                if (addr & 0x80u) { r->ep_in = addr;  r->mps_in = mps;
                                    r->interval_in = intv; }
                else              { r->ep_out = addr; r->mps_out = mps;
                                    r->interval_out = intv; }
            }
        }
        pos += blen;
    }
}

/* Completion-driven Attach context (single global instance: only one GIP pad
 * for now — worker13 says the per-device extension lives at device+0x1c via
 * SetExtension, an ABI we do not have pinned/linked, so we use one static ctx). */
struct gdr_attach_ctx {
    void *device;                       /* IUsbDevice*                      */
    gdr_submit_fn submit;               /* SubmitRequest (real or fake)     */
    gdr_complete_fn in_complete;        /* gdr_in_complete (ring+re-submit) */
    struct gdr_ring *ring;              /* trace ring (DPC-safe push only)  */
    volatile u32 seq;
    volatile u32 rx_events;             /* interrupt-IN completions (RX)    */
    volatile u32 tx_events;             /* interrupt-OUT completions        */
    volatile int  in_flight;            /* 1 while an IN URB is pending     */
    volatile u32 state;                 /* 0..5 step marker, 6=live         */
    volatile u32 failed;                /* 0 ok / 1 STEPFAIL / 2 CFGFAIL    */
    u32 fail_step;
    u32 fail_status;

    /* request/id accounting: correlate one completion with one request and
     * make immediate submission rejections observable (in_flight=1 after a
     * blindly ignored submit result is NOT evidence of a pending request). */
    volatile u32 req_id;                /* monotonic submit counter          */
    volatile u32 in_req_id;             /* id of the in-flight IN request    */
    volatile u32 tx_req_id;             /* id of the in-flight OUT request   */
    volatile u32 in_submit_fail;        /* immediate IN submit rejections    */
    volatile u32 tx_submit_fail;        /* immediate OUT submit rejections   */
    volatile u32 in_rearm_guard;        /* re-entrancy guard (0 = not re-arming) */
    volatile u32 tick;                  /* coarse main-loop tick (ms), DPC-safe read */
    u8           tx_req_len;            /* requested OUT frame length        */
    volatile u32 cb_log;                /* 1 => emit completion-discriminator CB events */

    u32 control_handle;                 /* default control pipe (fn 0x82)   */
    u32 in_handle, out_handle;          /* interrupt IN / OUT pipes         */

    u8  ep_in, ep_out;                  /* endpoint addresses route parsed  */
    u16 mps_in, mps_out;
    u8  interval_in, interval_out;
    u8  iface;                          /* GIP interface number             */
    u8  cfg_value;                      /* bConfigurationValue              */
    u16 cfg_len;                        /* clamped config length (S1)       */

    gdr_urb_open     open_urb;          /* reused: ctrl-open, IN, OUT       */
    gdr_urb_control  ctrl_urb;          /* reused: GET_DESC 9 / full / SET  */
    u8               cfg_stage[9];
    u8               cfg_buf[256];

    gdr_urb_transfer in_urb;            /* persistent interrupt IN          */
    u8               rx_buf[64];

    /* OUT queue + one in-flight URB. tx_buf is a DEDICATED OUT DMA buffer,
     * never the IN rx_buf; TransferLength is the frame length, never mps.
     * tx_head/tx_tail = single-producer (main loop) / single-consumer (TXDONE)
     * FIFO, the same single-CPU DISPATCH_LEVEL model as gdr_ring. */
    gdr_urb_transfer tx_urb;
    u8               tx_buf[64];        /* OUT DMA buffer (NEVER IN)         */
    u8               tx_q[GDR_TX_SLOTS][64];
    u8               tx_len[GDR_TX_SLOTS];
    volatile u32     tx_head, tx_tail;
    volatile int     tx_busy;
    u8               tx_cmd;            /* command byte of the frame in flight */

    /* ---- slice2 lifecycle (attach/detach generation + cancel/close/ack) --- */
    volatile u32 generation;          /* bumped each attach and each detach    */
    volatile u32 lifecycle;           /* GDR_LIFE_*                            */
    volatile u32 detached;            /* 1 => RemoveDevice ran: stop new I/O   */
    volatile u32 add_complete_called; /* AddComplete fired-exactly-once guard  */
    long          add_status;         /* status signalled to AddComplete (last)*/
    volatile u32 remove_complete_called; /* RemoveComplete acked (0/1)         */
    volatile u32 pending;             /* accepted-but-not-completed URBs (honest) */
    volatile u32 cancel_count;        /* URBs cancelled via CancelRequest      */
    volatile u32 open_pending;        /* 1 while open_urb has an accepted req  */
    volatile u32 ctrl_pending;        /* 1 while ctrl_urb has an accepted req  */
    volatile u32 removing_in_walk;    /* 1 during the remove cancel walk       */
    gdr_add_complete_fn      add_complete;   /* Xbox: usbd_AddComplete          */
    gdr_cancel_fn            cancel_request; /* Xbox: usbd_CancelRequest        */
    gdr_remove_complete_fn   remove_complete;/* Xbox: usbd_RemoveComplete       */

    /* ---- native CLOSE chain (22-native-close): the class driver owns closing
     * every endpoint it opened (default pipe fn 0x82, IN/OUT fn 0x02); the stack's
     * RemoveComplete frees ONLY the address. Saved handles + a reused 0x1c close
     * URB + a completion-driven chain that closes default (fn 0xc3) then IN then
     * OUT (fn 0x43) before RemoveComplete. */
    gdr_urb_close  close_urb;
    u32            close_ctrl, close_in, close_out;  /* saved handles to close */
    volatile u32   close_stage;       /* 0=next ctrl 1=next in 2=next out 3=done */
    volatile u32   close_pending;     /* accepted-but-not-completed close URBs   */
    volatile u32   close_started;     /* close chain dispatched once             */
    volatile u32   close_count;       /* close URBs actually submitted           */
    volatile u32   close_submit_fail; /* immediate close-submit rejections       */

    /* ---- 30-native-lifetime: per-URB ownership that SURVIVES RemoveDevice.
     * Ownership words: own_open (open_urb), own_ctrl (ctrl_urb), and the
     * EXISTING in_flight (in_urb) / tx_busy (tx_urb), which keep their meaning
     * but are no longer cleared by RemoveDevice.
     * own = 1 from just before SubmitRequest(X) until X's completion callback
     * is delivered (or, for transfer URBs only, until the close of the pipe the
     * URB is queued on completes successfully: native OHCD retires every
     * transfer of a pipe before completing that pipe's close URB). One word per
     * URB (never a shared bitmask) so a DPC update of one URB cannot be lost by
     * a main-loop read-modify-write of another. `pending` is recomputed from
     * these words (diagnostic; it can no longer underflow or be forged to 0).
     * RemoveComplete is gated on all four being 0, no close in flight and every
     * close slot (close_ctrl/in/out) closed. */
    volatile int   own_open;          /* open_urb (S0 default / S4 IN / S5 OUT)  */
    volatile int   own_ctrl;          /* ctrl_urb (S1 / S2 / SET_CONFIGURATION)   */
    volatile u32   close_which;       /* close URB in flight for: 1 ctrl 2 in 3 out */
    volatile u32   late_open_captured;/* handles from opens completing after remove */
    volatile u32   stale_completions; /* completions for a URB we do not own: ignored */
    volatile u32   retired_by_close;  /* transfer URBs retired by their pipe close  */
};

static void gdr_own_sync(struct gdr_attach_ctx *ctx) {
    ctx->pending = (u32)((ctx->own_open != 0) + (ctx->own_ctrl != 0) + (ctx->in_flight != 0) + (ctx->tx_busy != 0));
}
static int gdr_own_any(const struct gdr_attach_ctx *ctx) {
    return (ctx->own_open | ctx->own_ctrl | ctx->in_flight | ctx->tx_busy) != 0;
}
/* take ownership BEFORE SubmitRequest: an inline completion inside the submit
 * then finds the flag set and consumes it exactly once. */
static void gdr_own_take(struct gdr_attach_ctx *ctx, volatile int *own) {
    *own = 1; gdr_own_sync(ctx);
}
/* 1 = we owned it and now released it; 0 = not owned (duplicate/stale/late). */
static int gdr_own_drop(struct gdr_attach_ctx *ctx, volatile int *own) {
    if (!*own) { gdr_own_sync(ctx); return 0; }   /* resync: caller may have cleared it */
    *own = 0; gdr_own_sync(ctx);
    return 1;
}

/* Forward decls: these slice2 lifecycle helpers are DEFINED later (after the
 * completion chain) but the OUT/IN completion callbacks below (gdr_tx_*,
 * gdr_in_complete) call them before that point. */
static void gdr_retire_check(struct gdr_attach_ctx *ctx);
static void gdr_close_next(struct gdr_attach_ctx *ctx);

/* ---- structured ring events (RAW: no text built in the DPC) ------------- */
/* Each helper stores kind + small integers/bytes; the text line is built by
 * gdr_format_event at DRAIN time (main loop) with a 256-byte buffer. This fixes
 * worker14's log truncation: CFG/OPEN were cut at GDR_PKT_MAX=64 and lost their
 * trailing '\n'. */

static void gdr_evt_openctrl(struct gdr_attach_ctx *ctx, u32 handle) {
    struct gdr_evt e; memset(&e, 0, sizeof e);
    e.kind = GDR_EVT_OPENCTRL; e.a = handle; e.seq = ++ctx->seq;
    gdr_ring_push(ctx->ring, &e);
}
static void gdr_evt_cfg(struct gdr_attach_ctx *ctx, const struct gdr_cfg_result *r) {
    struct gdr_evt e; memset(&e, 0, sizeof e);
    e.kind = GDR_EVT_CFG; e.seq = ++ctx->seq;
    e.a = (u32)r->iface | ((u32)r->ep_in << 8) | ((u32)r->ep_out << 16) | ((u32)r->cfg_value << 24);
    e.b = (u32)r->mps_in | ((u32)r->mps_out << 16);
    e.c = (u32)r->interval_in | ((u32)r->interval_out << 8);
    gdr_ring_push(ctx->ring, &e);
}
static void gdr_evt_open(struct gdr_attach_ctx *ctx) {
    struct gdr_evt e; memset(&e, 0, sizeof e);
    e.kind = GDR_EVT_OPEN; e.seq = ++ctx->seq;
    e.a = (u32)ctx->ep_in | ((u32)ctx->ep_out << 8);
    e.b = ctx->in_handle;
    e.c = ctx->out_handle;
    e.d = 0;   /* out_flags literal 1,0,0 (FlagB0=1,FlagB1=0,Direction=0, XID OUT) */
    gdr_ring_push(ctx->ring, &e);
}
static void gdr_evt_cfgfail(struct gdr_attach_ctx *ctx) {
    struct gdr_evt e; memset(&e, 0, sizeof e);
    ctx->failed = 2; ctx->fail_step = 2;
    e.kind = GDR_EVT_CFGFAIL; e.seq = ++ctx->seq;
    gdr_ring_push(ctx->ring, &e);
}

/* ---- OUT queue (one URB, its own CompleteProc, never the IN pipe) ------- */

static void GDR_STDCALL gdr_tx_complete(void *urb, void *ctxv);

/* Enqueue one OUT frame (called from the main loop after the state machine
 * decides what to send); returns 1 stored, 0 dropped. */
static int gdr_tx_enqueue(struct gdr_attach_ctx *ctx, const u8 *data, int len) {
    u32 h; u32 s; int i;
    if (!data || len <= 0 || len > 64) return 0;
    h = ctx->tx_head;
    if (h - ctx->tx_tail >= GDR_TX_SLOTS) return 0;   /* backpressure: drop NEW */
    s = h % GDR_TX_SLOTS;
    for (i = 0; i < len; i++) ctx->tx_q[s][i] = data[i];
    ctx->tx_len[s] = (u8)len;
    ctx->tx_head = h + 1;               /* publish head LAST                 */
    return 1;
}

/* Submit the next queued OUT frame. One in flight: called from the main loop
 * (kick) and from gdr_tx_complete (DISPATCH_LEVEL). TransferLength is the frame
 * length (tx_len), never the endpoint mps. TransferBuffer is the dedicated
 * tx_buf, never the IN rx_buf. */
static void gdr_tx_submit_next(struct gdr_attach_ctx *ctx) {
    u32 t; u32 i; gdr_urb_transfer *u;
    if (!ctx->device || !ctx->out_handle || ctx->tx_busy || ctx->detached) return;
    while (ctx->tx_head != ctx->tx_tail) {
        t = ctx->tx_tail % GDR_TX_SLOTS;
        if (ctx->tx_len[t] == 0) { ctx->tx_tail++; continue; }
        u = &ctx->tx_urb;
        for (i = 0; i < sizeof *u; i++) ((u8*)u)[i] = 0;
        u->Hdr.Length   = 0x28;
        u->Hdr.Function = 0x41;
        u->Hdr.CompleteProc    = GDR_P2U32(gdr_tx_complete);
        u->Hdr.CompleteContext = GDR_P2U32(ctx);
        u->EndpointHandle = ctx->out_handle;
        u->TransferLength = ctx->tx_len[t];      /* frame length, NOT mps   */
        for (i = 0; i < ctx->tx_len[t]; i++) ctx->tx_buf[i] = ctx->tx_q[t][i];
        u->TransferBuffer = GDR_P2U32(ctx->tx_buf);  /* dedicated OUT buffer */
        u->FlagB0 = 1; u->FlagB1 = 0; u->Direction = 0; /* XID OUT URB (VERIFIED) */
        ctx->tx_cmd     = ctx->tx_buf[0];
        ctx->tx_req_len = ctx->tx_len[t];        /* requested OUT length      */
        ctx->tx_busy = 1;
        ctx->tx_tail++;                       /* consume this frame          */
        ctx->req_id++;
        ctx->tx_req_id = ctx->req_id;
        gdr_own_take(ctx, &ctx->tx_busy);
        if (ctx->detached) {
            /* F6 narrowing: RemoveDevice (DPC) ran after the entry check. Do
             * not submit on a pipe that is being closed. (Residual window
             * between this check and SubmitRequest: see work/30 REPORT.) */
            gdr_own_drop(ctx, &ctx->tx_busy);
            ctx->tx_busy = 0;
            return;
        }
        {
            long r = ctx->submit(ctx->device, u);
            if ((long)r < 0) {
                /* immediate rejection: NOT in flight, surface it, do not keep
                 * blindly resubmitting the same URB. */
                ctx->tx_busy = 0;
                ctx->tx_submit_fail++;
                gdr_own_drop(ctx, &ctx->tx_busy);
            }
        }
        return;
    }
}

/* Completion discriminator: identify which URB the callback actually delivered
 * and its raw fields, so a single run shows whether an OUT URB is routed to the
 * IN callback or a buffer is crossed. DPC-safe (u32 compares + field reads
 * only; the text is formatted at drain time). */
static void gdr_cb_tag(struct gdr_evt *e, const struct gdr_attach_ctx *ctx,
                       const gdr_urb_transfer *u) {
    u32 up = (u32)(uintptr_t)u;
    e->cb_urb = (up == GDR_P2U32(&ctx->in_urb))  ? 1
              : (up == GDR_P2U32(&ctx->tx_urb))  ? 2
              : (up == GDR_P2U32(&ctx->open_urb))? 3
              : (up == GDR_P2U32(&ctx->ctrl_urb))? 4 : 0;
    e->cb_fn  = u->Hdr.Function;
    e->cb_eh  = u->EndpointHandle;
    e->cb_buf = (u->TransferBuffer == GDR_P2U32(ctx->rx_buf))  ? 1
              : (u->TransferBuffer == GDR_P2U32(ctx->tx_buf))  ? 2
              : (u->TransferBuffer == GDR_P2U32(ctx->cfg_buf)) ? 3
              : (u->TransferBuffer == GDR_P2U32(ctx->cfg_stage)) ? 4 : 0;
    e->cb_flags = (u32)u->FlagB0 | ((u32)u->FlagB1 << 8) | ((u32)u->Direction << 16);
    e->cb_len14 = u->TransferLength;
    e->cb_len20 = u->ByteCount;
}

/* Push a standalone completion-discriminator event (its own bounded line, so the
 * full-payload RX/TXDONE lines stay within the 256-byte buffer). is_in: 1 = the
 * IN completion callback, 2 = the OUT completion callback. */
static void gdr_push_cb(struct gdr_attach_ctx *ctx, const gdr_urb_transfer *u,
                        u32 is_in) {
    if (!ctx->cb_log) return;            /* off by default; main.c enables it */
    struct gdr_evt e; memset(&e, 0, sizeof e);
    e.kind  = GDR_EVT_CB;
    e.a     = is_in;
    e.seq   = ++ctx->seq;
    gdr_cb_tag(&e, ctx, u);
    gdr_ring_push(ctx->ring, &e);
}

/* OUT completion (DISPATCH_LEVEL): ring-log TXDONE with the TRUE header status
 * (+0x04), actual completed OUT bytes (+0x14), the requested frame length and
 * the request id; then send the next queued frame. Distinct from the IN
 * completion: never touches rx_buf or the IN pipe. A failed completion is
 * still logged (status is real, not silent), so OUT loss is observable. */
static void GDR_STDCALL gdr_tx_complete(void *urb, void *ctxv) {
    struct gdr_attach_ctx *ctx = (struct gdr_attach_ctx*)ctxv;
    gdr_urb_transfer *u = (gdr_urb_transfer*)urb;
    if (!gdr_own_drop(ctx, &ctx->tx_busy)) { ctx->stale_completions++; return; }
    if (ctx->detached) { ctx->tx_busy = 0; gdr_retire_check(ctx); return; }
    long status = (long)(int)u->Hdr.Status;     /* +0x04 TRUE status (not +0x24) */
    u32  actual = u->TransferLength;            /* +0x14 completed OUT bytes     */
    struct gdr_evt e; memset(&e, 0, sizeof e);
    e.kind = GDR_EVT_TXDONE;
    e.seq  = ++ctx->seq;
    e.a    = (u32)status;                       /* true header status            */
    e.len  = actual;                            /* actual completed bytes        */
    e.b    = ctx->tx_cmd;
    e.d    = ctx->tx_req_len;                   /* requested frame length        */
    e.req_id = ctx->tx_req_id;
    e.tick   = ctx->tick;
    gdr_ring_push(ctx->ring, &e);
    gdr_push_cb(ctx, u, 2);                     /* discriminator (OUT callback)  */
    ctx->tx_events++;
    ctx->tx_busy = 0;
    gdr_tx_submit_next(ctx);
}

/* Interrupt-IN transfer size: the endpoint max-packet (64 for the GIP data
 * interface). Shared by the initial submit (S5) and every re-submit so the two
 * can never disagree. */
static u32 gdr_in_mps(const struct gdr_attach_ctx *ctx) {
    return ctx->mps_in ? (u32)ctx->mps_in : (u32)GDR_PKT_MAX;
}

/* Interrupt-IN completion (DISPATCH_LEVEL): log RX with the TRUE byte count
 * and re-arm.
 *
 * Corrected field use (Sol audit, from the linked XBE):
 *   - actual received bytes = TransferLength (+0x14), where the HCD
 *     ACCUMULATES completed bytes at completion. Snapshot it BEFORE resetting.
 *   - ByteCount (+0x20) is the ORIGINAL MAPPED length, NOT received bytes; it
 *     is never read here (previous code logged n=64 from it for a short frame).
 *   - Hdr.Status (+0x04) is the REAL status; TransferStatus (+0x24) is HCD
 *     linkage and is never read as status.
 *   - Re-arm resets TransferLength to the endpoint max-packet (mps) before
 *     submit, mirroring XID_NewInterruptData (xid-in.disasm @2b223..2b236).
 *
 * A failed completion (negative status) must NOT publish stale rx_buf, and a
 * zero-length completion stays 0 (never fabricate 64). If SubmitRequest
 * rejects immediately, in_flight is NOT set (a pending flag after a discarded
 * submit return is not evidence). */
static void GDR_STDCALL gdr_in_complete(void *urb, void *ctxv) {
    struct gdr_attach_ctx *ctx = (struct gdr_attach_ctx*)ctxv;
    gdr_urb_transfer *u = (gdr_urb_transfer*)urb;
    if (!gdr_own_drop(ctx, &ctx->in_flight)) { ctx->stale_completions++; return; }
    if (ctx->detached) { ctx->in_flight = 0; gdr_retire_check(ctx); return; }
    long status = (long)(int)u->Hdr.Status;   /* +0x04 TRUE status   */
    u32  actual = u->TransferLength;          /* +0x14 accumulated actual bytes (snapshot) */
    u32  req    = gdr_in_mps(ctx);            /* requested size (endpoint mps) */
    u32  req_id = ctx->in_req_id;             /* id of THIS completed request  */

    if (actual > GDR_PKT_MAX) actual = GDR_PKT_MAX;  /* reject impossible length */

    ctx->in_flight = 0;                       /* this request completed */

    if (status >= 0) {
        /* genuine successful completion: publish actual bytes; len==0 stays 0 */
        struct gdr_evt e; memset(&e, 0, sizeof e);
        e.kind = GDR_EVT_RX;
        e.a    = (u32)status;
        e.len  = actual;                      /* 0 stays 0 (no fabricated 64) */
        e.b    = req;                         /* requested size (for the log) */
        e.req_id = req_id;
        e.tick   = ctx->tick;
        e.seq  = ++ctx->seq;
        for (u32 i = 0; i < actual; i++) e.data[i] = ctx->rx_buf[i];
        gdr_ring_push(ctx->ring, &e);
        ctx->rx_events++;
    }
    /* discriminator fires for BOTH success and failure, so a misrouted OUT
     * (delivered to this IN callback) is still visible. Pushed BEFORE the
     * re-arm resets +0x14. */
    gdr_push_cb(ctx, u, 1);
    /* failed completions drop the RX entirely; the failure is still observable
     * via the LIVE in_flight/rearm counters and the incrementing rx_events
     * absence + req_id gap, and no stale rx_buf is published. */

    /* re-arm the SAME URB unless closed / failed / negative status / already
     * re-entrant. Snapshot of +14 happened above; now reset +14 BEFORE submit. */
    if (ctx->device && ctx->in_handle && !ctx->failed && status >= 0 &&
        ctx->in_rearm_guard == 0) {
        ctx->in_rearm_guard = 1;
        u->TransferLength = req;              /* reset +14 to mps BEFORE re-arm */
        ctx->req_id++;
        ctx->in_req_id = ctx->req_id;
        ctx->in_flight = 1;                   /* pending unless rejected/completed sync */
        gdr_own_take(ctx, &ctx->in_flight);
        {
            long r = ctx->submit(ctx->device, u);
            if ((long)r < 0) {
                ctx->in_flight = 0;           /* immediate rejection: NOT pending */
                ctx->in_submit_fail++;
                gdr_own_drop(ctx, &ctx->in_flight);
            }
        }
        ctx->in_rearm_guard = 0;
    }
}

/* Forward decls for the completion chain. */
static void GDR_STDCALL gdr_step_s0c(void *urb, void *ctxv);
static void GDR_STDCALL gdr_step_s1 (void *urb, void *ctxv);
static void GDR_STDCALL gdr_step_s2 (void *urb, void *ctxv);
static void GDR_STDCALL gdr_step_s3 (void *urb, void *ctxv);
static void GDR_STDCALL gdr_step_s4 (void *urb, void *ctxv);
static void GDR_STDCALL gdr_step_s5 (void *urb, void *ctxv);

/* ========================================================================== */
/* Slice2 lifecycle helpers (attach/detach generation, reset/no-stale,        */
/* AddComplete exactly-once, cancel->quiesce->RemoveComplete ordering).        */
/* ========================================================================== */

/* Retirement driver (any context; bounded, no wait). Runs after RemoveDevice
 * started the close chain whenever something retires: a close completes, or an
 * owned URB's completion arrives for the detached generation. It advances the
 * serialized close chain; gdr_close_next acks only at full quiescence. */
static void gdr_retire_check(struct gdr_attach_ctx *ctx) {
    if (!ctx->detached || !ctx->close_started || ctx->remove_complete_called) return;
    if (ctx->close_pending || ctx->failed == 3) return;   /* close in flight / quarantined */
    gdr_close_next(ctx);
}

/* An ACCEPTED open URB completed after RemoveDevice (F4). A successful open
 * returned an endpoint the class driver now owns: record it in its close slot so
 * the chain closes it before RemoveComplete. A failed open owns nothing. */
static void gdr_late_open(struct gdr_attach_ctx *ctx, const gdr_urb_open *u, u32 *slot) {
    if ((int)u->Hdr.Status >= 0 && u->EndpointHandle != 0) {
        if (*slot == 0) { *slot = u->EndpointHandle; ctx->late_open_captured++; }
        else ctx->failed = 3;   /* impossible by construction (one open per slot):
                                 * two handles for one slot -> quarantine, never ack */
    }
    gdr_retire_check(ctx);
}

/* Ack removal: call RemoveComplete exactly once, then go IDLE. Legal only once
 * the cancel walk has finished AND pending==0 (every accepted URB completed). */
static void gdr_remove_ack(struct gdr_attach_ctx *ctx) {
    struct gdr_evt e;
    if (ctx->remove_complete_called) return;
    ctx->remove_complete_called = 1;
    ctx->lifecycle = GDR_LIFE_IDLE;
    memset(&e, 0, sizeof e);
    e.kind = GDR_EVT_REMOVED; e.a = ctx->generation; e.b = ctx->close_count;
    e.seq = ++ctx->seq;
    gdr_ring_push(ctx->ring, &e);
    if (ctx->remove_complete) ctx->remove_complete(ctx->device);
}

static void GDR_STDCALL gdr_close_complete(void *urb, void *ctxv);

/* A rejected/failed close is not proof of retirement. Keep the detached
 * context quarantined, preserve its saved handles and report from the main
 * loop; never free/reuse the device while ownership remains unproved. */
static void gdr_close_fail(struct gdr_attach_ctx *ctx, u32 status) {
    struct gdr_evt e;
    ctx->close_submit_fail++;
    ctx->failed = 3;
    ctx->fail_step = 7;
    ctx->fail_status = status;
    memset(&e, 0, sizeof e);
    e.kind = GDR_EVT_STEPFAIL; e.a = 7; e.b = status; e.seq = ++ctx->seq;
    if (ctx->ring) gdr_ring_push(ctx->ring, &e);
}

/* Native endpoint-close chain. The stack's RemoveComplete frees ONLY the device
 * address — the CLASS driver owns closing every endpoint it opened (default
 * control pipe + interrupt IN/OUT). The stock _XID_RemoveDevice closes them with
 * an async close-URB chain before RemoveComplete (XID_CloseEndpointStateMachine
 * @0x2f133: Length 0x1c, fn 0xc3 DEFAULT then fn 0x43 per endpoint via handle
 * @+0x10, each chained through its own completion, RemoveComplete last).
 *
 * Order: default pipe (fn 0xc3) -> IN (fn 0x43) -> OUT (fn 0x43). A handle that
 * was never opened (0) is skipped. A rejected or failed close quarantines this
 * context until title exit; it must not be mistaken for successful retirement. */
static void gdr_close_next(struct gdr_attach_ctx *ctx) {
    u32 which, handle = 0; u8 fn = 0;
    if      (ctx->close_ctrl) { which = 1; handle = ctx->close_ctrl; fn = 0xc3; }
    else if (ctx->close_in)   { which = 2; handle = ctx->close_in;   fn = 0x43; }
    else if (ctx->close_out)  { which = 3; handle = ctx->close_out;  fn = 0x43; }
    else which = 0;
    if (which) {
        gdr_urb_close *u = &ctx->close_urb;
        u32 i; for (i = 0; i < sizeof *u; i++) ((u8*)u)[i] = 0;
        u->Hdr.Length   = 0x1c;
        u->Hdr.Function = fn;
        u->Hdr.CompleteProc    = GDR_P2U32(gdr_close_complete);
        u->Hdr.CompleteContext = GDR_P2U32(ctx);
        u->EndpointHandle = handle;
        ctx->close_stage = which - 1;   /* 0 ctrl / 1 in / 2 out in flight */
        ctx->close_which = which;
        ctx->close_pending++;
        ctx->close_count++;
        {
            long r = ctx->submit(ctx->device, u);
            if (r < 0) { ctx->close_pending--; ctx->close_which = 0; gdr_close_fail(ctx, (u32)r); }
        }
        return;                         /* wait for the completion to continue */
    }
    ctx->close_stage = 3;               /* every known owned endpoint closed */
    /* An accepted open still outstanding may yet return an endpoint we own;
     * any other still-owned URB means retirement is unproved. Wait (bounded:
     * its completion re-enters gdr_retire_check). Never forge pending=0. */
    if (gdr_own_any(ctx)) return;
    gdr_remove_ack(ctx);                /* native: RemoveComplete after the last close */
}

static void GDR_STDCALL gdr_close_complete(void *urb, void *ctxv) {
    struct gdr_attach_ctx *ctx = (struct gdr_attach_ctx*)ctxv;
    gdr_urb_close *u = (gdr_urb_close*)urb;
    u32 which;
    if (!ctx->close_pending) { ctx->stale_completions++; return; }   /* duplicate */
    ctx->close_pending--;
    which = ctx->close_which; ctx->close_which = 0;
    if ((int)u->Hdr.Status < 0) { gdr_close_fail(ctx, u->Hdr.Status); return; }  /* slot kept */
    /* the pipe is closed: its slot is retired (never closed twice), and the
     * native close retired every transfer still queued on it (OHCD: queued
     * ones inline at close submit, programmed ones before this completion).
     * A transfer flag still set here means its callback never came; any later
     * callback is then fenced as stale by the dropped ownership flag. */
    if (which == 1) {
        ctx->close_ctrl = 0;
        if (gdr_own_drop(ctx, &ctx->own_ctrl)) ctx->retired_by_close++;
    } else if (which == 2) {
        ctx->close_in = 0;
        if (gdr_own_drop(ctx, &ctx->in_flight)) { ctx->in_flight = 0; ctx->retired_by_close++; }
    } else if (which == 3) {
        ctx->close_out = 0;
        if (gdr_own_drop(ctx, &ctx->tx_busy)) { ctx->tx_busy = 0; ctx->retired_by_close++; }
    }
    gdr_retire_check(ctx);              /* close the next endpoint, or finish */
}

/* Signal IUsbDevice::AddComplete EXACTLY ONCE per attach generation.
 * status >= 0  => enumeration complete (device leaves the pending list; for a
 *                 type-2 device AddComplete(0) runs USBD_DeviceEnumNextPending).
 * status <  0  => aborted/disconnected (AddComplete(<0) runs the disconnect
 *                 path). Derived: AddComplete @0x2f9bb type 1/2 branch. */
static void gdr_signal_add_complete(struct gdr_attach_ctx *ctx, long status) {
    struct gdr_evt e;
    if (ctx->add_complete_called) return;         /* exactly once */
    ctx->add_complete_called = 1;
    ctx->add_status = status;
    ctx->lifecycle = (status >= 0) ? GDR_LIFE_LIVE : GDR_LIFE_FAILED;
    memset(&e, 0, sizeof e);
    e.kind = GDR_EVT_ADDCOMPLETE; e.a = (u32)status; e.seq = ++ctx->seq;
    if (ctx->ring) gdr_ring_push(ctx->ring, &e);
    if (ctx->add_complete) ctx->add_complete(ctx->device, status);
}

/* RemoveDevice (the description's __stdcall(1) remove callback, invoked by the
 * tree on disconnect). Invalidates state, stops new I/O, drops queued OUT frames,
 * and runs the native close chain (default -> IN -> OUT) BEFORE RemoveComplete.
 * No CancelRequest: its return value is unreliable (OHCD @0x3145a..0x31510 returns
 * +0x40020000 for BOTH already-cancelled and scheduled-cancel, 0 for the
 * inline-completed queued case, negative only for unsupported) — closing the
 * endpoint is the authoritative teardown that retires any in-flight transfer on
 * that pipe. Idempotent (double-remove / no-context / mismatched device no-ops). */
static void gdr_remove_device(struct gdr_attach_ctx *ctx, void *device) {
    struct gdr_evt e;

    if (!ctx) return;                                   /* no context */
    if (ctx->lifecycle == GDR_LIFE_IDLE) return;        /* never attached */
    if (ctx->device != device) return;                  /* not our device */
    if (ctx->detached) return;                          /* double remove */

    /* invalidate: stop new I/O + neutralize handle reuse immediately. SAVE the
     * owned handles first — the stack's RemoveComplete frees only the address
     * (VERIFIED @0x305ef); WE must close default + IN + OUT before ack. */
    ctx->detached   = 1;
    ctx->generation++;
    ctx->lifecycle  = GDR_LIFE_REMOVING;
    ctx->close_ctrl = ctx->control_handle;
    ctx->close_in   = ctx->in_handle;
    ctx->close_out  = ctx->out_handle;
    ctx->close_stage  = 0;
    ctx->close_pending = 0;
    ctx->close_which = 0;
    ctx->close_started = 0;
    ctx->close_submit_fail = 0;
    ctx->in_handle  = 0;
    ctx->out_handle = 0;
    ctx->control_handle = 0;
    /* in_flight / tx_busy are NOT cleared: they are the IN / OUT URB
     * ownership words and stay set until that URB's completion arrives or
     * its pipe's close completes (gdr_close_complete). */
    ctx->open_pending = 0;
    ctx->ctrl_pending = 0;
    ctx->tx_head = ctx->tx_tail = 0;   /* drop queued-but-unsent OUT frames */

    memset(&e, 0, sizeof e);
    e.kind = GDR_EVT_DETACH; e.a = ctx->generation; e.b = GDR_P2U32(device);
    e.seq = ++ctx->seq;
    gdr_ring_push(ctx->ring, &e);

    /* start the close chain (default -> IN -> OUT); its completion is the ONLY
     * gate on RemoveComplete, because closing a pipe retires any in-flight
     * transfer on it. */
    if (!ctx->close_started) { ctx->close_started = 1; gdr_retire_check(ctx); }
}

/* STEPFAIL: negative URB status on a mandatory step (structured event). */
static void gdr_step_fail(struct gdr_attach_ctx *ctx, u32 step, u32 status) {
    struct gdr_evt e; memset(&e, 0, sizeof e);
    ctx->failed       = 1;
    ctx->fail_step    = step;
    ctx->fail_status  = status;
    e.kind = GDR_EVT_STEPFAIL; e.a = step; e.b = status; e.seq = ++ctx->seq;
    gdr_ring_push(ctx->ring, &e);
    /* a mandatory step's failure is THIS attach's terminal result: signal
     * AddComplete(<0) exactly once so the stack aborts the pending enumeration
     * instead of re-enumerating the same device forever. */
    gdr_signal_add_complete(ctx, (long)(int)status);
}

/* Build + submit a control URB over the default control pipe. */
static void gdr_ctrl_get_desc(struct gdr_attach_ctx *ctx, u32 len, u32 buf,
                              void *complete) {
    gdr_urb_control *u = &ctx->ctrl_urb;
    u32 i; for (i = 0; i < sizeof *u; i++) ((u8*)u)[i] = 0;
    u->Hdr.Length   = 0x30;
    u->Hdr.Function = 0x40;
    u->Hdr.CompleteProc    = GDR_P2U32(complete);
    u->Hdr.CompleteContext = GDR_P2U32(ctx);
    u->EndpointHandle = ctx->control_handle;
    u->TransferLength = len;
    u->TransferBuffer = buf;
    u->FlagB0   = 2;    u->FlagB1 = 1;   u->Direction = 0;  /* XID ctrl values */
    u->SetupPacket[0] = 0x80;            /* IN | standard | device           */
    u->SetupPacket[1] = 0x06;            /* GET_DESCRIPTOR                   */
    u->SetupPacket[2] = 0x00; u->SetupPacket[3] = 0x02;   /* wValue type=config */
    u->SetupPacket[4] = 0x00; u->SetupPacket[5] = 0x00;   /* wIndex 0          */
    u->SetupPacket[6] = (u8)(len & 0xFF);
    u->SetupPacket[7] = (u8)((len >> 8) & 0xFF);
    {
        long r;
        gdr_own_take(ctx, &ctx->own_ctrl);
        r = ctx->submit(ctx->device, u);
        if (r < 0) { gdr_own_drop(ctx, &ctx->own_ctrl); ctx->ctrl_pending = 0; gdr_step_fail(ctx, ctx->state, (u32)r); }
        else ctx->ctrl_pending = 1;
    }
}

static void GDR_STDCALL gdr_step_s0c(void *urb, void *ctxv) {
    struct gdr_attach_ctx *ctx = (struct gdr_attach_ctx*)ctxv;
    gdr_urb_open *u = (gdr_urb_open*)urb;
    if (!gdr_own_drop(ctx, &ctx->own_open)) { ctx->stale_completions++; return; }
    if (ctx->detached) { gdr_late_open(ctx, u, &ctx->close_ctrl); return; }
    ctx->open_pending = 0;
    if ((long)(int)u->Hdr.Status < 0) { gdr_step_fail(ctx, 0, u->Hdr.Status); return; }
    ctx->control_handle = u->EndpointHandle;
    ctx->state = 1;
    gdr_evt_openctrl(ctx, ctx->control_handle);
    gdr_ctrl_get_desc(ctx, 9, GDR_P2U32(ctx->cfg_stage), (void*)gdr_step_s1);
}

static void GDR_STDCALL gdr_step_s1(void *urb, void *ctxv) {
    struct gdr_attach_ctx *ctx = (struct gdr_attach_ctx*)ctxv;
    gdr_urb_control *u = (gdr_urb_control*)urb;
    u32 wtotal;
    if (!gdr_own_drop(ctx, &ctx->own_ctrl)) { ctx->stale_completions++; return; }
    if (ctx->detached) { gdr_retire_check(ctx); return; }
    ctx->ctrl_pending = 0;
    if ((long)(int)u->Hdr.Status < 0) { gdr_step_fail(ctx, 1, u->Hdr.Status); return; }
    wtotal = (u32)ctx->cfg_stage[2] | ((u32)ctx->cfg_stage[3] << 8);
    if (wtotal < 9)  wtotal = 9;
    if (wtotal > 255) wtotal = 255;          /* clamp above our static buffer */
    ctx->cfg_len = (u16)wtotal;
    ctx->state = 2;
    gdr_ctrl_get_desc(ctx, wtotal, GDR_P2U32(ctx->cfg_buf), (void*)gdr_step_s2);
}

static void GDR_STDCALL gdr_step_s2(void *urb, void *ctxv) {
    struct gdr_attach_ctx *ctx = (struct gdr_attach_ctx*)ctxv;
    gdr_urb_control *u = (gdr_urb_control*)urb;
    struct gdr_cfg_result r;
    if (!gdr_own_drop(ctx, &ctx->own_ctrl)) { ctx->stale_completions++; return; }
    if (ctx->detached) { gdr_retire_check(ctx); return; }
    ctx->ctrl_pending = 0;
    if ((long)(int)u->Hdr.Status < 0) { gdr_step_fail(ctx, 2, u->Hdr.Status); return; }
    gdr_cfg_parse(ctx->cfg_buf, (int)ctx->cfg_len, &r);
    if (!r.found) {
        gdr_evt_cfgfail(ctx);   /* claimed-idle; no crash */
        /* no 0xFF data interface: this pad cannot be driven. Signal
         * AddComplete(<0) once so the stack aborts instead of re-enumerating.
         * (int) cast keeps the NTSTATUS sign-extended on both 32- and 64-bit. */
        gdr_signal_add_complete(ctx, (long)(int)0x80000400u);   /* USBD unsupported */
        return;
    }
    ctx->iface = r.iface; ctx->cfg_value = r.cfg_value;
    ctx->ep_in = r.ep_in; ctx->ep_out = r.ep_out;
    ctx->mps_in = r.mps_in; ctx->mps_out = r.mps_out;
    ctx->interval_in = r.interval_in; ctx->interval_out = r.interval_out;
    gdr_evt_cfg(ctx, &r);
    ctx->state = 3;
    /* SET_CONFIGURATION (bmRequestType 0x00, bRequest 0x09, wValue=cfgval) —
     * mirrors Stage5 @0x2aef0 setup `00 05 ... 09` (worker13 Q2). */
    {
        gdr_urb_control *c = &ctx->ctrl_urb;
        u32 i; for (i = 0; i < sizeof *c; i++) ((u8*)c)[i] = 0;
        c->Hdr.Length   = 0x30;
        c->Hdr.Function = 0x40;
        c->Hdr.CompleteProc    = GDR_P2U32(gdr_step_s3);
        c->Hdr.CompleteContext = GDR_P2U32(ctx);
        c->EndpointHandle = ctx->control_handle;
        c->TransferLength = 0;
        c->TransferBuffer = 0;
        c->FlagB0 = 2; c->FlagB1 = 1; c->Direction = 0;   /* XID ctrl values */
        c->SetupPacket[0] = 0x00;                        /* OUT | standard   */
        c->SetupPacket[1] = 0x09;                        /* SET_CONFIGURATION*/
        c->SetupPacket[2] = (u8)(r.cfg_value & 0xFF);
        c->SetupPacket[3] = (u8)((r.cfg_value >> 8) & 0xFF);
        c->SetupPacket[4] = 0x00; c->SetupPacket[5] = 0x00; c->SetupPacket[6] = 0x00; c->SetupPacket[7] = 0x00;
        {
            long r;
            gdr_own_take(ctx, &ctx->own_ctrl);
            r = ctx->submit(ctx->device, c);
            if (r < 0) { gdr_own_drop(ctx, &ctx->own_ctrl); ctx->ctrl_pending = 0; gdr_step_fail(ctx, 2, (u32)r); }
            else ctx->ctrl_pending = 1;
        }
    }
}

static void GDR_STDCALL gdr_step_s3(void *urb, void *ctxv) {
    struct gdr_attach_ctx *ctx = (struct gdr_attach_ctx*)ctxv;
    gdr_urb_control *c = (gdr_urb_control*)urb;   /* SET_CONFIGURATION URB */
    if (!gdr_own_drop(ctx, &ctx->own_ctrl)) { ctx->stale_completions++; return; }
    if (ctx->detached) { gdr_retire_check(ctx); return; }
    ctx->ctrl_pending = 0;
    if ((long)(int)c->Hdr.Status < 0) { gdr_step_fail(ctx, 3, c->Hdr.Status); return; }
    ctx->state = 4;
    /* OPEN_ENDPOINT IN (fn 0x02): caller sets +0x15 addr, +0x16 type, +0x17
     * interval, +0x1C mps; SubmitRequest fills +0x14 addr, +0x18 buf, +0x1E
     * dir (worker09 §2). */
    {
        gdr_urb_open *o = &ctx->open_urb;
        u32 i; for (i = 0; i < sizeof *o; i++) ((u8*)o)[i] = 0;
        o->Hdr.Length   = 0x20;
        o->Hdr.Function = 0x02;
        o->Hdr.CompleteProc    = GDR_P2U32(gdr_step_s4);
        o->Hdr.CompleteContext = GDR_P2U32(ctx);
        o->EndpointAddress = ctx->ep_in;
        o->TransferType    = 3;              /* interrupt */
        o->Interval        = ctx->interval_in;
        o->MaxPacketSize   = ctx->mps_in;
        {
            long r;
            gdr_own_take(ctx, &ctx->own_open);
            r = ctx->submit(ctx->device, o);
            if (r < 0) { gdr_own_drop(ctx, &ctx->own_open); ctx->open_pending = 0; gdr_step_fail(ctx, 3, (u32)r); }
            else ctx->open_pending = 1;
        }
    }
}

static void GDR_STDCALL gdr_step_s4(void *urb, void *ctxv) {
    struct gdr_attach_ctx *ctx = (struct gdr_attach_ctx*)ctxv;
    gdr_urb_open *u = (gdr_urb_open*)urb;
    if (!gdr_own_drop(ctx, &ctx->own_open)) { ctx->stale_completions++; return; }
    if (ctx->detached) { gdr_late_open(ctx, u, &ctx->close_in); return; }
    ctx->open_pending = 0;
    if ((long)(int)u->Hdr.Status < 0) { gdr_step_fail(ctx, 4, u->Hdr.Status); return; }
    ctx->in_handle = u->EndpointHandle;
    ctx->state = 5;
    {
        gdr_urb_open *o = &ctx->open_urb;
        u32 i; for (i = 0; i < sizeof *o; i++) ((u8*)o)[i] = 0;
        o->Hdr.Length   = 0x20;
        o->Hdr.Function = 0x02;
        o->Hdr.CompleteProc    = GDR_P2U32(gdr_step_s5);
        o->Hdr.CompleteContext = GDR_P2U32(ctx);
        o->EndpointAddress = ctx->ep_out;
        o->TransferType    = 3;
        o->Interval        = ctx->interval_out;
        o->MaxPacketSize   = ctx->mps_out;
        {
            long r;
            gdr_own_take(ctx, &ctx->own_open);
            r = ctx->submit(ctx->device, o);
            if (r < 0) { gdr_own_drop(ctx, &ctx->own_open); ctx->open_pending = 0; gdr_step_fail(ctx, 4, (u32)r); }
            else ctx->open_pending = 1;
        }
    }
}

static void GDR_STDCALL gdr_step_s5(void *urb, void *ctxv) {
    struct gdr_attach_ctx *ctx = (struct gdr_attach_ctx*)ctxv;
    gdr_urb_open *u = (gdr_urb_open*)urb;
    if (!gdr_own_drop(ctx, &ctx->own_open)) { ctx->stale_completions++; return; }
    if (ctx->detached) { gdr_late_open(ctx, u, &ctx->close_out); return; }
    ctx->open_pending = 0;
    if ((long)(int)u->Hdr.Status < 0) { gdr_step_fail(ctx, 5, u->Hdr.Status); return; }
    ctx->out_handle = u->EndpointHandle;
    if (!ctx->in_handle || !ctx->out_handle) { gdr_step_fail(ctx, 5, 0xc0000002u); return; }
    ctx->state = 6;                          /* live */
    gdr_evt_open(ctx);
    /* endpoints are open and the persistent IN URB is about to be armed:
     * enumeration is complete. Signal AddComplete(0) exactly once so the
     * type-2 device leaves the pending list (USBD_DeviceEnumNextPending). */
    gdr_signal_add_complete(ctx, 0);
    /* the AddComplete seam may RE-ENTER removal (a synchronous disconnect) and
     * detach/zero the handles. Re-check liveness/identity before arming the IN
     * URB so a detached-generartion never submits. */
    if (ctx->detached || !ctx->in_handle || !ctx->out_handle) return;

    /* persistent interrupt IN URB (fn 0x41) */
    {
        gdr_urb_transfer *t = &ctx->in_urb;
        u32 i; for (i = 0; i < sizeof *t; i++) ((u8*)t)[i] = 0;
        t->Hdr.Length   = 0x28;
        t->Hdr.Function = 0x41;
        t->Hdr.CompleteProc    = GDR_P2U32(ctx->in_complete);
        t->Hdr.CompleteContext = GDR_P2U32(ctx);
        t->EndpointHandle = ctx->in_handle;
        t->TransferLength = gdr_in_mps(ctx);
        t->TransferBuffer = GDR_P2U32(ctx->rx_buf);
        t->FlagB0 = 2; t->FlagB1 = 1; t->Direction = 0;  /* XID IN (VERIFIED) */
        ctx->req_id++;
        ctx->in_req_id = ctx->req_id;
        ctx->in_flight = 1;                   /* pending unless rejected */
        gdr_own_take(ctx, &ctx->in_flight);
        {
            long r = ctx->submit(ctx->device, t);
            if ((long)r < 0) {
                ctx->in_flight = 0;           /* immediate rejection: NOT pending */
                ctx->in_submit_fail++;
                gdr_own_drop(ctx, &ctx->in_flight);
            }
        }
    }
    /* GIP init is NOT sent from this DPC. The no-announce wired path is started
     * by gdr_gip_qualify_wired (main loop, once state==6) with minimal power-on
     * then S-init serialized on completion; the announce->identify path starts
     * from gdr_rx_identify. IDENTIFY is never sent blind before power. */
}

/* S0 — Attach(device). Runs in XInitDevices/Process (PASSIVE) context.
 * Mirrors Stage4 @0x2b00b: open the DEFAULT CONTROL endpoint (fn 0x82) first,
 * then the GET_DESCRIPTOR(config) chain. Everything else is completion-driven.
 *
 * FAIL-CLOSED: if a previous generation is still REMOVING (or any accepted URB
 * is still outstanding), refuse to claim the device — return non-zero and leave
 * the context untouched. One-controller scope does NOT justify clobbering a live
 * context while old URBs are unquiesced; the caller signals AddComplete(<0) on
 * the refused device. */
static int gdr_attach_begin(struct gdr_attach_ctx *ctx, void *device,
                            gdr_submit_fn submit, struct gdr_ring *ring) {
    u32 i;
    if (!ctx) return 1;
    if (ctx->lifecycle == GDR_LIFE_REMOVING || ctx->pending != 0 || gdr_own_any(ctx)) return 1;

    ctx->device = device;
    ctx->submit = submit;
    ctx->ring   = ring;
    ctx->seq    = 0;
    ctx->rx_events = 0; ctx->tx_events = 0; ctx->in_flight = 0;
    ctx->state  = 0;
    ctx->failed = 0;
    ctx->fail_step = 0; ctx->fail_status = 0;
    ctx->req_id = 0; ctx->in_req_id = 0; ctx->tx_req_id = 0;
    ctx->in_submit_fail = 0; ctx->tx_submit_fail = 0;
    ctx->in_rearm_guard = 0; ctx->tick = 0; ctx->tx_req_len = 0;
    ctx->control_handle = 0; ctx->in_handle = 0; ctx->out_handle = 0;
    ctx->ep_in = ctx->ep_out = 0;
    ctx->mps_in = ctx->mps_out = 0;
    ctx->interval_in = ctx->interval_out = 0;
    ctx->iface = 0; ctx->cfg_value = 0; ctx->cfg_len = 0;
    ctx->tx_busy = 0; ctx->tx_head = 0; ctx->tx_tail = 0; ctx->tx_cmd = 0;
    /* ---- slice2 lifecycle: a fresh generation; reset the detach/ack guards.
     * The ctx is TITLE-LIFETIME (never freed); re-use here is safe only because
     * the previous generation fully quiesced (RemoveComplete ack => pending==0)
     * before the stack can re-Attach. */
    ctx->detached     = 0;
    ctx->lifecycle    = GDR_LIFE_ATTACHING;
    ctx->add_complete_called = 0;
    ctx->add_status   = 0;
    ctx->remove_complete_called = 0;
    ctx->pending      = 0;
    ctx->cancel_count = 0;
    ctx->open_pending = 0;
    ctx->ctrl_pending = 0;
    ctx->removing_in_walk = 0;
    ctx->close_stage  = 0;
    ctx->close_pending = 0;
    ctx->close_which = 0;
    ctx->close_started = 0;
    ctx->close_submit_fail = 0;
    for (i = 0; i < GDR_TX_SLOTS; i++) { ctx->tx_len[i] = 0; for (u32 j = 0; j < 64; j++) ctx->tx_q[i][j] = 0; }
    for (u32 j = 0; j < 64; j++) ctx->tx_buf[j] = 0;
    for (u32 j = 0; j < 64; j++) ctx->rx_buf[j] = 0;
    /* OPEN DEFAULT CONTROL ENDPOINT (fn 0x82 -> SubmitRequest 0x415383 rewrites
     * to 0x02 and fills all fields from the default control EP; no caller
     * params, worker09 §2). */
    for (i = 0; i < sizeof ctx->open_urb; i++) ((u8*)&ctx->open_urb)[i] = 0;
    ctx->open_urb.Hdr.Length   = 0x20;
    ctx->open_urb.Hdr.Function = 0x82;
    ctx->open_urb.Hdr.CompleteProc    = GDR_P2U32(gdr_step_s0c);
    ctx->open_urb.Hdr.CompleteContext = GDR_P2U32(ctx);
    {
        long r;
        gdr_own_take(ctx, &ctx->own_open);
        r = ctx->submit(device, &ctx->open_urb);
        if (r < 0) {
            /* immediate rejection of the control-endpoint open: this attach
             * failed before any chain ran. Signal AddComplete(r) exactly once. */
            gdr_own_drop(ctx, &ctx->own_open);
            ctx->open_pending = 0;
            gdr_step_fail(ctx, 0, (u32)r);
        } else ctx->open_pending = 1;
    }
    return 0;
}

/* Full decoder reset on generation transition (detach): reuse the SAME
 * gdr_gip_init reset semantics so the decoded snapshot, identity, TX queue,
 * sequence, and counters all clear together — a replug streams fresh state and
 * any pre-unplug queued-but-unsent OUT frames are dropped. Called by the main
 * loop on a DETACH event (NOT from DPC context); it sends no protocol frames. */
static void gdr_gip_neutralize(struct gdr_gip *m) {
    gdr_gip_init(m, 0);
}

#endif /* GIPDRIVE_H */
