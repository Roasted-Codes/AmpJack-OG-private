/*
 * diag_util.h — pure, dependency-free core of the AmpJack-OG USB diagnostic.
 *
 * HEADER-ONLY on purpose: the SAME code compiles into (a) the Xbox title
 * (main.c) and (b) the host test harness (ogxbox/work/09-diagnostic/
 * test_diagnostic.c), so the logic the Xbox runs is literally the logic the
 * host tests exercise.
 *
 * Four parts:
 *   1. TRACE RING   — bounded, pre-allocated ring. The LoadClassDriver capture
 *                     handler may ONLY push (no malloc, no file I/O, O(1));
 *                     a normal-context drain formats + writes the log.
 *                     Overflow is counted, never crashes.
 *   2. LOG FORMAT   — one line per event, machine-parseable.
 *   3. SIGNATURE    — byte-signature match with an explicit negative control,
 *                     used to pin the USBD functions in OUR built XBE.
 *   4. (pinned_load.h) — the E9 detour pin, generated separately from the
 *                     built XBE's actual bytes by ogxbox/work/09-diagnostic/
 *                     gen_pinned_load.py; main.c compares the target bytes to
 *                     it at runtime before writing (fail-closed).
 *
 * No proprietary XDK code is reproduced here: the USB descriptor structs are
 * the public USB 1.1 spec layout, and the "signatures" are instruction-byte
 * patterns re-derived from the built XBE (see ogxbox/research/binding).
 */
#ifndef DIAG_UTIL_H
#define DIAG_UTIL_H

#include <stddef.h>   /* size_t — stddef.h is present on BOTH host and Xbox XDK */
#if defined(_MSC_VER) && _MSC_VER < 1600
/* The Xbox XDK (VC7.1) ships no <stdint.h>; provide the exact-width types. */
typedef unsigned char  uint8_t;
typedef unsigned int   uint32_t;
typedef signed char    int8_t;
typedef int            int32_t;
#else
#include <stdint.h>
#endif

/*
 * DIAG_LIT_LEN(s) — byte length of a string literal (excludes the NUL).
 * Every log_write(s, n) caller with a string LITERAL must pass
 * DIAG_LIT_LEN(lit), never a hand-counted number: a wrong hand-count silently
 * truncates or pads the line (the exit line was counted 18 when it is 21).
 * main.c wraps this as LOG_LIT(s) = log_write((s), DIAG_LIT_LEN(s)).
 */
#define DIAG_LIT_LEN(s) (sizeof(s) - 1u)


/* ------------------------------------------------------------------ */
/* 1. TRACE RING                                                       */
/* ------------------------------------------------------------------ */

#define DIAG_RING_CAP      256u   /* bounded; pre-allocated, never grows      */

/* Event kinds. The LoadClassDriver capture only ever emits DIAG_EVT_MATCH. */
enum {
    DIAG_EVT_MATCH      = 1,  /* USBD_LoadClassDriver capture (rich payload)   */
    DIAG_EVT_OVERFLOW   = 2,  /* ring wrapped; synthesized at drain time      */
    DIAG_EVT_STOCKPAD   = 3,  /* XGetDeviceChanges reported a port bit         */
    DIAG_EVT_SYNTH      = 9   /* synthetic test event (clearly labelled)       */
};

/*
 * diag_event — one slot in the ring.  `a`/`b` keep their meaning across the
 * simple events; the MATCH-specific fields are only meaningful when
 * kind == DIAG_EVT_MATCH.
 */
typedef struct diag_event {
    uint32_t kind;     /* DIAG_EVT_*                                           */
    uint32_t device;   /* MATCH: IUsbDevice* (opaque; only read by the desc mgr)*/
    uint32_t a;        /* MATCH: classId (PNP_CLASS_ID, 16-bit); OVERFLOW: dropped; SYNTH: label */
    uint32_t b;        /* STOCKPAD: insertion mask (bit N = XID port N)         */
    uint32_t speed;    /* MATCH: GetLowSpeed() (0 = full, 1 = low)             */
    uint32_t iface;    /* MATCH: GetInterfaceNumber()                          */
    uint32_t dclass;   /* MATCH: bDeviceClass                                  */
    uint32_t dsub;     /* MATCH: bDeviceSubClass                               */
    uint32_t dproto;   /* MATCH: bDeviceProtocol                               */
    uint32_t ifclass;  /* MATCH: bInterfaceClass                               */
    uint32_t ifsub;    /* MATCH: bInterfaceSubClass                            */
    uint32_t ifproto;  /* MATCH: bInterfaceProtocol                            */
    uint32_t nep;      /* MATCH: bNumEndpoints                                 */
    uint32_t niface;   /* MATCH: bNumInterfaces                                */
    uint32_t vendor;   /* MATCH: idVendor (0 if not exposed)                   */
    uint32_t product;  /* MATCH: idProduct (0 if not exposed)                  */
    uint32_t find;     /* MATCH: FindClassDriver() result (0 = no stock driver)*/
    uint32_t seq;      /* monotonic sequence number (helps the parser)         */
} diag_event;

typedef struct diag_ring {
    diag_event slots[DIAG_RING_CAP];
    volatile uint32_t count;    /* # valid slots 0..count-1 (append-only)      */
    volatile uint32_t overflow; /* # pushes dropped because ring was full       */
} diag_ring;

static void diag_ring_reset(diag_ring *r) {
    r->count = 0;
    r->overflow = 0;
}

/*
 * Single-writer, bounded, no allocation, no calls, O(1): the only operation
 * the capture handler may perform on the ring.  Returns 1 if recorded, 0 if
 * dropped (ring full — counted in r->overflow).
 */
static int diag_ring_push(diag_ring *r, const diag_event *e) {
    uint32_t n = r->count;
    if (n >= DIAG_RING_CAP) {
        r->overflow++;
        return 0;
    }
    r->slots[n] = *e;
    r->count = n + 1;
    return 1;
}

/* Normal-context drain: snapshot, then reset for the next window. */
static void diag_ring_drain(diag_ring *r,
                            uint32_t *count_out, uint32_t *overflow_out) {
    *count_out = r->count;
    *overflow_out = r->overflow;
    diag_ring_reset(r);
}

/* ------------------------------------------------------------------ */
/* 2. LOG FORMAT                                                       */
/* ------------------------------------------------------------------ */

/*
 * One text line per event, '\n'-terminated.  Deterministic and parseable:
 *
 *   MATCH dev=0x00414f22 class=0x5882 speed=0x00 iface=0x00
 *         dclass=0x00 dsub=0x00 dproto=0x00 ifclass=0x58 ifsub=0x42 ifproto=0x00
 *         nep=0x02 niface=0x01 vendor=0x045e product=0x028e find=0x00414f22
 *         seq=0x00000001                         (single line, spaces only)
 *   OVERFLOW dropped=0x00000003 seq=0x00000002
 *   STOCKPAD insertions=0x00000009 seq=0x00000003
 *   SYNTH label=0x00abcdcd seq=0x00000004
 *
 * Field widths are fixed: pointers/32-bit = 8 hex, 16-bit = 4 hex, byte = 2
 * hex.  Returns bytes written (excluding NUL).  Never reads the filesystem and
 * never dereferences 'device'.
 */
static size_t diag_format_event(char *buf, size_t cap, const diag_event *e) {
    static const char hexd[] = "0123456789abcdef";

    #define EMIT(...) do { \
        const char *_s = __VA_ARGS__; \
        while (*_s && (size_t)(p - buf) < cap - 1) *p++ = *_s++; \
    } while (0)

    #define EMIT_HEX(v, bits) do { \
        int _i; \
        for (_i = (bits) - 4; _i >= 0; _i -= 4) { \
            if ((size_t)(p - buf) < cap - 1) \
                *p++ = hexd[((uint32_t)(v) >> _i) & 0xF]; \
        } \
    } while (0)

    #define EMIT_HEX32(v) EMIT_HEX(v, 32)
    #define EMIT_HEX16(v) EMIT_HEX(v, 16)
    #define EMIT_HEX8(v)  EMIT_HEX(v, 8)

    char *p = buf;
    switch (e->kind) {
    case DIAG_EVT_MATCH:
        EMIT("MATCH dev=0x");    EMIT_HEX32(e->device);
        EMIT(" class=0x");       EMIT_HEX16(e->a);
        EMIT(" speed=0x");       EMIT_HEX8(e->speed);
        EMIT(" iface=0x");       EMIT_HEX8(e->iface);
        EMIT(" dclass=0x");      EMIT_HEX8(e->dclass);
        EMIT(" dsub=0x");        EMIT_HEX8(e->dsub);
        EMIT(" dproto=0x");      EMIT_HEX8(e->dproto);
        EMIT(" ifclass=0x");     EMIT_HEX8(e->ifclass);
        EMIT(" ifsub=0x");       EMIT_HEX8(e->ifsub);
        EMIT(" ifproto=0x");     EMIT_HEX8(e->ifproto);
        EMIT(" nep=0x");         EMIT_HEX8(e->nep);
        EMIT(" niface=0x");      EMIT_HEX8(e->niface);
        EMIT(" vendor=0x");      EMIT_HEX16(e->vendor);
        EMIT(" product=0x");     EMIT_HEX16(e->product);
        EMIT(" find=0x");        EMIT_HEX32(e->find);
        break;
    case DIAG_EVT_OVERFLOW:
        EMIT("OVERFLOW dropped=0x"); EMIT_HEX32(e->a);
        break;
    case DIAG_EVT_STOCKPAD:
        EMIT("STOCKPAD insertions=0x"); EMIT_HEX32(e->b);
        break;
    case DIAG_EVT_SYNTH:
        EMIT("SYNTH label=0x"); EMIT_HEX32(e->a);
        break;
    default:
        EMIT("UNKNOWN kind="); EMIT_HEX32(e->kind);
        break;
    }
    EMIT(" seq=0x"); EMIT_HEX32(e->seq);
    EMIT("\n");
    *p = '\0';
    return (size_t)(p - buf);

    #undef EMIT
    #undef EMIT_HEX
    #undef EMIT_HEX32
    #undef EMIT_HEX16
    #undef EMIT_HEX8
}

/* ------------------------------------------------------------------ */
/* 3. SIGNATURE MATCH                                                  */
/* ------------------------------------------------------------------ */

/*
 * Find the first occurrence of pattern (pattern_len bytes, 0xFF == wildcard)
 * in [mem, mem+mem_len). Returns byte offset, or -1 if absent.
 */
static long diag_sig_find(const uint8_t *mem, size_t mem_len,
                          const uint8_t *pattern, size_t pattern_len) {
    size_t i, j;
    if (pattern_len == 0 || mem_len < pattern_len)
        return -1;
    for (i = 0; i + pattern_len <= mem_len; i++) {
        for (j = 0; j < pattern_len; j++) {
            if (pattern[j] != 0xFF && mem[i + j] != pattern[j])
                break;
        }
        if (j == pattern_len)
            return (long)i;
    }
    return -1;
}

/* FNV-1a hash over a byte range: negative-control check. */
static uint32_t diag_sig_hash(const uint8_t *mem, size_t len) {
    uint32_t h = 2166136261u;
    size_t i;
    for (i = 0; i < len; i++) {
        h ^= mem[i];
        h *= 16777619u;
    }
    return h;
}

/* ------------------------------------------------------------------ */
/* 4. DETOUR-PIN ANALYZER (fail-closed, shared with the host tests)     */
/* ------------------------------------------------------------------ */

/*
 * Conservative x86 opcode-length walk over the first instructions of a function.
 * Walks whole instructions from offset 0 until >= 5 bytes are covered (the E9
 * detour replaces 5 bytes; the "displaced span" is every instruction that
 * overlaps those 5 bytes and must be re-executed by the trampoline).
 *
 * On success (0): *span_len = displaced span length (>= 5), *rel_ofs = offset
 * of the first PC-relative instruction in the span (-1 if none), *rel_target =
 * that instruction's destination relative to the span start.
 *
 * Returns -1 on any opcode it does not recognise => the caller must fail closed
 * and refuse to install a detour.  main.c cross-checks the result against the
 * gen-time PINNED_LOAD_* constants so the two can never silently disagree.
 */
static int diag_span_analyze(const uint8_t *code, size_t maxlen,
                             size_t *span_len, long *rel_ofs, long *rel_target) {
    size_t off = 0;
    long found_ofs = -1, target = 0;
    int result = 0;

    *span_len = 0;
    *rel_ofs = -1;
    *rel_target = 0;

    while (off < 5) {
        size_t l = 0;
        int pc = 0;
        long tgt = 0;
        uint8_t b = code[off];
        uint8_t modrm, mod, rm;
        size_t disp, sib, imm;

        if (b == 0x90 || b == 0xCC)                       l = 1;
        else if (b >= 0x50 && b <= 0x5F)                  l = 1;  /* push/pop reg */
        else if (b >= 0x40 && b <= 0x4F)                  l = 1;  /* inc/dec reg  */
        else if (b >= 0xB8 && b <= 0xBF)                  l = 5;  /* mov reg, imm32 */
        else if (b == 0x68)                               l = 5;  /* push imm32    */
        else if (b == 0x6A)                               l = 2;  /* push imm8     */
        else if (b == 0xC3)                               l = 1;  /* ret           */
        else if (b == 0xEB) {                             /* jmp rel8       */
            l = 2; pc = 1; tgt = (long)off + 2 + (int8_t)code[off + 1];
        }
        else if (b >= 0x70 && b <= 0x7F) {                /* jcc rel8       */
            l = 2; pc = 1; tgt = (long)off + 2 + (int8_t)code[off + 1];
        }
        else if (b == 0xE8 || b == 0xE9) {                /* call/jmp rel32 */
            uint32_t d = (uint32_t)code[off + 1] | ((uint32_t)code[off + 2] << 8) |
                         ((uint32_t)code[off + 3] << 16) | ((uint32_t)code[off + 4] << 24);
            l = 5; pc = 1; tgt = (long)off + 5 + (int32_t)d;
        }
        else {
            /* mod-reg-rm group: mov/cmp/test/lea/call [rm] etc. (length only) */
            modrm = code[off + 1];
            mod = modrm >> 6; rm = modrm & 7;
            disp = 0; sib = 0; imm = 0;
            if (mod == 0 && rm == 5)            disp = 4;
            else if (mod == 1)                  disp = 1;
            else if (mod == 2)                  disp = 4;
            if (mod != 3 && rm == 4) {          /* SIB present */
                sib = 1;
                if (mod == 0 && (code[off + 2] & 7) == 5) disp = 4;  /* no base => disp32 */
            }
            if      (b == 0x83) imm = 1;        /* group1 imm8 (cmp/etc.) */
            else if (b == 0x81) imm = 4;        /* group1 imm32           */
            else if (b == 0xC7) imm = 4;        /* mov r/m32, imm32       */
            switch (b) {                        /* allow only known modrm ops */
                case 0x01: case 0x03: case 0x09: case 0x0B: case 0x11:
                case 0x19: case 0x21: case 0x23: case 0x29: case 0x2B:
                case 0x31: case 0x33: case 0x39: case 0x3A: case 0x3B:
                case 0x80: case 0x81: case 0x83: case 0x85: case 0x89:
                case 0x8B: case 0x8D: case 0xC7: case 0xFF:
                    l = 2 + disp + sib + imm;
                    break;
                default:
                    result = -1;                 /* unrecognised => fail closed */
                    break;
            }
            if (result != 0) break;
        }

        if (off + l > maxlen) { result = -1; break; }
        if (pc) { found_ofs = (long)off; target = tgt; }
        off += l;
        if (off > 32) { result = -1; break; }    /* unreasonably long prologue */
    }

    if (result == 0) {
        *span_len = off;
        *rel_ofs = found_ofs;
        *rel_target = target;
    }
    return result;
}

/*
 * Fail-closed prologue pin: 1 iff mem[i] == pinned[i] for the whole span and
 * the span is long enough to hold an E9 (>= 5 bytes).  main.c calls this on
 * the live target bytes before writing the detour; the pinned[] bytes come from
 * PINNED_LOAD_SPAN (derived from the built XBE by gen_pinned_load.py).
 */
static int diag_pin_span(const uint8_t *mem, const uint8_t *pinned, size_t len) {
    size_t i;
    if (len < 5)
        return 0;
    for (i = 0; i < len; i++)
        if (mem[i] != pinned[i])
            return 0;
    return 1;
}

#endif /* DIAG_UTIL_H */
