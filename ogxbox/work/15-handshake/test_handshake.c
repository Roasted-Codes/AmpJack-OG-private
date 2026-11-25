/*
 * test_handshake.c — host tests for the worker-15 v3 fixes (gipdrive.h).
 *
 * Compiles the SAME ogxbox/gipdriver/src/gipdrive.h the Xbox title compiles
 * and exercises the three bugs the real-pad xemu run exposed, RED -> GREEN:
 *
 *   1. Log truncation: every event kind formats to a '\n'-terminated line in a
 *      256-byte buffer, and a full 64-byte packet prints all 64 bytes.
 *   2. IN/OUT separation: a fake SubmitRequest completes OUT then IN; the ring
 *      records TXDONE (OUT) vs RX (IN), and the OUT/IN buffers never cross.
 *   3. Handshake bytes + TransferLength: power-on / S-init / LED / rumble-off /
 *      identify / ack frames are byte-exact, and the OUT URB's TransferLength is
 *      the frame length (never mps=64).
 *   4. Handshake completeness: announce -> identify, needs-ack -> ack, and the
 *      start_gamepad sequence (power->S-init->LED->rumble) is monotonic.
 *
 * Build & run (see run_tests.sh):
 *   cc -std=c11 -Wall -Wextra -I ../../gipdriver/src test_handshake.c -o test_handshake
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

/* ---- 1. gdr_format_event: '\n'-terminated, 256-byte buffer, 64 B fully --- */

static void test_format_event(void) {
    char line[256];
    struct gdr_evt e;
    size_t n;

    int kinds[] = {
        GDR_EVT_PACKET, GDR_EVT_ATTACH, GDR_EVT_OPEN, GDR_EVT_SUBMIT,
        GDR_EVT_ERR, GDR_EVT_STATE, GDR_EVT_LOG, GDR_EVT_RX, GDR_EVT_TXDONE,
        GDR_EVT_IDENTIFY, GDR_EVT_ACK, GDR_EVT_CFG, GDR_EVT_OPENCTRL,
        GDR_EVT_STEPFAIL, GDR_EVT_CFGFAIL
    };
    int all_nl = 1, all_fit = 1;
    for (unsigned i = 0; i < sizeof(kinds)/sizeof(kinds[0]); i++) {
        memset(&e, 0, sizeof e);
        e.kind = (u32)kinds[i]; e.a = 0x12345678; e.b = 0x0201; e.c = 0x0302;
        e.d = 0; e.len = 3; e.seq = 2;
        e.data[0] = 0x20; e.data[1] = 0x00; e.data[2] = 0x01;
        n = gdr_format_event(line, sizeof line, &e);
        if (n == 0 || line[n-1] != '\n') all_nl = 0;
        if (n > 255) all_fit = 0;
    }
    CHECK(all_nl, "format: every event kind ends with '\\n'");
    CHECK(all_fit, "format: every event kind fits a 256-byte line");

    /* a full 64-byte packet prints all 64 bytes */
    memset(&e, 0, sizeof e);
    e.kind = GDR_EVT_RX; e.a = 0; e.len = 64; e.seq = 9;
    for (u32 i = 0; i < 64; i++) e.data[i] = (u8)i;
    n = gdr_format_event(line, sizeof line, &e);
    CHECK(line[n-1] == '\n', "format: 64-byte RX line ends with '\\n'");
    CHECK(strstr(line, "3f ") != NULL, "format: 64-byte RX prints byte 63 (0x3f)");
    CHECK(strstr(line, "n=64 00 ") != NULL, "format: 64-byte RX prints byte 0");

    /* CFG round-trips the packed struct fields (worker14 lost these) */
    memset(&e, 0, sizeof e);
    e.kind = GDR_EVT_CFG;
    e.a = 0 | (0x82 << 8) | (0x02 << 16) | (1 << 24);  /* iface0, 0x82/0x02, cfg1 */
    e.b = 64 | (64 << 16);
    e.c = 4 | (4 << 8);
    e.seq = 3;
    n = gdr_format_event(line, sizeof line, &e);
    CHECK(strstr(line, "iface=0 ep_in=0x82 ep_out=0x02 mps_in=64 mps_out=64 int_in=4 int_out=4 cfgval=1") != NULL,
          "format: CFG line un-truncated (the worker14 >64-byte loss)");
}

/* ---- 2. handshake frame bytes + TransferLength + IN/OUT separation ------ */

struct sim_rec {
    u8  function;
    u32 endpoint_handle;
    u32 transfer_length;
    u32 transfer_buffer;
};
static struct sim_rec g_sim[32];
static int g_sim_n;

static long fake_submit(void *device, void *urb) {
    (void)device;
    struct sim_rec *r = &g_sim[g_sim_n++];
    gdr_urb_header *h = (gdr_urb_header*)urb;
    memset(r, 0, sizeof *r);
    r->function = h->Function;
    if (h->Function == 0x41) {
        gdr_urb_transfer *t = (gdr_urb_transfer*)urb;
        r->endpoint_handle = t->EndpointHandle;
        r->transfer_length = t->TransferLength;
        r->transfer_buffer = t->TransferBuffer;
    }
    return 0;
}

/* local IN completion: log RX from rx_buf, mirror main.c's gip_in_complete */
static void fake_in_complete(void *urb, void *ctx) {
    (void)urb;
    struct gdr_attach_ctx *ctx2 = (struct gdr_attach_ctx*)ctx;
    gdr_urb_transfer *u = &ctx2->in_urb;
    u32 n = u->ByteCount;
    if (n > 64) n = 64;
    struct gdr_evt e; memset(&e, 0, sizeof e);
    e.kind = GDR_EVT_RX; e.a = u->TransferStatus; e.len = n; e.seq = 99;
    for (u32 i = 0; i < n; i++) e.data[i] = ctx2->rx_buf[i];
    gdr_ring_push(ctx2->ring, &e);
}

static void test_out_queue_separation(void) {
    static struct gdr_attach_ctx ctx;
    static struct gdr_ring ring;
    memset(&ctx, 0, sizeof ctx);
    gdr_ring_reset(&ring);
    ctx.device = (void*)0x1234;
    ctx.submit = fake_submit;
    ctx.ring   = &ring;
    ctx.in_handle  = 0xAAAA;
    ctx.out_handle = 0xBBBB;
    ctx.in_urb.TransferBuffer = GDR_P2U32(ctx.rx_buf);
    ctx.in_urb.TransferLength = 64;

    /* handshake frames, byte-exact + lengths */
    const u8 power[5]   = { 0x05, 0x20, 0x01, 0x01, 0x00 };
    const u8 s_init[19] = { 0x05, 0x20, 0x02, 0x0f, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00,
                            0x00, 0x55, 0x53, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };
    const u8 led[7]     = { 0x0a, 0x20, 0x03, 0x03, 0x00, 0x01, 0x14 };
    const u8 rumble[13] = { 0x09, 0x00, 0x04, 0x09, 0x00, 0x0f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };
    const u8 ident[4]   = { 0x04, 0x20, 0x05, 0x00 };
    const u8 ack[13]    = { 0x01, 0x20, 0x06, 0x09, 0x00, 0x07, 0x20, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00 };

    u8 buf[64]; int blen;
    blen = gdr_build_power_on(buf, 1);
    CHECK(blen == 5  && memcmp(buf, power, 5) == 0, "frame: power-on byte-exact, len 5");
    blen = gdr_build_s_init(buf, 2);
    CHECK(blen == 19 && memcmp(buf, s_init, 19) == 0
          && buf[11] == 0x55 && buf[12] == 0x53, "frame: S-init byte-exact (19 B, 'US' kept)");
    blen = gdr_build_led(buf, 3);
    CHECK(blen == 7  && memcmp(buf, led, 7) == 0, "frame: LED byte-exact, len 7");
    blen = gdr_build_rumble_stop(buf, 4);
    CHECK(blen == 13 && memcmp(buf, rumble, 13) == 0, "frame: rumble-stop byte-exact, len 13");
    blen = gdr_build_identify(buf, 5);
    CHECK(blen == 4  && memcmp(buf, ident, 4) == 0, "frame: identify byte-exact, len 4");
    blen = gdr_build_ack(buf, 6, 0x07, 2);
    CHECK(blen == 13 && memcmp(buf, ack, 13) == 0, "frame: ack byte-exact, len 13");

    g_sim_n = 0;

    /* 1. enqueue S-init, kick -> OUT URB #1 with exact length + dedicated buffer */
    CHECK(gdr_tx_enqueue(&ctx, s_init, 19) == 1, "out: enqueue 19-byte S-init");
    gdr_tx_submit_next(&ctx);
    CHECK(g_sim_n == 1 && g_sim[0].function == 0x41 && g_sim[0].endpoint_handle == ctx.out_handle,
          "out: OUT URB #1 targets the OUT handle");
    CHECK(g_sim[0].transfer_length == 19, "out: TransferLength = frame length 19 (NOT mps 64)");
    CHECK(g_sim[0].transfer_buffer == GDR_P2U32(ctx.tx_buf), "out: TransferBuffer = dedicated tx_buf");
    CHECK(memcmp(ctx.tx_buf, s_init, 19) == 0, "out: tx_buf holds the exact S-init bytes");

    /* buffers never cross */
    CHECK(GDR_P2U32(ctx.tx_buf) != GDR_P2U32(ctx.rx_buf), "sep: tx_buf and rx_buf are distinct storage");
    CHECK(ctx.tx_urb.TransferBuffer != ctx.in_urb.TransferBuffer, "sep: OUT vs IN TransferBuffer differ");

    /* 2. enqueue LED while S-init is still in flight (queue, not immediate) */
    CHECK(gdr_tx_enqueue(&ctx, led, 7) == 1, "out: enqueue LED behind S-init");

    /* 3. complete S-init -> TXDONE, then auto-send LED from TXDONE */
    gdr_tx_complete(&ctx.tx_urb, &ctx);
    CHECK(g_sim_n == 2 && g_sim[1].transfer_length == 7, "out: next frame sent from TXDONE (LED now in flight)");
    {
        u32 c = 0, o = 0; gdr_ring_drain(&ring, &c, &o);
        CHECK(c == 1 && ring.slots[0].kind == GDR_EVT_TXDONE, "sep: OUT completion -> TXDONE (NOT RX)");
        CHECK(ring.slots[0].len == 19 && ring.slots[0].b == 0x05, "sep: TXDONE carries len 19 + command 0x05");
    }

    /* 4. complete LED -> second TXDONE, queue now empty, nothing re-submits */
    gdr_tx_complete(&ctx.tx_urb, &ctx);
    {
        u32 c = 0, o = 0; gdr_ring_drain(&ring, &c, &o);
        CHECK(c == 1 && ring.slots[0].kind == GDR_EVT_TXDONE && ring.slots[0].len == 7,
              "sep: LED completion -> TXDONE len 7");
    }

    /* 5. IN completion -> RX carrying the IN buffer's bytes (never OUT bytes) */
    for (u32 i = 0; i < 64; i++) ctx.rx_buf[i] = 0xE0 + (u8)(i & 0x0F);
    ctx.in_urb.ByteCount = 8;
    ctx.in_urb.TransferStatus = 0;
    fake_in_complete(&ctx.in_urb, &ctx);
    {
        u32 c = 0, o = 0; gdr_ring_drain(&ring, &c, &o);
        CHECK(c == 1 && ring.slots[0].kind == GDR_EVT_RX, "sep: IN completion -> RX kind");
        CHECK(ring.slots[0].len == 8, "sep: RX records true ByteCount 8 (not forced 64)");
        int match = 1;
        for (u32 i = 0; i < 8; i++) if (ring.slots[0].data[i] != ctx.rx_buf[i]) match = 0;
        CHECK(match, "sep: RX data == rx_buf bytes (never tx_buf)");
    }
}

/* ---- 3. handshake completeness: announce/identify/ack + monotonic seq ---- */

static void test_handshake_flow(void) {
    struct gdr_gip m; gdr_gip_init(&m, 0);
    u8 frame[128]; int n, drained; u8 out[64];

    /* announce -> identify */
    u8 ann[28]; memset(ann, 0, sizeof ann);
    ann[8] = 0x5e; ann[9] = 0x04; ann[10] = 0x12; ann[11] = 0x0b;
    n = gdr_gip_frame(frame, GIP_CMD_ANNOUNCE, GIP_OPT_INTERNAL, 1, ann, 28);
    gdr_gip_rx(&m, frame, n);
    CHECK(m.did_announce && m.vendor == 0x045e && m.product == 0x0b12, "hsk: announce parsed");
    drained = gdr_tx_drain(&m, out, 64);
    CHECK(drained == 4 && out[0] == GIP_CMD_IDENTIFY && out[2] == 1, "hsk: announce -> identify (seq 1)");

    /* identify reply with a Gamepad class -> start_gamepad */
    u8 idp[64]; memset(idp, 0, sizeof idp);
    idp[26] = 12; idp[27] = 0; idp[28] = 1; idp[29] = 26; idp[30] = 0;
    memcpy(idp + 31, "Windows.Xbox.Input.Gamepad", 26);
    n = gdr_gip_frame(frame, GIP_CMD_IDENTIFY, GIP_OPT_INTERNAL, 2, idp, 57);
    gdr_gip_rx(&m, frame, n);
    CHECK(m.identified && m.gamepad && m.ready, "hsk: identify -> gamepad + start");

    /* start_gamepad emits power->S-init->LED->rumble, monotonic sequence */
    u8 seqs[4], cmds[4]; int lens[4];
    for (int i = 0; i < 4; i++) {
        drained = gdr_tx_drain(&m, out, 64);
        CHECK(drained > 0, "hsk: 4 init frames queued");
        seqs[i] = out[2]; lens[i] = drained; cmds[i] = out[0];
    }
    CHECK(gdr_tx_drain(&m, out, 64) == 0, "hsk: init queue empty after 4 frames");
    CHECK(lens[0] == 5 && cmds[0] == GIP_CMD_POWER, "hsk: power-on first");
    CHECK(lens[1] == 19 && cmds[1] == GIP_CMD_POWER, "hsk: S-init second (POWER cmd, 19 B)");
    CHECK(cmds[2] == GIP_CMD_LED, "hsk: LED third");
    CHECK(cmds[3] == GIP_CMD_RUMBLE, "hsk: rumble-off fourth");
    int mono = 1, nonzero = 1;
    for (int i = 0; i < 4; i++) { if (seqs[i] == 0) nonzero = 0; if (i && seqs[i] <= seqs[i-1]) mono = 0; }
    CHECK(nonzero, "hsk: GIP sequence never 0");
    CHECK(mono, "hsk: GIP sequence monotonic across the init frames");

    /* needs-ack frame -> ACK queued (echo incoming seq + len) */
    u8 mode[2] = { 0x01, 0x5b };   /* guide/mode report */
    n = gdr_gip_frame(frame, 0x07, GIP_OPT_ACK, 0x42, mode, 2);
    gdr_gip_rx(&m, frame, n);
    drained = gdr_tx_drain(&m, out, 64);
    CHECK(drained == 13, "hsk: needs-ack frame queues a 13-byte ACK");
    CHECK(out[0] == GIP_CMD_ACK && out[1] == GIP_OPT_INTERNAL && out[2] == 0x42,
          "hsk: ACK echoes the incoming sequence (0x42)");
    CHECK(out[5] == 0x07 && out[6] == 0x20 && out[7] == 0x02 && out[8] == 0x00,
          "hsk: ACK payload = 00 <cmd> 20 <le16 len> ...");
}

int main(void) {
    printf("AmpJack-OG worker15 handshake host tests (gipdrive.h v3)\n");
    test_format_event();
    test_out_queue_separation();
    test_handshake_flow();
    if (g_fail == 0) { printf("RESULT: ALL CHECKS PASSED\n"); return 0; }
    printf("RESULT: %d CHECK(S) FAILED\n", g_fail);
    return 1;
}
