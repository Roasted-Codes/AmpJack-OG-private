/*
 * test_sol17.c — worker-17 regressions for the corrected transport/gate path.
 *
 * Compiles the SAME ogxbox/gipdriver/src/gipdrive.h the Xbox title compiles and
 * exercises the REAL gdr_in_complete / gdr_tx_complete / submit path (NOT the
 * worker15 fake_in_complete), against the disassembly-verified URB semantics:
 *
 *   1. +0x14 = requested@submit / actual-completed@completion; +0x20 = original
 *      mapped length (NOT received); +0x04 = real status; +0x24 = linkage.
 *   2. Immediate reject vs delayed vs synchronous completion: no false pending,
 *      one request/one completion, no recursion storm, no silent TX loss.
 *   3. Qualified no-announce/no-identify wired startup -> valid 0x20 input
 *      decodes to a full snapshot (A/trigger/sticks), with complete state log.
 *   4. Real 0b12 config fixture -> alt0 interval4; malformed/oversized fail
 *      closed; the head/tail handoff never overwrites undrained events.
 *
 * Build & run (from repo root):
 *   cc -std=c11 -Wall -Wextra -I ogxbox/gipdriver/src \
 *      ogxbox/work/17-sol-execution/test_sol17.c -o ogxbox/work/17-sol-execution/test17
 *   ogxbox/work/17-sol-execution/test17
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

/* ------------------------------------------------------------------ */
/* Fake SubmitRequest: records the re-armed IN request and can model    */
/* an immediate rejection, a delayed (async) completion, or a           */
/* synchronous re-entrant completion.                                    */
/* ------------------------------------------------------------------ */
static struct gdr_attach_ctx *g_ctx;
static long g_sim_ret    = 0;   /* submit return value                  */
static int  g_sim_sync   = 0;   /* 1 => complete synchronously           */
static u32  g_sim_sync_len = 8; /* length to fake on the sync completion */
static int  g_sim_resubmits = 0;/* # of re-arm submits observed          */

static long fake_submit(void *device, void *urb) {
    (void)device;
    if (g_sim_sync) {
        /* model a synchronous completion of THIS (re-armed) request with a
         * short 8-byte frame, then still return success. */
        ((gdr_urb_transfer*)urb)->TransferLength = g_sim_sync_len;
        ((gdr_urb_transfer*)urb)->Hdr.Status = 0;
        g_sim_resubmits++;
        gdr_in_complete(urb, g_ctx);
        return 0;
    }
    g_sim_resubmits++;
    return g_sim_ret;
}

static void setup_ctx(struct gdr_attach_ctx *ctx, struct gdr_ring *ring) {
    memset(ctx, 0, sizeof *ctx);
    gdr_ring_reset(ring);
    ctx->device = (void*)0x1234;
    ctx->submit = fake_submit;
    ctx->ring   = ring;
    ctx->in_handle  = 0xAAAA;
    ctx->out_handle = 0xBBBB;
    ctx->mps_in = 64;
    g_ctx = ctx;
    g_sim_ret = 0; g_sim_sync = 0; g_sim_sync_len = 8; g_sim_resubmits = 0;
}

/* ------------------------------------------------------------------ */
/* 1. Field semantics of the REAL gdr_in_complete                       */
/* ------------------------------------------------------------------ */
static void test_in_complete_fields(void) {
    static struct gdr_attach_ctx ctx;
    static struct gdr_ring ring;
    struct gdr_evt e; u32 c, o;
    int i;

    /* ---- requested64, completion8 at +14, mapped (+20) stays 64 -------- */
    setup_ctx(&ctx, &ring);
    ctx.in_urb.TransferLength = 8;          /* HCD accumulated actual = 8    */
    ctx.in_urb.ByteCount      = 64;         /* mapped length stays 64 (+20)  */
    ctx.in_urb.Hdr.Status     = 0;
    ctx.in_urb.TransferStatus = 0;          /* linkage                       */
    ctx.in_req_id = 1;                       /* this completed request = 1   */
    ctx.in_flight = 1;
    for (i = 0; i < 8; i++) ctx.rx_buf[i] = 0xA0 + i;
    gdr_in_complete(&ctx.in_urb, &ctx);

    c = 0; o = 0; gdr_ring_drain(&ring, &c, &o);
    CHECK(c == 1, "in_complete: exactly ONE 8-byte RX event (not two)");
    if (c == 1) {
        CHECK(ring.slots[0].kind == GDR_EVT_RX, "in_complete: event kind RX");
        CHECK(ring.slots[0].len == 8, "in_complete: actual length 8 from +14 (not +20==64)");
        CHECK(ring.slots[0].b == 64, "in_complete: requested size logged as 64");
        int m = 1;
        for (i = 0; i < 8; i++) if (ring.slots[0].data[i] != (u8)(0xA0 + i)) m = 0;
        CHECK(m, "in_complete: RX payload == rx_buf[0..7]");
    }
    CHECK(ctx.in_urb.TransferLength == 64, "in_complete: re-armed +14 reset to mps 64");
    CHECK(ctx.in_flight == 1, "in_complete: re-armed request is pending (in_flight=1)");
    CHECK(g_sim_resubmits == 1, "in_complete: re-armed exactly once");

    /* ---- zero-length completion stays 0 (never fabricated 64) -------- */
    setup_ctx(&ctx, &ring);
    ctx.in_req_id = 1; ctx.in_flight = 1;
    ctx.in_urb.TransferLength = 64; ctx.in_urb.ByteCount = 64; ctx.in_urb.Hdr.Status = 0;
    ctx.in_urb.TransferLength = 0;           /* 0-byte completion           */
    gdr_in_complete(&ctx.in_urb, &ctx);
    gdr_ring_drain(&ring, &c, &o);
    CHECK(c == 1 && ring.slots[0].kind == GDR_EVT_RX && ring.slots[0].len == 0,
          "in_complete: 0-byte completion stays 0 (no fabricated 64)");
    CHECK(ctx.in_urb.TransferLength == 64, "in_complete: next request still armed at 64");

    /* ---- negative Hdr.Status + nonzero +24 linkage does NOT publish ----- */
    setup_ctx(&ctx, &ring);
    ctx.in_req_id = 1; ctx.in_flight = 1;
    ctx.in_urb.TransferLength = 8;
    ctx.in_urb.ByteCount      = 64;
    ctx.in_urb.Hdr.Status     = 0xC0000004u;  /* real status: negative     */
    ctx.in_urb.TransferStatus = 0x12345678u;  /* linkage: nonzero (old bug) */
    ctx.rx_events = 0;
    gdr_in_complete(&ctx.in_urb, &ctx);
    gdr_ring_drain(&ring, &c, &o);
    CHECK(c == 0, "in_complete: failed completion publishes NO stale RX");
    CHECK(ctx.rx_events == 0, "in_complete: rx_events unchanged on failure");
    CHECK(ctx.in_flight == 0, "in_complete: not re-armed after negative status");
    CHECK(g_sim_resubmits == 0, "in_complete: no re-submit after negative status");
}

/* ------------------------------------------------------------------ */
/* 2. Immediate reject vs delayed vs synchronous completion            */
/* ------------------------------------------------------------------ */
static void test_submit_correlation(void) {
    static struct gdr_attach_ctx ctx;
    static struct gdr_ring ring;
    u32 c, o;

    /* ---- immediate rejection: no false pending, failure accounted ------ */
    setup_ctx(&ctx, &ring);
    g_sim_ret = -1L;                          /* SubmitRequest rejects       */
    ctx.in_req_id = 1; ctx.in_flight = 1;
    ctx.in_urb.TransferLength = 8; ctx.in_urb.Hdr.Status = 0;
    gdr_in_complete(&ctx.in_urb, &ctx);
    CHECK(ctx.in_flight == 0, "reject: in_flight NOT set after rejected submit");
    CHECK(ctx.in_submit_fail == 1, "reject: in_submit_fail counted");
    CHECK(g_sim_resubmits == 1, "reject: submit attempted exactly once");

    /* ---- delayed completion: one request / one completion --------------- */
    setup_ctx(&ctx, &ring);
    g_sim_ret = 0;                            /* queued, completes later    */
    ctx.req_id = 1; ctx.in_req_id = 1; ctx.in_flight = 1;  /* request 1 pending */
    ctx.in_urb.TransferLength = 8; ctx.in_urb.Hdr.Status = 0;
    for (int i = 0; i < 8; i++) ctx.rx_buf[i] = i;
    gdr_in_complete(&ctx.in_urb, &ctx);       /* request A completes, re-arms */
    /* request A produced exactly one RX, and one re-armed request is pending */
    gdr_ring_drain(&ring, &c, &o);
    CHECK(c == 1 && ring.slots[0].len == 8, "delayed: one completion -> one 8B RX");
    CHECK(ctx.in_flight == 1 && ctx.in_req_id == 2, "delayed: re-armed request id 2 pending");
    g_sim_sync = 0;
    /* a later, unrelated completion of request 2 (delayed) */
    ctx.in_urb.TransferLength = 64; ctx.in_urb.Hdr.Status = 0;
    gdr_in_complete(&ctx.in_urb, &ctx);
    gdr_ring_drain(&ring, &c, &o);
    CHECK(c == 1 && ring.slots[0].len == 64, "delayed: second delayed completion -> one 64B RX");
    CHECK(ctx.in_flight == 1, "delayed: re-armed again (stream steady-state)");

    /* ---- synchronous completion: no recursion storm --------------------- */
    setup_ctx(&ctx, &ring);
    g_sim_ret = 0; g_sim_sync = 1;           /* complete inline within submit */
    ctx.in_req_id = 1; ctx.in_flight = 1;
    ctx.in_urb.TransferLength = 8; ctx.in_urb.Hdr.Status = 0;
    gdr_in_complete(&ctx.in_urb, &ctx);      /* request A completes; re-arm completes sync */
    /* the synchronous inner completion must NOT re-arm again (guard), so the
     * number of submits stays bounded at exactly 1, and there is no pending
     * flag left set (the sync request already completed). */
    CHECK(g_sim_resubmits == 1, "sync: submit invoked exactly once (no recursion storm)");
    CHECK(ctx.in_flight == 0, "sync: no false pending after sync completion");
    CHECK(ctx.in_submit_fail == 0, "sync: no rejection counted");
}

/* ------------------------------------------------------------------ */
/* 3. Qualified no-announce/no-identify wired startup + full decode    */
/* ------------------------------------------------------------------ */
static void test_qualified_wired(void) {
    struct gdr_gip m;
    u8 out[64]; int n;
    char sline[160];

    gdr_gip_init(&m, 0);
    CHECK(m.gamepad == 0, "wired: gamepad starts 0 (unqualified)");

    gdr_gip_qualify_wired(&m);
    CHECK(m.gamepad == 1 && m.identified == 1 && m.fallback == 1,
          "wired: qualify sets gamepad/identified/fallback (no identify)");
    CHECK(m.snapshot_valid == 0, "wired: snapshot still invalid before any input");

    /* minimal startup: exactly ONE frame queued = power-on (no LED/rumble) */
    n = gdr_tx_drain(&m, out, 64);
    CHECK(n == 5 && out[0] == GIP_CMD_POWER && out[1] == GIP_OPT_INTERNAL && out[4] == 0x00,
          "wired: power-on is the ONLY first frame (minimal, no LED/rumble)");
    CHECK(gdr_tx_drain(&m, out, 64) == 0, "wired: no S-init/LED/rumble queued yet (serialized)");

    /* S-init follows only on successful power-on completion */
    gdr_gip_on_power_done(&m);
    n = gdr_tx_drain(&m, out, 64);
    CHECK(n == 19 && out[0] == GIP_CMD_POWER && out[3] == 0x0f && out[4] == 0x06
          && out[11] == 0x55 && out[12] == 0x53,
          "wired: S-init (19 B, 'US') follows power-on completion");
    CHECK(gdr_tx_drain(&m, out, 64) == 0, "wired: S-init sent exactly once");
    gdr_gip_on_power_done(&m);   /* idempotent: no duplicate */
    CHECK(gdr_tx_drain(&m, out, 64) == 0, "wired: second power-done is a no-op");

    /* SYNTHETIC 0x20 input frame -> full mapped snapshot */
    {
        u8 frame[64];
        u8 in_payload[14] = { 0 };
        in_payload[0] = 0x10; in_payload[1] = 0x01;  /* buttons: A(bit4) + DPAD_UP(bit8) */
        in_payload[2] = 0x00; in_payload[3] = 0x02;  /* LT = 512 */
        in_payload[4] = 0x00; in_payload[5] = 0x03;  /* RT = 768 */
        in_payload[6] = 0x00; in_payload[7] = 0x01;  /* lx = 256  */
        in_payload[8] = 0x00; in_payload[9] = 0xff;  /* ly = -256 */
        in_payload[10] = 0x00; in_payload[11] = 0x02;/* rx = 512  */
        in_payload[12] = 0x00; in_payload[13] = 0xfe;/* ry = -512 */
        int flen = gdr_gip_frame(frame, GIP_CMD_INPUT, 0x00, 3, in_payload, 14);
        gdr_gip_rx(&m, frame, flen);
    }
    CHECK(m.snapshot_valid == 1 && m.input_reports == 1,
          "wired: valid 0x20 decodes WITHOUT announce/identify (snapshot valid)");
    CHECK(m.snap.analog[0] == 0xff, "wired: A pressed -> analog A=255");
    CHECK(m.snap.analog[2] == 0x00 && m.snap.analog[3] == 0x00, "wired: X/Y released");
    m.snap.lx = m.snap.lx; /* (sticks checked below) */
    CHECK(m.snap.lx == 256 && m.snap.ly == -256 && m.snap.rx == 512 && m.snap.ry == -512,
          "wired: all four stick axes decoded");
    CHECK(m.snap.analog[6] == 127, "wired: LT 512 -> 127");
    CHECK(m.snap.analog[7] == 191, "wired: RT 768 -> 191");

    /* complete all-field state line (no silent truncation) */
    {
        size_t sn = gdr_format_state(sline, sizeof sline, &m.snap);
        CHECK(sn > 0 && strstr(sline, "A=255") && strstr(sline, "B=0")
              && strstr(sline, "X=0") && strstr(sline, "Y=0")
              && strstr(sline, "Black=0") && strstr(sline, "White=0")
              && strstr(sline, "lt=127") && strstr(sline, "rt=191"),
              "wired: state line logs A/B/X/Y/Black/White/LT/RT and sticks");
        (void)sn;
    }
}

/* ------------------------------------------------------------------ */
/* 4. Real config fixture + fail-closed + handoff interleaving         */
/* ------------------------------------------------------------------ */
/* Real 045e:0b12 config descriptor from research/usb/real-pad/config-descriptor-0b12.bin:
 * IF0 alt0 EP 0x02 OUT/0x82 IN interrupt 64B interval4; IF0 alt1 int2; audio EP3. */
static const u8 CFG_REAL_0B12[] = {
    0x09,0x02,0x77,0x00,0x03,0x01,0x00,0xa0,0xfa,
    0x09,0x04,0x00,0x00,0x02,0xff,0x47,0xd0,0x00,
    0x07,0x05,0x02,0x03,0x40,0x00,0x04,
    0x07,0x05,0x82,0x03,0x40,0x00,0x04,
    0x09,0x04,0x00,0x01,0x02,0xff,0x47,0xd0,0x00,
    0x07,0x05,0x02,0x03,0x40,0x00,0x04,
    0x07,0x05,0x82,0x03,0x40,0x00,0x02,
    0x09,0x04,0x01,0x00,0x00,0xff,0x47,0xd0,0x00,
    0x09,0x04,0x01,0x01,0x02,0xff,0x47,0xd0,0x00,
    0x07,0x05,0x03,0x01,0xe4,0x00,0x01,
    0x07,0x05,0x83,0x01,0x40,0x00,0x01,
    0x09,0x04,0x02,0x00,0x00,0xff,0x47,0xd0,0x00,
    0x09,0x04,0x02,0x01,0x02,0xff,0x47,0xd0,0x00,
    0x07,0x05,0x04,0x02,0x40,0x00,0x00,
    0x07,0x05,0x84,0x02,0x40,0x00,0x00
};
#define CFG_REAL_0B12_LEN ((int)sizeof CFG_REAL_0B12)

/* truncated interface descriptor (blen cuts off before endpoints) -> fail closed */
static const u8 CFG_SHORT_IFACE[] = {
    0x09,0x02,0x20,0x00,0x01,0x01,0x00,0xa0,0xfa,
    0x09,0x04,0x00,0x00,0x02,0xff,0x47       /* interface: blen says 9 but only 7 present */
};
#define CFG_SHORT_IFACE_LEN ((int)sizeof CFG_SHORT_IFACE)

static void test_cfg_and_handoff(void) {
    struct gdr_cfg_result r;

    gdr_cfg_parse(CFG_REAL_0B12, CFG_REAL_0B12_LEN, &r);
    CHECK(r.found == 1 && r.iface == 0, "real0b12: IF0 selected");
    CHECK(r.ep_in == 0x82 && r.ep_out == 0x02, "real0b12: EP 0x82 IN / 0x02 OUT");
    CHECK(r.mps_in == 64 && r.mps_out == 64, "real0b12: mps 64/64");
    CHECK(r.interval_in == 4 && r.interval_out == 4, "real0b12: alt0 interval 4 (not alt1 int2)");

    gdr_cfg_parse(CFG_SHORT_IFACE, CFG_SHORT_IFACE_LEN, &r);
    CHECK(r.found == 0, "short/malformed interface/endpoint fails closed (found=0)");

    /* oversized completion clamps to GDR_PKT_MAX (fail closed, no overflow) */
    {
        static struct gdr_attach_ctx ctx;
        static struct gdr_ring ring;
        u32 c, o;
        setup_ctx(&ctx, &ring);
        ctx.in_req_id = 1; ctx.in_flight = 1;
        ctx.in_urb.TransferLength = 100;      /* impossible length > 64       */
        ctx.in_urb.Hdr.Status = 0;
        gdr_in_complete(&ctx.in_urb, &ctx);
        gdr_ring_drain(&ring, &c, &o);
        CHECK(c == 1 && ring.slots[0].len == GDR_PKT_MAX,
              "oversized completion clamps to 64 (fail closed)");
    }

    /* head/tail handoff: producer/consumer interleaving never loses an event */
    {
        struct gdr_ring ring; struct gdr_evt ev, out; u32 popped = 0;
        gdr_ring_reset(&ring);
        /* fill to capacity */
        for (u32 i = 0; i < GDR_RING_CAP; i++) {
            memset(&ev, 0, sizeof ev); ev.kind = GDR_EVT_RX; ev.seq = i + 1;
            gdr_ring_push(&ring, &ev);
        }
        /* consume half */
        for (u32 i = 0; i < GDR_RING_CAP / 2; i++) {
            if (gdr_ring_pop(&ring, &out)) popped++;
        }
        /* producer keeps pushing while consumer is mid-drain: fills the freed
         * half again, wrapping head past GDR_RING_CAP modulo */
        for (u32 i = 0; i < GDR_RING_CAP / 2; i++) {
            memset(&ev, 0, sizeof ev); ev.kind = GDR_EVT_TXDONE; ev.seq = 1000 + i;
            gdr_ring_push(&ring, &ev);
        }
        /* drain the rest (undrained half + newly pushed half) */
        u32 seq_last = 0, in_order = 1, total = 0; u32 ovf;
        while (gdr_ring_pop(&ring, &out)) {
            total++;
            if (out.seq <= seq_last) in_order = 0;
            seq_last = out.seq;
        }
        ovf = ring.overflow;
        CHECK(popped == GDR_RING_CAP / 2, "handoff: half drained before interleave");
        CHECK(total == GDR_RING_CAP, "handoff: undrained + newly-pushed events all delivered (wrap)");
        CHECK(ovf == 0, "handoff: no overflow during interleaved wrap");
        CHECK(in_order, "handoff: event sequence stays monotonic");
    }
}

/* ------------------------------------------------------------------ */
/* 5. OUT URB field-by-field == pinned XID_fSendDeviceReport           */
/* ------------------------------------------------------------------ */
static void test_out_urb_xid_pin(void) {
    static struct gdr_attach_ctx ctx;
    static struct gdr_ring ring;
    static const u8 power_on[5] = { 0x05, 0x20, 0x01, 0x01, 0x00 };

    setup_ctx(&ctx, &ring);
    CHECK(gdr_tx_enqueue(&ctx, power_on, 5), "out: power-on enqueued");
    gdr_tx_submit_next(&ctx);

    /* XID_fSendDeviceReport interrupt-OUT (0x41) branch, xid-object.disasm:
     *   96  c6 00 28             mov [eax],0x28         URB.Length = 0x28
     *   99  c6 46 11 41          mov [esi+0x11],0x41    Function = 0x41
     *   a7  89 56 20             mov [esi+0x20],edx     EndpointHandle = device->[0x10]
     *   a0  89 4e 28             mov [esi+0x28],ecx     TransferBuffer = feedback buf
     *   aa  89 4e 24             mov [esi+0x24],ecx     TransferLength = report len
     *   ad  c6 46 2c 01          mov [esi+0x2c],0x1     FlagB0 = 1
     *   b1  88 5e 2d             mov [esi+0x2d],bl      FlagB1 = 0
     *   b4  88 5e 2e             mov [esi+0x2e],bl      Direction = 0 */
    CHECK(ctx.tx_urb.Hdr.Length == 0x28, "out: Hdr.Length == 0x28 (XID-pinned)");
    CHECK(ctx.tx_urb.Hdr.Function == 0x41, "out: Function == 0x41 (interrupt-OUT)");
    CHECK(ctx.tx_urb.EndpointHandle == ctx.out_handle, "out: EndpointHandle == separately opened OUT handle");
    CHECK(ctx.tx_urb.TransferBuffer == GDR_P2U32(ctx.tx_buf), "out: TransferBuffer == tx_buf (NOT rx_buf)");
    CHECK(ctx.tx_urb.TransferLength == 5, "out: TransferLength == frame length 5 (not mps)");
    CHECK(ctx.tx_urb.FlagB0 == 1 && ctx.tx_urb.FlagB1 == 0 && ctx.tx_urb.Direction == 0,
          "out: FlagB0=1 FlagB1=0 Direction=0 (pinned XID bytes)");
    CHECK(ctx.tx_urb.Hdr.CompleteProc == GDR_P2U32(gdr_tx_complete),
          "out: CompleteProc == gdr_tx_complete (distinct from IN callback)");
}

/* ------------------------------------------------------------------ */
/* 6. completion discriminator (CB) line                               */
/* ------------------------------------------------------------------ */
static void test_cb_discriminator(void) {
    static struct gdr_attach_ctx ctx;
    static struct gdr_ring ring;
    struct gdr_evt out; u32 o; char line[256]; size_t n; u32 i, kind;

    /* ---- IN callback with the IN URB -> "CB kind=in urb=in .. buf=rx" ---- */
    setup_ctx(&ctx, &ring);
    ctx.cb_log = 1;
    ctx.in_req_id = 1; ctx.in_flight = 1;
    ctx.in_urb.Hdr.Function = 0x41;
    ctx.in_urb.EndpointHandle = ctx.in_handle;            /* 0xAAAA             */
    ctx.in_urb.TransferBuffer = GDR_P2U32(ctx.rx_buf);
    ctx.in_urb.FlagB0 = 2; ctx.in_urb.FlagB1 = 1; ctx.in_urb.Direction = 0;
    ctx.in_urb.TransferLength = 8; ctx.in_urb.ByteCount = 64; ctx.in_urb.Hdr.Status = 0;
    for (i = 0; i < 8; i++) ctx.rx_buf[i] = 0x40 + i;
    gdr_in_complete(&ctx.in_urb, &ctx);

    kind = 0; o = gdr_ring_take_overflow(&ring);
    while (gdr_ring_pop(&ring, &out)) {
        if (out.kind == GDR_EVT_CB) { kind = out.kind; break; }
    }
    CHECK(kind == GDR_EVT_CB, "cb: IN completion emitted a CB event (cb_log=1)");
    n = gdr_format_event(line, sizeof line, &out);
    CHECK(strstr(line, "CB kind=in") && strstr(line, "urb=in") && strstr(line, "buf=rx"),
          "cb: IN -> kind=in urb=in buf=rx");
    CHECK(strstr(line, "l14=8") && strstr(line, "l20=64"), "cb: IN -> l14=8 l20=64 (mapped stays 64)");
    CHECK(strstr(line, "flags=2,1,0"), "cb: IN -> flags=2,1,0");
    (void)n;

    /* ---- OUT callback with the OUT URB -> "CB kind=tx urb=tx .. buf=tx" --- */
    setup_ctx(&ctx, &ring);
    ctx.cb_log = 1;
    {
        static const u8 power_on[5] = { 0x05, 0x20, 0x01, 0x01, 0x00 };
        gdr_tx_enqueue(&ctx, power_on, 5);
        gdr_tx_submit_next(&ctx);                    /* builds tx_urb, submits  */
        ctx.tx_urb.Hdr.Status = 0; ctx.tx_urb.TransferLength = 5; ctx.tx_urb.ByteCount = 5;
        gdr_tx_complete(&ctx.tx_urb, &ctx);          /* real OUT completion     */
    }
    kind = 0; gdr_ring_take_overflow(&ring);
    while (gdr_ring_pop(&ring, &out)) {
        if (out.kind == GDR_EVT_CB) { kind = out.kind; break; }
    }
    CHECK(kind == GDR_EVT_CB, "cb: OUT completion emitted a CB event (cb_log=1)");
    n = gdr_format_event(line, sizeof line, &out);
    CHECK(strstr(line, "CB kind=tx") && strstr(line, "urb=tx") && strstr(line, "buf=tx"),
          "cb: OUT -> kind=tx urb=tx buf=tx");
    CHECK(strstr(line, "flags=1,0,0"), "cb: OUT -> flags=1,0,0");
}

int main(void) {
    printf("AmpJack-OG worker17 corrected-transport regressions (gipdrive.h)\n");
    test_in_complete_fields();
    test_submit_correlation();
    test_qualified_wired();
    test_cfg_and_handoff();
    test_out_urb_xid_pin();
    test_cb_discriminator();
    if (g_fail == 0) { printf("RESULT: ALL CHECKS PASSED\n"); return 0; }
    printf("RESULT: %d CHECK(S) FAILED\n", g_fail);
    return 1;
}
