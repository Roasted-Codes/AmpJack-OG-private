/*
 * test_attach.c — host tests for the worker-14 completion-driven Attach
 * (gipdrive.h section 5). Exercises:
 *   1. gdr_urb_control byte layout (setup packet @+0x28, 0x30 long)
 *   2. gdr_build_s_init (S-init frame byte-exact)
 *   3. gdr_cfg_parse on a real-looking 3-interface GIP config descriptor +
 *      negative (no 0xFF interface)
 *   4. the S0..S5 completion chain, driven by a fake SubmitRequest that
 *      RECORDS each URB and lets the harness complete it LATER:
 *        - URB byte layouts per step (fn/len/setup/endpoint/mps)
 *        - GET_DESCRIPTOR(9) -> wTotalLength -> GET_DESCRIPTOR(full) ->
 *          SET_CONFIGURATION -> OPEN IN -> OPEN OUT -> IN URB + handshake
 *        - handshake OUT frame order (power-on, S-init, LED), one in flight
 *   5. negatives: STALL in S1 (STEPFAIL), bogus wTotalLength > 255 (clamped),
 *      no 0xFF interface (CFGFAIL, no further submits)
 *
 * Build & run (see run_tests.sh):
 *   cc -std=c11 -Wall -Wextra -I ../../gipdriver/src test_attach.c -o test_attach
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

/* ---- 1. control URB layout ---------------------------------------------- */
_Static_assert(offsetof(gdr_urb_control, EndpointHandle) == 0x10, "ctrl EndpointHandle @+0x10");
_Static_assert(offsetof(gdr_urb_control, TransferBuffer) == 0x18, "ctrl TransferBuffer @+0x18");
_Static_assert(offsetof(gdr_urb_control, TransferStatus) == 0x24, "ctrl TransferStatus @+0x24");
_Static_assert(offsetof(gdr_urb_control, SetupPacket) == 0x28, "ctrl SetupPacket @+0x28");
_Static_assert(sizeof(gdr_urb_control) >= 0x30, "ctrl URB >= 0x30 (48B)");

/* ---- 2. S-init frame ---------------------------------------------------- */
static void test_s_init(void) {
    u8 buf[64]; int n = gdr_build_s_init(buf, 0x07);
    const u8 expect[19] = { 0x05, 0x20, 0x07, 0x0f,
                            0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                            0x55, 0x53, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };
    CHECK(n == 19 && memcmp(buf, expect, 19) == 0,
          "S-init frame byte-exact (05 20 ss 0f 06 .. 55 53)");
}

/* ---- 3. config parsing -------------------------------------------------- */
/* 3-interface GIP config (worker01/12 lsusb): IF0 FF/47/D0, EP 0x01 OUT + 0x81
 * IN interrupt 64B int4; IF1 audio (isoc 0x02/0x82); IF2 chatpad. */
static const u8 CFG3[] = {
    9, 2, 73, 0,  3, 1, 0, 0x80, 250,          /* config: 3 ifaces, cfgval 1 */
    9, 4, 0, 0, 2, 0xFF, 0x47, 0xD0, 0,         /* IF0 data                   */
    7, 5, 0x01, 0x03, 0x40, 0x00, 4,            /* EP 0x01 OUT intr 64 int4   */
    7, 5, 0x81, 0x03, 0x40, 0x00, 4,            /* EP 0x81 IN  intr 64 int4   */
    9, 4, 1, 0, 0, 0x01, 0x01, 0x00, 0,         /* IF1 audio (alt0)           */
    9, 4, 1, 1, 2, 0x01, 0x02, 0x00, 0,         /* IF1 audio (alt1)           */
    7, 5, 0x02, 0x01, 0xE4, 0x00, 1,            /* EP 0x02 OUT isoc 228B       */
    7, 5, 0x82, 0x01, 0xE4, 0x00, 1,            /* EP 0x82 IN  isoc 228B       */
    9, 4, 2, 0, 0, 0x03, 0x00, 0x00, 0,         /* IF2 chatpad                */
};
#define CFG3_LEN ((int)sizeof CFG3)

/* same layout, but IF0 is HID (no 0xFF interface) */
static const u8 CFG_NOFF[] = {
    9, 2, 73, 0,  3, 1, 0, 0x80, 250,
    9, 4, 0, 0, 2, 0x03, 0x00, 0x00, 0,         /* IF0 HID (not 0xFF)         */
    7, 5, 0x01, 0x03, 0x40, 0x00, 4,
    7, 5, 0x81, 0x03, 0x40, 0x00, 4,
    9, 4, 1, 0, 0, 0x01, 0x01, 0x00, 0,
    9, 4, 1, 1, 2, 0x01, 0x02, 0x00, 0,
    7, 5, 0x02, 0x01, 0xE4, 0x00, 1,
    7, 5, 0x82, 0x01, 0xE4, 0x00, 1,
    9, 4, 2, 0, 0, 0x03, 0x00, 0x00, 0,
};
#define CFG_NOFF_LEN ((int)sizeof CFG_NOFF)

/* REAL descriptor read from the owner's pad on this PC (sysfs, 045e:0b12 Series S|X,
 * research/usb/real-pad/config-descriptor-0b12.bin). Every interface is FF/47/D0;
 * IF0 alt0 has EP 0x02 OUT / 0x82 IN interrupt 64 int4 (NOT 0x01/0x81); IF0 alt1
 * same addresses int 2; IF1 alt1 isoc 0x03/0x83; IF2 alt1 bulk 0x04/0x84. */
static const u8 CFG_REAL_0B12[] = { 0x09, 0x02, 0x77, 0x00, 0x03, 0x01, 0x00, 0xa0, 0xfa, 0x09, 0x04, 0x00, 0x00, 0x02, 0xff, 0x47, 0xd0, 0x00, 0x07, 0x05, 0x02, 0x03, 0x40, 0x00, 0x04, 0x07, 0x05, 0x82, 0x03, 0x40, 0x00, 0x04, 0x09, 0x04, 0x00, 0x01, 0x02, 0xff, 0x47, 0xd0, 0x00, 0x07, 0x05, 0x02, 0x03, 0x40, 0x00, 0x04, 0x07, 0x05, 0x82, 0x03, 0x40, 0x00, 0x02, 0x09, 0x04, 0x01, 0x00, 0x00, 0xff, 0x47, 0xd0, 0x00, 0x09, 0x04, 0x01, 0x01, 0x02, 0xff, 0x47, 0xd0, 0x00, 0x07, 0x05, 0x03, 0x01, 0xe4, 0x00, 0x01, 0x07, 0x05, 0x83, 0x01, 0x40, 0x00, 0x01, 0x09, 0x04, 0x02, 0x00, 0x00, 0xff, 0x47, 0xd0, 0x00, 0x09, 0x04, 0x02, 0x01, 0x02, 0xff, 0x47, 0xd0, 0x00, 0x07, 0x05, 0x04, 0x02, 0x40, 0x00, 0x00, 0x07, 0x05, 0x84, 0x02, 0x40, 0x00, 0x00 };
#define CFG_REAL_0B12_LEN ((int)sizeof CFG_REAL_0B12)

static void test_cfg_parse(void) {
    struct gdr_cfg_result r;
    gdr_cfg_parse(CFG3, CFG3_LEN, &r);
    CHECK(r.found == 1, "cfg parse: 0xFF interface found");
    CHECK(r.iface == 0,        "cfg parse: GIP interface 0");
    CHECK(r.ep_in == 0x81 && r.ep_out == 0x01, "cfg parse: EP 0x81 IN / 0x01 OUT");
    CHECK(r.mps_in == 64 && r.mps_out == 64,   "cfg parse: mps 64/64");
    CHECK(r.interval_in == 4 && r.interval_out == 4, "cfg parse: bInterval 4/4");
    CHECK(r.cfg_value == 1,    "cfg parse: bConfigurationValue 1");

    gdr_cfg_parse(CFG_NOFF, CFG_NOFF_LEN, &r);
    CHECK(r.found == 0,        "cfg parse: no 0xFF interface => found=0");

    gdr_cfg_parse(CFG_REAL_0B12, CFG_REAL_0B12_LEN, &r);
    CHECK(r.found == 1 && r.iface == 0, "real 0b12: IF0 selected (all ifaces are FF/47/D0)");
    CHECK(r.ep_in == 0x82 && r.ep_out == 0x02, "real 0b12: EP 0x82 IN / 0x02 OUT (not 0x81/0x01)");
    CHECK(r.mps_in == 64 && r.mps_out == 64 && r.interval_in == 4 && r.interval_out == 4, "real 0b12: 64B int4 (alt0, not alt1 int2)");
    CHECK(r.cfg_value == 1, "real 0b12: bConfigurationValue 1");
}

/* ---- 4. completion-chain simulation (fake SubmitRequest) ---------------- */

/* One recorded submission. */
#define SIM_MAX 64
struct sim_urb {
    u8  function;
    u8  length;
    u8  setup[8];
    u8  ep_address;       /* OPEN_ENDPOINT +0x15 */
    u8  transfer_type;    /* OPEN_ENDPOINT +0x16 */
    u8  interval;
    u16 max_packet;
    u32 endpoint_handle;  /* +0x10 at submit time */
    u32 transfer_length;  /* +0x14 */
    u32 transfer_buffer;  /* +0x18 */
    u32 complete_context;
    long status;          /* the harness later writes this  */
};
static struct sim_urb g_sim[SIM_MAX];
static int            g_sim_n;
static const u8      *g_sim_cfg;      /* descriptor the fake device returns   */
static int            g_sim_cfg_len;
static u32            g_fake_handle;  /* monotonic pipe handles               */

static long fake_submit(void *device, void *urb) {
    struct sim_urb *r = &g_sim[g_sim_n++];
    gdr_urb_header *h = (gdr_urb_header*)urb;
    memset(r, 0, sizeof *r);
    r->function = h->Function; r->length = h->Length; r->status = 0;
    r->complete_context = h->CompleteContext;
    if (h->Function == 0x40) {
        gdr_urb_control *c = (gdr_urb_control*)urb;
        memcpy(r->setup, c->SetupPacket, 8);
        r->endpoint_handle = c->EndpointHandle;
        r->transfer_length = c->TransferLength;
        r->transfer_buffer = c->TransferBuffer;
    } else if (h->Function == 0x02 || h->Function == 0x82) {
        gdr_urb_open *o = (gdr_urb_open*)urb;
        r->ep_address    = o->EndpointAddress;
        r->transfer_type = o->TransferType;
        r->interval      = o->Interval;
        r->max_packet    = o->MaxPacketSize;
        r->endpoint_handle = o->EndpointHandle;
    } else if (h->Function == 0x41) {
        gdr_urb_transfer *t = (gdr_urb_transfer*)urb;
        r->endpoint_handle = t->EndpointHandle;
        r->transfer_length = t->TransferLength;
        r->transfer_buffer = t->TransferBuffer;
    }
    return 0;   /* recorded, NOT completed yet */
}

/* The chain is deterministic, so the harness dispatches the KNOWN next step
 * (the Xbox URB stores a 32-bit CompleteProc, which truncates 64-bit host
 * pointers — hence the harness keeps the mapping rather than round-tripping). */
static void complete_open0(struct gdr_attach_ctx *ctx, long status) {
    ctx->open_urb.Hdr.Status        = (u32)status;
    ctx->open_urb.EndpointHandle    = ++g_fake_handle;
    gdr_step_s0c(&ctx->open_urb, ctx);
}
static void complete_ctrl1(struct gdr_attach_ctx *ctx, long status, const u8 *fill, int fill_len) {
    gdr_urb_control *c = &ctx->ctrl_urb;
    c->Hdr.Status = (u32)status;
    if (status >= 0 && fill && fill_len >= 9)
        memcpy(ctx->cfg_stage, fill, 9);
    (void)fill_len;
    gdr_step_s1(c, ctx);
}
static void complete_ctrl2(struct gdr_attach_ctx *ctx, long status) {
    gdr_urb_control *c = &ctx->ctrl_urb;
    c->Hdr.Status = (u32)status;
    if (status >= 0 && g_sim_cfg) {
        int n = (int)c->TransferLength;
        if (n > g_sim_cfg_len) n = g_sim_cfg_len;
        memcpy(ctx->cfg_buf, g_sim_cfg, (size_t)n);
    }
    gdr_step_s2(c, ctx);
}
static void complete_ctrl3(struct gdr_attach_ctx *ctx, long status) {
    gdr_urb_control *c = &ctx->ctrl_urb;
    c->Hdr.Status = (u32)status;
    gdr_step_s3(c, ctx);
}
static void complete_open4(struct gdr_attach_ctx *ctx, long status) {
    ctx->open_urb.Hdr.Status     = (u32)status;
    ctx->open_urb.EndpointHandle = ++g_fake_handle;
    gdr_step_s4(&ctx->open_urb, ctx);
}
static void complete_open5(struct gdr_attach_ctx *ctx, long status) {
    ctx->open_urb.Hdr.Status     = (u32)status;
    ctx->open_urb.EndpointHandle = ++g_fake_handle;
    gdr_step_s5(&ctx->open_urb, ctx);
}

static void sim_reset(void) {
    g_sim_n = 0; g_fake_handle = 0;
    memset(g_sim, 0, sizeof g_sim);
}

static void test_chain_happy(void) {
    static struct gdr_attach_ctx ctx;
    static struct gdr_ring ring;
    g_sim_cfg = CFG3; g_sim_cfg_len = CFG3_LEN;
    sim_reset();
    memset(&ctx, 0, sizeof ctx);
    gdr_ring_reset(&ring);

    gdr_attach_begin(&ctx, (void*)0x1234, fake_submit, &ring);
    CHECK(g_sim_n == 1 && g_sim[0].function == 0x82 && g_sim[0].length == 0x20,
          "S0: first URB is OPEN DEFAULT CONTROL (fn 0x82, len 0x20)");

    complete_open0(&ctx, 0);   /* control pipe opens -> GET_DESCRIPTOR(9) */
    CHECK(g_sim_n == 2 && g_sim[1].function == 0x40 && g_sim[1].length == 0x30,
          "S0c: submits 0x40 GET_DESCRIPTOR(9) control URB (len 0x30)");
    CHECK(g_sim[1].setup[0]==0x80 && g_sim[1].setup[1]==0x06 && g_sim[1].setup[3]==0x02
          && g_sim[1].setup[6]==0x09 && g_sim[1].setup[7]==0x00,
          "S0c: setup 80 06 00 02 00 00 09 00");

    /* S1: the fake device fills the 9-byte stage with wTotalLength */
    {
        u8 stage[9] = { 9, 2, 73, 0, 0, 1, 0, 0x80, 250 };
        complete_ctrl1(&ctx, 0, stage, 9);
    }
    CHECK(g_sim_n == 3 && g_sim[2].function == 0x40,
          "S1: submits GET_DESCRIPTOR(full) control URB");
    CHECK(g_sim[2].setup[6] == 73 && g_sim[2].setup[7] == 0 && g_sim[2].transfer_length == 73,
          "S1: wLength = wTotalLength (73)");

    complete_ctrl2(&ctx, 0);    /* config parsed -> SET_CONFIGURATION */
    CHECK(ctx.failed == 0 && ctx.cfg_value == 1 && ctx.ep_in == 0x81 && ctx.ep_out == 0x01,
          "S2: config parsed into ctx (cfgval 1, EP 0x81/0x01)");
    CHECK(g_sim_n == 4 && g_sim[3].function == 0x40
          && g_sim[3].setup[0]==0x00 && g_sim[3].setup[1]==0x09
          && g_sim[3].setup[2]==0x01 && g_sim[3].setup[3]==0x00,
          "S2: SET_CONFIGURATION setup 00 09 01 00 00 00 00 00");

    complete_ctrl3(&ctx, 0);    /* SET_CONFIG done -> OPEN IN */
    CHECK(g_sim_n == 5 && g_sim[4].function == 0x02 && g_sim[4].length == 0x20
          && g_sim[4].ep_address == 0x81 && g_sim[4].transfer_type == 3
          && g_sim[4].interval == 4 && g_sim[4].max_packet == 64,
          "S3: OPEN_ENDPOINT IN (0x81, intr, int4, mps64)");

    complete_open4(&ctx, 0);    /* IN open -> OPEN OUT */
    CHECK(ctx.in_handle != 0, "S4: IN endpoint handle recorded");
    CHECK(g_sim_n == 6 && g_sim[5].function == 0x02 && g_sim[5].ep_address == 0x01
          && g_sim[5].transfer_type == 3 && g_sim[5].interval == 4 && g_sim[5].max_packet == 64,
          "S4: OPEN_ENDPOINT OUT (0x01, intr, int4, mps64)");

    complete_open5(&ctx, 0);    /* OUT open -> persistent IN URB only */
    CHECK(ctx.out_handle != 0 && ctx.state == 6 && ctx.failed == 0,
          "S5: OUT handle recorded, state=live");
    CHECK(g_sim_n == 7, "S5: persistent IN URB posted (1 more URB; GIP init is state-machine driven)");
    CHECK(g_sim[6].function == 0x41 && g_sim[6].endpoint_handle == ctx.in_handle
          && g_sim[6].transfer_length == 64,
          "S5: interrupt IN URB (fn 0x41, in_handle, len 64)");
}

/* ---- 5. negatives ------------------------------------------------------- */
static void test_stall_s1(void) {
    static struct gdr_attach_ctx ctx;
    static struct gdr_ring ring;
    g_sim_cfg = CFG3; g_sim_cfg_len = CFG3_LEN;
    sim_reset();
    memset(&ctx, 0, sizeof ctx);
    gdr_ring_reset(&ring);

    gdr_attach_begin(&ctx, (void*)0x1234, fake_submit, &ring);
    complete_open0(&ctx, 0);
    complete_ctrl1(&ctx, 0xC0000004L, 0, 0);  /* STALL on GET_DESCRIPTOR(9) */
    CHECK(ctx.failed == 1 && ctx.fail_step == 1 && ctx.fail_status == 0xC0000004u,
          "STALL in S1 => STEPFAIL step=1 (no further submit)");
    /* the failed S1 must NOT have submitted GET_DESCRIPTOR(full) */
    int has_full = 0;
    for (int i = 0; i < g_sim_n; i++) if (g_sim[i].function == 0x40 && g_sim[i].setup[1]==0x06 && g_sim[i].setup[6]!=9) has_full = 1;
    CHECK(!has_full, "STALL: GET_DESCRIPTOR(full) never submitted");
}

static void test_bogus_wtotal(void) {
    static struct gdr_attach_ctx ctx;
    static struct gdr_ring ring;
    sim_reset();
    memset(&ctx, 0, sizeof ctx);
    gdr_ring_reset(&ring);

    gdr_attach_begin(&ctx, (void*)0x1234, fake_submit, &ring);
    complete_open0(&ctx, 0);
    {
        u8 stage[9] = { 9, 2, 0xFF, 0xFF, 0, 1, 0, 0x80, 250 };  /* wTotalLength=0xFFFF */
        complete_ctrl1(&ctx, 0, stage, 9);
    }
    CHECK(g_sim_n == 3 && g_sim[2].setup[6] == 0xFF && g_sim[2].setup[7] == 0x00
          && g_sim[2].transfer_length == 255 && ctx.cfg_len == 255,
          "bogus wTotalLength (0xFFFF) clamped to 255 (no buffer overflow)");
    {
        u8 stage[9] = { 9, 2, 4, 0, 0, 1, 0, 0x80, 250 };  /* wTotalLength=4 (<9) */
        /* fresh ctx to re-run S1 clamp min */
        memset(&ctx, 0, sizeof ctx);
        gdr_ring_reset(&ring); sim_reset();
        gdr_attach_begin(&ctx, (void*)0x1234, fake_submit, &ring);
        complete_open0(&ctx, 0);
        complete_ctrl1(&ctx, 0, stage, 9);
        CHECK(g_sim[2].transfer_length == 9,
              "wTotalLength < 9 clamped up to 9 (always fetch a full header)");
    }
}

static void test_cfgfail(void) {
    static struct gdr_attach_ctx ctx;
    static struct gdr_ring ring;
    g_sim_cfg = CFG_NOFF; g_sim_cfg_len = CFG_NOFF_LEN;
    sim_reset();
    memset(&ctx, 0, sizeof ctx);
    gdr_ring_reset(&ring);

    gdr_attach_begin(&ctx, (void*)0x1234, fake_submit, &ring);
    complete_open0(&ctx, 0);
    {
        u8 stage[9] = { 9, 2, 73, 0, 0, 1, 0, 0x80, 250 };
        complete_ctrl1(&ctx, 0, stage, 9);
    }
    complete_ctrl2(&ctx, 0);
    CHECK(ctx.failed == 2, "CFGFAIL: no 0xFF interface => failed=2 (claimed-idle)");
    int setcfg = 0, opened = 0;
    for (int i = 0; i < g_sim_n; i++) {
        if (g_sim[i].function == 0x40 && g_sim[i].setup[1] == 0x09) setcfg = 1;
        if (g_sim[i].function == 0x02) opened = 1;
    }
    CHECK(!setcfg && !opened, "CFGFAIL: SET_CONFIGURATION + endpoints never submitted");
}

int main(void) {
    printf("AmpJack-OG worker14 Attach host tests (gipdrive.h section 5)\n");
    test_s_init();
    test_cfg_parse();
    test_chain_happy();
    test_stall_s1();
    test_bogus_wtotal();
    test_cfgfail();
    if (g_fail == 0) { printf("RESULT: ALL CHECKS PASSED\n"); return 0; }
    printf("RESULT: %d CHECK(S) FAILED\n", g_fail);
    return 1;
}
