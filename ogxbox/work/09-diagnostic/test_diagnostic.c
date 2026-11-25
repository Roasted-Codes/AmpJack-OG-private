/*
 * test_diagnostic.c — host test harness for the AmpJack-OG diagnostic logic.
 *
 * Compiles the SAME diag_util.h the Xbox title compiles, and exercises:
 *   1. trace-ring bound + overflow + drain,
 *   2. log-format (byte-exact) + a line parser (MATCH incl. the rich payload),
 *   3. byte-signature match + unknown-hash negative control,
 *   4. the detour-pin analyzer (span length + rel32 detection) on a synthetic
 *      span WITH a rel32 `call` (the real pinned prologue: 56 8b f1 e8 rel32)
 *      and a span WITHOUT one (56 8b f1 83 7e 14 20), and
 *   5. the fail-closed prologue pin (diag_pin_span): match arms, any
 *      mismatch or a sub-5-byte span refuses.
 *   6. literal-length discipline: DIAG_LIT_LEN() matches strlen for the
 *      literals main.c passes to log_write (the exit literal was hand-counted
 *      18 when it is really 21 — that bug is what this regression-locks).
 *
 * Build & run (bundled as ogxbox/work/09-diagnostic/run_tests.sh):
 *   cc -std=c99 -Wall -Wextra -I ../../diagnostic/src test_diagnostic.c -o test_diagnostic
 *   ./test_diagnostic
 */
#include <stdio.h>
#include <string.h>
#include "diag_util.h"

static int g_fail = 0;
#define CHECK(cond, msg) do { \
    if (cond) printf("  ok  %s\n", msg); \
    else { printf("FAIL  %s\n", msg); g_fail++; } \
} while (0)

/* ---- 3. signature match helpers ------------------------------------------ */
static const uint8_t SIG_FCD[] = {0x3a,0x70,0x01,0x75,0x04,0x3a,0x10};
static const uint8_t SIG_LP[]  = {0x56,0x8b,0xf1};

static void test_signature(void) {
    uint8_t buf[32] = {0};
    memcpy(buf + 5, SIG_FCD, sizeof(SIG_FCD));
    CHECK(diag_sig_find(buf, sizeof buf, SIG_FCD, sizeof SIG_FCD) == 5,
          "sig_find finds signed bytes at expected offset");

    uint8_t a[16] = {0};
    memcpy(a, SIG_LP, sizeof SIG_LP);
    CHECK(diag_sig_find(a, sizeof a, SIG_LP, sizeof SIG_LP) == 0,
          "sig_find finds prefix at offset 0");

    uint8_t b[16] = {0x90,0x90,0x90,0x90,0xcc,0x90,0x90,0x90,
                     0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90};
    CHECK(diag_sig_find(b, sizeof b, SIG_FCD, sizeof SIG_FCD) == -1,
          "sig_find returns -1 when signature absent");

    uint8_t target[8] = {0x56,0x8b,0xf1,0xe8,0x00,0x00,0x00,0x00};
    uint8_t other[8]  = {0xde,0xad,0xbe,0xef,0x00,0x00,0x00,0x00};
    CHECK(diag_sig_hash(target, sizeof target) != diag_sig_hash(other, sizeof other),
          "negative control: unknown-hash differs from expected");
    CHECK(diag_sig_hash(target, sizeof target) == diag_sig_hash(target, sizeof target),
          "hash is deterministic (positive sanity)");
}

/* ---- 1. trace ring -------------------------------------------------------- */
static void test_ring(void) {
    diag_ring r; diag_ring_reset(&r);

    diag_event e; memset(&e, 0, sizeof e);
    e.kind = DIAG_EVT_MATCH; e.device = 0x414f22u; e.a = 0x5882u; e.seq = 1;

    int all_in = 1;
    for (uint32_t i = 0; i < DIAG_RING_CAP; i++) { e.seq = i + 1; if (!diag_ring_push(&r, &e)) all_in = 0; }
    CHECK(all_in && r.count == DIAG_RING_CAP, "ring accepts exactly DIAG_RING_CAP events");

    e.seq = DIAG_RING_CAP + 1;
    CHECK(diag_ring_push(&r, &e) == 0, "push beyond capacity returns 0 (dropped)");
    CHECK(r.overflow == 1, "overflow counter incremented to 1");
    CHECK(r.count == DIAG_RING_CAP, "ring count stays bounded at capacity");

    uint32_t c = 0, o = 0; diag_ring_drain(&r, &c, &o);
    CHECK(c == DIAG_RING_CAP && o == 1, "drain reports count + overflow");
    CHECK(r.count == 0 && r.overflow == 0, "drain resets the ring");
}

/* ---- 2. log format + parser ---------------------------------------------- */
/* The exact MATCH line (single line, spaces only) produced by diag_format_event.
 * NOTE: the `port=` field was REMOVED — GetPort reads device->port before
 * LoadClassDriver's SetExternalPort runs, so it was garbage (0xcccccccc); the
 * physical XID port now comes from the STOCKPAD insertion-mask bit instead. */
static void test_log(void) {
    char line[256];
    diag_event e; memset(&e, 0, sizeof e);
    e.kind = DIAG_EVT_MATCH;
    e.device = 0x414f22u; e.a = 0x5882u; e.seq = 1;
    e.speed = 0; e.iface = 0;
    e.ifclass = 0x58; e.ifsub = 0x42; e.ifproto = 0; e.nep = 2; e.niface = 1;
    e.vendor = 0x045e; e.product = 0x028e; e.find = 0x414f22u;

    const char *expect =
        "MATCH dev=0x00414f22 class=0x5882 speed=0x00 iface=0x00 "
        "dclass=0x00 dsub=0x00 dproto=0x00 ifclass=0x58 ifsub=0x42 ifproto=0x00 "
        "nep=0x02 niface=0x01 vendor=0x045e product=0x028e find=0x00414f22 "
        "seq=0x00000001\n";

    size_t n = diag_format_event(line, sizeof line, &e);
    CHECK(n == strlen(expect), "MATCH line length correct");
    CHECK(strcmp(line, expect) == 0, "MATCH line is byte-exact");

    /* parse it back (16 fields — port removed) */
    {
        unsigned int dev=0, cls=0, speed=0, iface=0, dclass=0, dsub=0, dproto=0;
        unsigned int ifclass=0, ifsub=0, ifproto=0, nep=0, niface=0, vendor=0, product=0, find=0, seq=0;
        int got = sscanf(line,
            "MATCH dev=0x%08x class=0x%04x speed=0x%02x iface=0x%02x "
            "dclass=0x%02x dsub=0x%02x dproto=0x%02x ifclass=0x%02x ifsub=0x%02x ifproto=0x%02x "
            "nep=0x%02x niface=0x%02x vendor=0x%04x product=0x%04x find=0x%08x seq=0x%08x",
            &dev,&cls,&speed,&iface,&dclass,&dsub,&dproto,
            &ifclass,&ifsub,&ifproto,&nep,&niface,&vendor,&product,&find,&seq);
        CHECK(got == 16, "parser reads all 16 MATCH fields");
        CHECK(dev==0x414f22u && cls==0x5882u && speed==0 && iface==0 &&
              dclass==0 && dsub==0 && dproto==0 && ifclass==0x58 && ifsub==0x42 &&
              ifproto==0 && nep==2 && niface==1 && vendor==0x045e && product==0x028e &&
              find==0x414f22u && seq==1u,
              "parser round-trips every MATCH field");
    }

    /* overflow line */
    memset(&e, 0, sizeof e); e.kind = DIAG_EVT_OVERFLOW; e.a = 7; e.seq = 2;
    diag_format_event(line, sizeof line, &e);
    CHECK(strcmp(line, "OVERFLOW dropped=0x00000007 seq=0x00000002\n") == 0,
          "OVERFLOW line byte-exact");

    /* stockpad line (mask carries the XID port bit) */
    memset(&e, 0, sizeof e); e.kind = DIAG_EVT_STOCKPAD; e.b = 0x9; e.seq = 3;
    diag_format_event(line, sizeof line, &e);
    CHECK(strcmp(line, "STOCKPAD insertions=0x00000009 seq=0x00000003\n") == 0,
          "STOCKPAD line byte-exact");

    /* synthetic line */
    memset(&e, 0, sizeof e); e.kind = DIAG_EVT_SYNTH; e.a = 0xABCDCD; e.seq = 4;
    diag_format_event(line, sizeof line, &e);
    CHECK(strcmp(line, "SYNTH label=0x00abcdcd seq=0x00000004\n") == 0,
          "SYNTH line byte-exact");

    /* truncation safety */
    char tiny[8];
    memset(&e, 0, sizeof e); e.kind = DIAG_EVT_MATCH; e.device = 0xdeadbeef; e.a = 0x1; e.seq = 9;
    size_t tn = diag_format_event(tiny, sizeof tiny, &e);
    CHECK(tn < sizeof tiny, "formatter bounds output to buffer size");
}

/* ---- 4. detour-pin analyzer (rel32 detection + span length) -------------- */
static void test_span_analyzer(void) {
    size_t span_len; long rel_ofs, rel_target;

    /* real pinned prologue: push esi; mov esi,ecx; call rel32 -> 8 bytes, rel32 @3 */
    const uint8_t with_rel[8] = {0x56, 0x8b, 0xf1, 0xe8, 0xc0, 0xf7, 0xff, 0xff};
    CHECK(diag_span_analyze(with_rel, sizeof with_rel, &span_len, &rel_ofs, &rel_target) == 0,
          "span_analyze succeeds on real rel32 prologue");
    CHECK(span_len == 8 && rel_ofs == 3, "span_analyze: span=8, rel32 at offset 3");
    /* call target = 8 + (-0x840) = -0x838 relative to entry (SetExternalPort) */
    CHECK(rel_target == -0x838, "span_analyze: rel32 target is -0x838 rel entry");

    /* a prologue with NO PC-relative instruction: push esi; mov esi,ecx; cmp [esi+0x14],0x20 */
    const uint8_t no_rel[7] = {0x56, 0x8b, 0xf1, 0x83, 0x7e, 0x14, 0x20};
    CHECK(diag_span_analyze(no_rel, sizeof no_rel, &span_len, &rel_ofs, &rel_target) == 0,
          "span_analyze succeeds on no-rel prologue");
    CHECK(span_len >= 5 && rel_ofs == -1, "span_analyze: no rel32 in a cmp-only span");

    /* unknown opcode => fail closed (-1), never guess */
    const uint8_t unknown[8] = {0x0f, 0x85, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}; /* jcc near (0f 85) */
    CHECK(diag_span_analyze(unknown, sizeof unknown, &span_len, &rel_ofs, &rel_target) == -1,
          "span_analyze refuses an unrecognised opcode (0f 85)");
}

/* ---- 5. fail-closed prologue pin ----------------------------------------- */
static void test_pin_span(void) {
    const uint8_t pinned[8] = {0x56, 0x8b, 0xf1, 0xe8, 0xc0, 0xf7, 0xff, 0xff};

    uint8_t match_buf[8]; memcpy(match_buf, pinned, 8);
    CHECK(diag_pin_span(match_buf, pinned, 8) == 1, "pin_span arms on exact prologue");

    uint8_t mismatch[8]; memcpy(mismatch, pinned, 8); mismatch[4] ^= 0xff;
    CHECK(diag_pin_span(mismatch, pinned, 8) == 0, "pin_span refuses when a byte differs (fail-closed)");

    uint8_t short_pin[4] = {0x56, 0x8b, 0xf1, 0xe8};
    uint8_t short_mem[4] = {0x56, 0x8b, 0xf1, 0xe8};
    CHECK(diag_pin_span(short_mem, short_pin, 4) == 0,
          "pin_span refuses a span shorter than the 5-byte E9 (fail-closed)");
}

/* ---- 6. literal-length discipline (DIAG_LIT_LEN) ------------------------- */
static void test_lit_len(void) {
    CHECK(DIAG_LIT_LEN("SYNTH exit=dashboard\n") == 21,
          "DIAG_LIT_LEN(exit line) == 21 (the old hand-count was 18)");
    CHECK(DIAG_LIT_LEN("SYNTH exit=dashboard\n") == strlen("SYNTH exit=dashboard\n"),
          "DIAG_LIT_LEN(exit line) matches strlen");
    CHECK(DIAG_LIT_LEN("MATCH dev=0x00414f22 class=0x5882") ==
          strlen("MATCH dev=0x00414f22 class=0x5882"),
          "DIAG_LIT_LEN matches strlen for a MATCH prefix literal");
    CHECK(DIAG_LIT_LEN("") == 0,
          "DIAG_LIT_LEN of the empty literal is 0");
}

int main(void) {
    printf("AmpJack-OG diagnostic host tests (diag_util.h)\n");
    test_ring();
    test_log();
    test_signature();
    test_span_analyzer();
    test_pin_span();
    test_lit_len();
    if (g_fail == 0) { printf("RESULT: ALL CHECKS PASSED\n"); return 0; }
    printf("RESULT: %d CHECK(S) FAILED\n", g_fail);
    return 1;
}
