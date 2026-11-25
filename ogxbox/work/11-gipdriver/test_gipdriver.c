/*
 * test_gipdriver.c — host tests for the AmpJack-OG GIP class-driver logic.
 *
 * Compiles the SAME ogxbox/gipdriver/src/gipdrive.h the Xbox title compiles,
 * and exercises:
 *   1. URB struct offsets (static asserts against the worker07/09 ABI),
 *   2. trace ring bound + overflow + drain,
 *   3. raw-packet hex formatter (byte-exact),
 *   4. GIP handshake frame builders (power-on / LED / rumble / identify),
 *   5. the wired GIP state machine on synthetic frames: announce -> identify ->
 *      power-on, then an input frame -> decoded snapshot (buttons/sticks/
 *      triggers), matching the og_gamepad map the adapter uses,
 *   6. the FindClassDriver shape-pin + begin-imm logic on synthetic bytes.
 *
 * Build & run (see run_tests.sh):
 *   cc -std=c11 -Wall -Wextra -I ../../gipdriver/src test_gipdriver.c -o test_gipdriver
 *   ./test_gipdriver
 */
#include <stdio.h>
#include <string.h>
#include <stddef.h>
#include "gipdrive.h"

static int g_fail = 0;
#define CHECK(cond, msg) do { \
    if (cond) printf("  ok  %s\n", msg); \
    else { printf("FAIL  %s\n", msg); g_fail++; } \
} while (0)

/* ---- 1. URB offsets (worker07/09 ABI) ---------------------------------- */
_Static_assert(offsetof(gdr_urb_header, Function) == 1, "Function @+1");
_Static_assert(offsetof(gdr_urb_header, Status) == 4, "Status @+4");
_Static_assert(offsetof(gdr_urb_header, CompleteProc) == 8, "CompleteProc @+8");
_Static_assert(offsetof(gdr_urb_header, CompleteContext) == 0xC, "CompleteContext @+0xC");
_Static_assert(offsetof(gdr_urb_open, EndpointHandle) == 0x10, "open EndpointHandle @+0x10");
_Static_assert(offsetof(gdr_urb_open, EndpointAddress) == 0x15, "open EndpointAddress @+0x15");
_Static_assert(offsetof(gdr_urb_open, TransferType) == 0x16, "open TransferType @+0x16");
_Static_assert(offsetof(gdr_urb_open, MaxPacketSize) == 0x1C, "open MaxPacketSize @+0x1C");
_Static_assert(offsetof(gdr_urb_transfer, EndpointHandle) == 0x10, "xfer EndpointHandle @+0x10");
_Static_assert(offsetof(gdr_urb_transfer, TransferLength) == 0x14, "xfer TransferLength @+0x14");
_Static_assert(offsetof(gdr_urb_transfer, TransferBuffer) == 0x18, "xfer TransferBuffer @+0x18");
_Static_assert(offsetof(gdr_urb_transfer, ByteCount) == 0x20, "xfer ByteCount @+0x20");
_Static_assert(offsetof(gdr_class_desc, Register) == 0x04, "desc Register @+0x04");
_Static_assert(offsetof(gdr_class_desc, Attach) == 0x08, "desc Attach @+0x08");
_Static_assert(sizeof(gdr_urb_open) >= 0x20, "open URB >= 0x20 (32B)");
_Static_assert(sizeof(gdr_urb_transfer) >= 0x28, "xfer URB >= 0x28 (40B)");

/* ---- 2. trace ring ------------------------------------------------------ */
static void test_ring(void) {
    struct gdr_ring r; gdr_ring_reset(&r);
    struct gdr_evt e; memset(&e, 0, sizeof e);
    e.kind = GDR_EVT_PACKET; e.len = 0; e.seq = 1;

    int all_in = 1;
    for (u32 i = 0; i < GDR_RING_CAP; i++) { e.seq = i + 1; if (!gdr_ring_push(&r, &e)) all_in = 0; }
    CHECK(all_in && r.count == GDR_RING_CAP, "ring accepts exactly GDR_RING_CAP events");

    e.seq = GDR_RING_CAP + 1;
    CHECK(gdr_ring_push(&r, &e) == 0, "push beyond capacity returns 0 (dropped)");
    CHECK(r.overflow == 1, "overflow counter incremented");
    CHECK(r.count == GDR_RING_CAP, "ring count stays bounded");

    u32 c = 0, o = 0; gdr_ring_drain(&r, &c, &o);
    CHECK(c == GDR_RING_CAP && o == 1, "drain reports count + overflow");
    CHECK(r.count == 0 && r.overflow == 0, "drain resets the ring");
}

/* ---- 3. packet hex formatter -------------------------------------------- */
static void test_packet_fmt(void) {
    char line[256];
    const u8 pkt[5] = { 0x20, 0x00, 0x01, 0x0e, 0x80 };
    gdr_format_packet(line, sizeof line, pkt, 5, 7);
    CHECK(strcmp(line, "PACKET seq=7 n=5 20 00 01 0e 80 \n") == 0,
          "packet hex line byte-exact");
}

/* ---- 4. GIP frame builders ---------------------------------------------- */
static void test_frames(void) {
    u8 buf[64]; int n;
    const u8 expect_power[5]  = { 0x05, 0x20, 0x01, 0x01, 0x00 };
    const u8 expect_sinit[19] = { 0x05, 0x20, 0x01, 0x0f, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00,
                                  0x00, 0x55, 0x53, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };
    const u8 expect_led[7]    = { 0x0a, 0x20, 0x02, 0x03, 0x00, 0x01, 0x14 };
    const u8 expect_rumble[13]= { 0x09, 0x00, 0x03, 0x09, 0x00, 0x0f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };
    const u8 expect_ident[4]  = { 0x04, 0x20, 0x04, 0x00 };
    const u8 expect_ack[13]   = { 0x01, 0x20, 0x07, 0x09, 0x00, 0x06, 0x20, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00 };

    n = gdr_build_power_on(buf, 1);
    CHECK(n == 5 && memcmp(buf, expect_power, 5) == 0, "power-on frame byte-exact [05 20 01 01 00]");
    n = gdr_build_s_init(buf, 1);
    CHECK(n == 19 && memcmp(buf, expect_sinit, 19) == 0, "S-init frame byte-exact (19 B, 55 53 present)");
    n = gdr_build_led(buf, 2);
    CHECK(n == 7 && memcmp(buf, expect_led, 7) == 0, "LED frame byte-exact [0a 20 02 03 00 01 14]");
    n = gdr_build_rumble_stop(buf, 3);
    CHECK(n == 13 && memcmp(buf, expect_rumble, 13) == 0, "rumble-stop frame byte-exact (xpad quiet form)");
    n = gdr_build_identify(buf, 4);
    CHECK(n == 4 && memcmp(buf, expect_ident, 4) == 0, "identify frame byte-exact [04 20 04 00]");
    n = gdr_build_ack(buf, 0x07, 0x06, 2);
    CHECK(n == 13 && memcmp(buf, expect_ack, 13) == 0, "ack frame byte-exact [01 20 ss 09 00 cmd 20 len_le ..]");
}

/* ---- 5. wired GIP state machine (synthetic frames -> decoded state) ----- */
static void test_state_machine(void) {
    struct gdr_gip m; gdr_gip_init(&m, 0);
    u8 frame[128]; int n, drained;
    u8 out[64];

    /* 5a. ANNOUNCE (vendor 0x045e, product 0x0b12) must queue IDENTIFY */
    u8 ann_payload[28]; memset(ann_payload, 0, sizeof ann_payload);
    ann_payload[8] = 0x5e; ann_payload[9] = 0x04;
    ann_payload[10] = 0x12; ann_payload[11] = 0x0b;
    n = gdr_gip_frame(frame, GIP_CMD_ANNOUNCE, GIP_OPT_INTERNAL, 1, ann_payload, 28);
    gdr_gip_rx(&m, frame, n);
    CHECK(m.did_announce && m.vendor == 0x045e && m.product == 0x0b12,
          "announce: identity parsed (045e:0b12)");
    drained = gdr_tx_drain(&m, out, 64);
    CHECK(drained == 4 && out[0] == GIP_CMD_IDENTIFY, "announce queued an IDENTIFY frame");

    /* 5b. IDENTIFY reply with the Gamepad class -> power-on (POWER/LED/RUMBLE)
     * Layout (core/gip.c handle_identify): base = data+16; classes offset at
     * data[26..27] (le16), pointing into base; base[off]=count, then le16
     * length + class string. Use off=12 so the class list sits after the
     * offset field itself. */
    u8 id_payload[64]; memset(id_payload, 0, sizeof id_payload);
    id_payload[26] = 12; id_payload[27] = 0;    /* classes offset = 12 */
    id_payload[28] = 1;                         /* count = 1 class (base[12]) */
    id_payload[29] = 26; id_payload[30] = 0;    /* class string len = 26 (le16) */
    memcpy(id_payload + 31, "Windows.Xbox.Input.Gamepad", 26);
    n = gdr_gip_frame(frame, GIP_CMD_IDENTIFY, GIP_OPT_INTERNAL, 2, id_payload, 57);
    gdr_gip_rx(&m, frame, n);
    CHECK(m.identified && m.gamepad, "identify reply: identified as a gamepad");
    CHECK(m.ready, "identify reply: powered-ready (start_gamepad ran)");
    /* drain -> POWER then S-init then LED then RUMBLE */
    drained = gdr_tx_drain(&m, out, 64);
    CHECK(drained == 5 && out[0] == GIP_CMD_POWER && out[4] == 0x00, "start queues POWER first");
    drained = gdr_tx_drain(&m, out, 64);
    CHECK(drained == 19 && out[0] == GIP_CMD_POWER && out[3] == 0x0f && out[4] == 0x06
          && out[11] == 0x55 && out[12] == 0x53, "then S-init (19 B, 'US' present)");
    drained = gdr_tx_drain(&m, out, 64);
    CHECK(drained == 7 && out[0] == GIP_CMD_LED, "then LED");
    drained = gdr_tx_drain(&m, out, 64);
    CHECK(drained == 13 && out[0] == GIP_CMD_RUMBLE, "then RUMBLE stop");
    CHECK(gdr_tx_drain(&m, out, 64) == 0, "tx queue now empty");

    /* 5c. INPUT frame -> decoded snapshot (buttons/sticks/triggers) */
    u8 in_payload[14] = { 0 };
    in_payload[0] = 0x10; in_payload[1] = 0x01;  /* A (bit4) + DPAD_UP (bit8) */
    in_payload[2] = 0x00; in_payload[3] = 0x02;  /* trigger_left = 512 */
    in_payload[4] = 0x00; in_payload[5] = 0x00;  /* trigger_right = 0 */
    in_payload[6] = 0x00; in_payload[7] = 0x01;  /* lx = 256 */
    in_payload[8] = 0x00; in_payload[9] = 0xff;  /* ly = -256 */
    in_payload[10] = 0x00; in_payload[11] = 0x00; /* rx = 0 */
    in_payload[12] = 0x00; in_payload[13] = 0x00; /* ry = 0 */
    n = gdr_gip_frame(frame, GIP_CMD_INPUT, 0x00, 3, in_payload, 14);
    gdr_gip_rx(&m, frame, n);
    CHECK(m.snapshot_valid && m.input_reports == 1, "input frame decoded (snapshot valid)");
    CHECK(m.snap.buttons == 0x0001, "buttons: DPAD_UP bit set (A is analog)");
    CHECK(m.snap.analog[0] == 0xff, "A pressed (analog A = 0xff)");
    CHECK(m.snap.analog[6] == 127, "trigger_left 512 -> 127 analog");
    CHECK(m.snap.lx == 256 && m.snap.ly == -256, "sticks decoded (lx=256 ly=-256)");

    /* 5d. state line formatter */
    char sline[128];
    size_t sn = gdr_format_state(sline, sizeof sline, &m.snap);
    CHECK(sn > 0 &&
          strcmp(sline, "buttons=0x0001 lx=256 ly=-256 rx=0 ry=0 lt=127 rt=0") == 0,
          "state line byte-exact");
}

/* ---- 6. FindClassDriver shape-pin on synthetic bytes -------------------- */
static void test_pin_findclass(void) {
    /* the real prologue shape: push esi; mov eax,<begin>; mov esi,<end> */
    const u8 prologue[12] = { 0x56, 0xB8, 0x14, 0x80, 0x02, 0x00,
                              0xBE, 0x20, 0x80, 0x02, 0x00, 0x00 }; /* begin=0x28014 */
    u32 begin_out = 0;
    unsigned int pins = gdr_pin_findclass(prologue, 0x00028014u, &begin_out);
    CHECK(pins == 0x3, "shape+begin pin matches (56 B8 + imm 0x28014)");
    CHECK(begin_out == 0x00028014u, "begin imm extracted (0x28014)");

    /* wrong shape => no shape bit */
    const u8 bad_shape[12] = { 0x55, 0xB8, 0x14, 0x80, 0x02, 0x00,
                               0xBE, 0x20, 0x80, 0x02, 0x00, 0x00 };
    pins = gdr_pin_findclass(bad_shape, 0x00028014u, &begin_out);
    CHECK((pins & 0x1) == 0, "non-56 first byte refuses (fail-closed)");

    /* wrong begin imm => shape ok but no begin bit */
    pins = gdr_pin_findclass(prologue, 0xDEADBEEFu, &begin_out);
    CHECK((pins & 0x1) == 0x1 && (pins & 0x2) == 0, "mismatched begin imm fails the begin bit");
}

/* ---- 7. arm gate + transport-live guard + loop cadence (worker 11 fix) -- */
static void test_arm_gate(void) {
    /* real prologue shape: push esi; mov eax,<begin=0x26014>; mov esi,<end> */
    const u8 prologue[12] = { 0x56, 0xB8, 0x14, 0x60, 0x02, 0x00,
                              0xBE, 0x20, 0x60, 0x02, 0x00, 0x00 };
    u32 begin_out = 0;
    unsigned int pins = gdr_pin_findclass(prologue, 0x00026014u, &begin_out);
    CHECK(pins == (GDR_PIN_SHAPE | GDR_PIN_BEGIN),
          "pin: shape+begin emit 0x3 (56 B8 + imm 0x26014)");
    unsigned int full = pins | GDR_PIN_WRITABLE;
    CHECK(full == GDR_PIN_ALL, "pin + writable == PIN_ALL (0x7)");
    CHECK(gdr_gip_arm_gate(full) == 0,
          "arm gate ACCEPTS a fully-matching FindClassDriver (was armcode=1)");

    CHECK(gdr_gip_arm_gate(pins) == 1,
          "arm gate REFUSES without writable (fail-closed)");

    /* begin-imm mismatch -> begin bit absent -> refuse even with writable */
    u32 b2 = 0;
    unsigned int p2 = gdr_pin_findclass(prologue, 0xDEADBEEFu, &b2) | GDR_PIN_WRITABLE;
    CHECK(gdr_gip_arm_gate(p2) == 1, "arm gate REFUSES begin-imm mismatch");
}

static void test_transport_live(void) {
    CHECK(gdr_transport_live(0, 0) == 0,        "PINFAIL (not attached) => transport OFF");
    CHECK(gdr_transport_live(1, 0) == 0,        "attached but IN not open => transport OFF");
    CHECK(gdr_transport_live(0, 0x1234) == 0,   "attach never ran => transport OFF");
    CHECK(gdr_transport_live(1, 0x1234) == 1,   "attached + IN open => transport ON");
}

static void test_loop_pinfail(void) {
    /* Drive the main-loop skeleton with arm=fail: Attach never ran, so
     * attached=0 / in_handle=0 / device=NULL. The submit sink stands in for
     * usbd_SubmitRequest(device=NULL): if the loop ever opens transport it WILL
     * deref NULL, so we assert the sink is reached zero times and that the loop
     * still exits on time and heartbeats every 5 s. */
    u32 now_ms = 0, last_hb = 0;
    int transport_at_any_tick = 0, submit_calls = 0, exited = 0;
    int hb_count = 0, hb_ok = 1, guard = 1;
    const int attached = 0; const u32 in_handle = 0;
    for (;;) {
        now_ms += GDR_TICK_MS;
        if (gdr_transport_live(attached, in_handle)) {
            transport_at_any_tick = 1;
            submit_calls++;                  /* == a NULL-device deref on Xbox */
        }
        if (now_ms - last_hb >= GDR_HB_PERIOD_MS) {
            if (now_ms % GDR_HB_PERIOD_MS != 0) hb_ok = 0;
            last_hb = now_ms; hb_count++;
        }
        if (now_ms >= GDR_EXIT_AFTER_MS) { exited = 1; break; }
        if (++guard > 100000) break;
    }
    CHECK(!transport_at_any_tick, "PINFAIL loop: transport NEVER enabled");
    CHECK(submit_calls == 0,        "PINFAIL loop: submit sink called 0 times (no NULL URB)");
    CHECK(exited,                   "PINFAIL loop: reached the exit after 60 s");
    CHECK(now_ms == GDR_EXIT_AFTER_MS, "PINFAIL loop: exit exactly at GDR_EXIT_AFTER_MS");
    CHECK(hb_count == (int)(GDR_EXIT_AFTER_MS / GDR_HB_PERIOD_MS) && hb_ok,
          "PINFAIL loop: heartbeat every 5 s for the full run");
}

static void test_loop_armed(void) {
    u32 now_ms = 0, last_hb = 0; int submit_calls = 0, exited = 0, guard = 1;
    const int attached = 1; const u32 in_handle = 0x1234;
    for (;;) {
        now_ms += GDR_TICK_MS;
        if (gdr_transport_live(attached, in_handle)) submit_calls++;
        if (now_ms - last_hb >= GDR_HB_PERIOD_MS) last_hb = now_ms;
        if (now_ms >= GDR_EXIT_AFTER_MS) { exited = 1; break; }
        if (++guard > 100000) break;
    }
    CHECK(submit_calls > 0, "armed loop: transport live, submit path runs");
    CHECK(exited,            "armed loop: reaches exit too");
}

int main(void) {
    printf("AmpJack-OG GIP driver host tests (gipdrive.h)\n");
    test_ring();
    test_packet_fmt();
    test_frames();
    test_state_machine();
    test_pin_findclass();
    test_arm_gate();
    test_transport_live();
    test_loop_pinfail();
    test_loop_armed();
    if (g_fail == 0) { printf("RESULT: ALL CHECKS PASSED\n"); return 0; }
    printf("RESULT: %d CHECK(S) FAILED\n", g_fail);
    return 1;
}
