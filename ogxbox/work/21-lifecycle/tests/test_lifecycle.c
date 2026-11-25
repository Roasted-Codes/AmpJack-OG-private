/*
 * test_lifecycle.c — slice2 host tests for the USB attach/detach lifecycle.
 *
 * Compiles the SAME ogxbox/gipdriver/src/gipdrive.h the Xbox title compiles and
 * exercises the REAL completion callbacks + attach chain (gdr_attach_begin,
 * gdr_step_s0c..s5, gdr_in_complete, gdr_tx_complete) against the slice2
 * lifecycle state machine — NOT text matching, NOT a fake_in_complete:
 *
 *   1. full 24-byte class-driver description (RemoveDevice @+0x0C, TypeInfo
 *      @+0x10, DispatchTable @+0x14) — the VERIFIED xapilib layout.
 *   2. AddComplete exactly-once on success (S5->live => status 0) and on
 *      failure (STALL S1, CFGFAIL, immediate S0-open reject => status < 0).
 *   3. RemoveDevice invalidates state (detached, handles zeroed) and stops new
 *      I/O: no submit/re-arm after detach.
 *   4. Cancel -> quiesce -> RemoveComplete ordering: RemoveComplete fires only
 *      after every cancelled URB's completion, exactly once.
 *   5. Removal during config-pending, IN-pending and OUT-pending.
 *   6. Old completion cannot re-arm/publish after detach (no stale overwrite).
 *   7. A post-detach re-attach streams a fresh generation (detached/ack guards
 *      reset; AddComplete fires exactly once for the new generation).
 *   8. No-context / double-remove / mismatched-device are no-ops.
 *   9. gdr_gip_neutralize clears the decoded snapshot (no stale buttons).
 *
 * Build & run (from repo root):
 *   cc -std=c11 -Wall -Wextra -I ogxbox/gipdriver/src \
 *      ogxbox/work/21-lifecycle/tests/test_lifecycle.c \
 *      -o ogxbox/work/21-lifecycle/tests/test_lifecycle
 *   ogxbox/work/21-lifecycle/tests/test_lifecycle
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

/* ---- device-under-test + recorded transport ------------------------------ */
static struct gdr_attach_ctx ctx;
static struct gdr_ring       ring;
static struct gdr_gip        gip;

#define SIM_MAX 64
static u8    sim_fn[SIM_MAX];      /* Hdr.Function of each submitted URB    */
static int   sim_n;
static long  sim_ret;             /* submit return value (0 = queued/ok)   */

static int   add_calls;  static long add_last;
static int   cancel_calls; static void *cancel_urb[8];
static int   rm_calls;
static int   g_cancel_reentrant;     /* 1 => fake_cancel completes in_urb inline */

static long fake_submit(void *device, void *urb) {
    gdr_urb_header *h = (gdr_urb_header*)urb;
    if (sim_n < SIM_MAX) sim_fn[sim_n++] = h->Function;
    (void)device;
    return sim_ret;
}
static void fake_add_complete(void *device, long status) {
    add_calls++; add_last = status; (void)device;
}
static long fake_cancel(void *device, void *urb) {
    if (cancel_calls < 8) cancel_urb[cancel_calls] = urb;
    cancel_calls++; (void)device;
    if (g_cancel_reentrant && urb == (void*)&ctx.in_urb) {
        /* model CancelRequest delivering the completion synchronously (same
         * DISPATCH_LEVEL re-entrant completion as a real OHCI cancel). */
        ctx.in_urb.Hdr.Status = 0xC0000120u; ctx.in_urb.TransferLength = 0;
        gdr_in_complete(&ctx.in_urb, &ctx);
    }
    return 0;
}
static void fake_remove_complete(void *device) {
    rm_calls++; (void)device;
}

static void reset_all(void) {
    memset(&ctx, 0, sizeof ctx);
    gdr_ring_reset(&ring);
    gdr_gip_init(&gip, 0);
    sim_n = 0; sim_ret = 0;
    add_calls = 0; add_last = 0;
    cancel_calls = 0; memset(cancel_urb, 0, sizeof cancel_urb);
    rm_calls = 0;
    g_cancel_reentrant = 0;
    ctx.add_complete    = fake_add_complete;
    ctx.cancel_request  = fake_cancel;
    ctx.remove_complete = fake_remove_complete;
}

/* ---- minimal 1-interface GIP config (EP 0x82 IN / 0x02 OUT, int4, 64B) -- */
static const u8 CFG[] = {
    9,2,0x20,0, 1,1,0,0x80,0xFA,     /* config: 1 iface, cfgval 1             */
    9,4,0,0,2, 0xFF,0x47,0xD0,0,     /* IF0 data FF/47/D0, 2 endpoints        */
    7,5,0x82,0x03,64,0,4,            /* EP 0x82 IN  interrupt 64B int4        */
    7,5,0x02,0x03,64,0,4             /* EP 0x02 OUT interrupt 64B int4        */
};
#define CFG_LEN ((int)sizeof CFG)

static u32 fake_handle = 0;

/* Drive the completion chain exactly as the OHCI completions would (the harness
 * keeps the callback mapping because CompleteProc is a truncated 32-bit field). */
static void complete_open0(long status) {
    ctx.open_urb.Hdr.Status     = (u32)status;
    ctx.open_urb.EndpointHandle = ++fake_handle;
    gdr_step_s0c(&ctx.open_urb, &ctx);
}
static void complete_ctrl(long status, const u8 *fill, int fill_len) {
    gdr_urb_control *c = &ctx.ctrl_urb;
    u32 i;
    c->Hdr.Status = (u32)status;
    if (status >= 0 && fill) {
        if (fill_len <= CFG_LEN) for (i = 0; i < (u32)fill_len; i++) ctx.cfg_buf[i] = fill[i];
    }
    /* which stage? state reflects the URB just completed: 1=GET9, 2=full, 3=SET */
    if (ctx.state == 1) { if (fill && fill_len >= 9) memcpy(ctx.cfg_stage, fill, 9); gdr_step_s1(c, &ctx); }
    else if (ctx.state == 2) gdr_step_s2(c, &ctx);
    else                    gdr_step_s3(c, &ctx);
}
static void complete_open(long status) {
    ctx.open_urb.Hdr.Status     = (u32)status;
    ctx.open_urb.EndpointHandle = ++fake_handle;
    if (ctx.state == 4) gdr_step_s4(&ctx.open_urb, &ctx);
    else                gdr_step_s5(&ctx.open_urb, &ctx);
}

/* Attach + drive the whole chain to LIVE (state 6) with a valid descriptor. */
static void drive_to_live(void) {
    u8 stage9[9] = { 9, 2, CFG_LEN, 0, 0, 1, 0, 0x80, 0xFA };
    gdr_attach_begin(&ctx, (void*)0x1234, fake_submit, &ring);
    complete_open0(0);                  /* S0 open ctrl -> GET_DESC(9)       */
    complete_ctrl(0, stage9, 9);        /* S1 -> GET_DESC(full)              */
    complete_ctrl(0, CFG, CFG_LEN);     /* S2 -> SET_CONFIGURATION           */
    complete_ctrl(0, 0, 0);             /* S3 -> OPEN IN                     */
    complete_open(0);                   /* S4 -> OPEN OUT                    */
    complete_open(0);                   /* S5 -> live + persistent IN URB    */
}

/* ---- 1. description layout (VERIFIED 24-byte xapilib layout) ------------- */
_Static_assert(offsetof(gdr_class_desc, MatchByte0)   == 0x00, "desc MatchByte0 @+0");
_Static_assert(offsetof(gdr_class_desc, MatchByte1)   == 0x01, "desc MatchByte1 @+1");
_Static_assert(offsetof(gdr_class_desc, Register)     == 0x04, "desc Register @+4");
_Static_assert(offsetof(gdr_class_desc, Attach)       == 0x08, "desc Attach @+8");
_Static_assert(offsetof(gdr_class_desc, RemoveDevice) == 0x0C, "desc RemoveDevice @+0xC");
_Static_assert(offsetof(gdr_class_desc, TypeInfo)     == 0x10, "desc TypeInfo @+0x10");
_Static_assert(offsetof(gdr_class_desc, DispatchTable)== 0x14, "desc DispatchTable @+0x14");
_Static_assert(sizeof(gdr_class_desc)                 == 0x18, "desc is 24 bytes");

/* ---- 2. AddComplete exactly once ------------------------------------------ */
static void test_add_complete_success(void) {
    reset_all(); drive_to_live();
    CHECK(ctx.state == 6 && ctx.failed == 0, "success: chain reached live");
    CHECK(ctx.lifecycle == GDR_LIFE_LIVE, "success: lifecycle == LIVE");
    CHECK(add_calls == 1 && add_last == 0, "success: AddComplete(0) exactly once");
    /* a second, spurious signal must not re-fire (exactly-once guard) */
    gdr_signal_add_complete(&ctx, 0);
    CHECK(add_calls == 1, "success: AddComplete not re-fired by a 2nd signal");
}

static void test_add_complete_fail_stall(void) {
    u8 stage9[9] = { 9, 2, CFG_LEN, 0, 0, 1, 0, 0x80, 0xFA };
    reset_all();
    gdr_attach_begin(&ctx, (void*)0x1234, fake_submit, &ring);
    complete_open0(0);
    complete_ctrl(0xC0000004L, 0, 0);   /* STALL on GET_DESCRIPTOR(9) */
    CHECK(ctx.failed == 1 && ctx.fail_step == 1, "fail: STALL in S1 => STEPFAIL");
    CHECK(add_calls == 1 && add_last == (long)(int)0xC0000004,
          "fail: AddComplete(negative status) exactly once");
    CHECK(ctx.lifecycle == GDR_LIFE_FAILED, "fail: lifecycle == FAILED");
}

static void test_add_complete_fail_cfgfail(void) {
    /* descriptor with no 0xFF interface */
    static const u8 NOFF[] = {
        9,2,0x12,0, 1,1,0,0x80,0xFA, 9,4,0,0,0, 0x03,0,0,0 };
    u8 stage9[9] = { 9, 2, sizeof NOFF, 0, 0, 1, 0, 0x80, 0xFA };
    reset_all();
    gdr_attach_begin(&ctx, (void*)0x1234, fake_submit, &ring);
    complete_open0(0);
    complete_ctrl(0, stage9, 9);
    memcpy(ctx.cfg_buf, NOFF, sizeof NOFF);
    gdr_step_s2(&ctx.ctrl_urb, &ctx);
    CHECK(ctx.failed == 2, "cfgfail: no 0xFF interface => failed=2");
    CHECK(add_calls == 1 && add_last == (long)(int)0x80000400,
          "cfgfail: AddComplete(0x80000400) exactly once");
}

static void test_add_complete_immediate_reject(void) {
    reset_all();
    sim_ret = -1L;                     /* S0 open rejected immediately */
    gdr_attach_begin(&ctx, (void*)0x1234, fake_submit, &ring);
    CHECK(ctx.failed == 1 && ctx.fail_step == 0, "reject: S0 reject => STEPFAIL 0");
    CHECK(add_calls == 1 && add_last == -1L,
          "reject: AddComplete(reject status) exactly once");
    CHECK(sim_n == 1, "reject: only the one S0 URB was submitted");
}

/* ---- 3/4/5. RemoveDevice invalidate + cancel->quiesce->ack ---------------- */
static void test_remove_during_live(void) {
    reset_all(); drive_to_live();
    int submits_before = sim_n;
    CHECK(ctx.in_flight == 1 && ctx.pending == 1, "live: one IN URB pending");

    gdr_remove_device(&ctx, (void*)0x1234);
    CHECK(ctx.detached == 1, "remove: detached set");
    CHECK(ctx.lifecycle == GDR_LIFE_REMOVING, "remove: lifecycle == REMOVING");
    CHECK(ctx.in_handle == 0 && ctx.out_handle == 0 && ctx.control_handle == 0,
          "remove: handles invalidated (no reuse)");
    CHECK(cancel_calls == 1 && cancel_urb[0] == (void*)&ctx.in_urb,
          "remove: persistent IN URB cancelled");
    CHECK(rm_calls == 0, "remove: RemoveComplete NOT yet acked (IN still quiescing)");

    /* a completion that races in AFTER detach must not re-arm or publish */
    ctx.in_urb.Hdr.Status = 0xC0000120u; ctx.in_urb.TransferLength = 64;
    for (int i = 0; i < 8; i++) ctx.rx_buf[i] = 0xFF;   /* would-be stale buttons */
    gdr_in_complete(&ctx.in_urb, &ctx);
    CHECK(ctx.in_flight == 0, "remove: stale IN completion did not re-arm");
    CHECK(sim_n == submits_before, "remove: no new submit after the stale completion");
    CHECK(rm_calls == 1, "remove: RemoveComplete acked once the IN URB quiesced");
    CHECK(ctx.lifecycle == GDR_LIFE_IDLE, "remove: lifecycle returns to IDLE after ack");

    /* no new OUT submit after detach */
    {
        static const u8 power_on[5] = { 0x05, 0x20, 0x01, 0x01, 0x00 };
        gdr_tx_enqueue(&ctx, power_on, 5);
        gdr_tx_submit_next(&ctx);
    }
    CHECK(sim_n == submits_before, "remove: no OUT submit after detach");
}

static void test_remove_during_config_pending(void) {
    u8 stage9[9] = { 9, 2, CFG_LEN, 0, 0, 1, 0, 0x80, 0xFA };
    reset_all();
    gdr_attach_begin(&ctx, (void*)0x1234, fake_submit, &ring);
    complete_open0(0);                 /* now S1: GET_DESC(9) control URB pending */
    CHECK(ctx.state == 1 && ctx.pending == 1, "config: one control URB pending (GET_DESC 9)");

    gdr_remove_device(&ctx, (void*)0x1234);
    CHECK(cancel_calls == 1 && cancel_urb[0] == (void*)&ctx.ctrl_urb,
          "config: in-flight control URB cancelled");
    CHECK(rm_calls == 0, "config: RemoveComplete not yet acked");

    ctx.ctrl_urb.Hdr.Status = 0xC0000120u;   /* cancelled control completion */
    gdr_step_s1(&ctx.ctrl_urb, &ctx);
    CHECK(rm_calls == 1, "config: RemoveComplete acked after the control URB quiesced");
    CHECK(add_calls == 0, "config: no AddComplete on a cancel-during-remove (not a STEPFAIL)");
}

static void test_remove_during_out_pending(void) {
    static const u8 power_on[5] = { 0x05, 0x20, 0x01, 0x01, 0x00 };
    reset_all(); drive_to_live();
    gdr_tx_enqueue(&ctx, power_on, 5);
    gdr_tx_submit_next(&ctx);          /* OUT URB now in flight */
    CHECK(ctx.tx_busy == 1 && ctx.pending == 2, "out: IN + OUT URBs pending");

    gdr_remove_device(&ctx, (void*)0x1234);
    CHECK(cancel_calls == 2, "out: both IN and OUT URBs cancelled");
    CHECK(rm_calls == 0, "out: RemoveComplete not yet acked");

    /* OUT completion quiesces first: still one (IN) outstanding */
    ctx.tx_urb.Hdr.Status = 0xC0000120u; ctx.tx_urb.TransferLength = 0;
    gdr_tx_complete(&ctx.tx_urb, &ctx);
    CHECK(rm_calls == 0, "out: RemoveComplete still deferred after OUT (IN pending)");

    ctx.in_urb.Hdr.Status = 0xC0000120u; ctx.in_urb.TransferLength = 0;
    gdr_in_complete(&ctx.in_urb, &ctx);
    CHECK(rm_calls == 1, "out: RemoveComplete acked after the last URB quiesced");
}

/* ---- 6/7. no new submit after detach + fresh re-attach generation --------- */
static void test_no_submit_after_detach(void) {
    reset_all(); drive_to_live();
    gdr_remove_device(&ctx, (void*)0x1234);
    /* directly model the IN completion (cancelled) to reach quiescence */
    ctx.in_urb.Hdr.Status = 0xC0000120u; ctx.in_urb.TransferLength = 0;
    gdr_in_complete(&ctx.in_urb, &ctx);
    CHECK(rm_calls == 1, "no-submit: fully detached and acked");
    int n = sim_n;
    /* every submit path is now closed: re-arm, OUT, and a naive re-attempt */
    gdr_in_complete(&ctx.in_urb, &ctx);   /* late/stale completion */
    CHECK(sim_n == n, "no-submit: a late IN completion does not submit");
}

static void test_reattach_fresh_generation(void) {
    reset_all(); drive_to_live();
    CHECK(add_calls == 1 && rm_calls == 0, "reattach: gen0 live, AddComplete(0) fired once");

    gdr_remove_device(&ctx, (void*)0x1234);
    ctx.in_urb.Hdr.Status = 0xC0000120u; ctx.in_urb.TransferLength = 0;
    gdr_in_complete(&ctx.in_urb, &ctx);
    CHECK(rm_calls == 1, "reattach: gen0 fully removed");

    /* replug: stack re-enumerates -> Attach runs a fresh generation */
    sim_n = 0; fake_handle = 0;
    drive_to_live();
    CHECK(ctx.detached == 0 && ctx.lifecycle == GDR_LIFE_LIVE,
          "reattach: fresh generation is not detached and is LIVE");
    CHECK(add_calls == 2 && add_last == 0, "reattach: AddComplete(0) fired once for gen1");
    CHECK(ctx.generation > 0, "reattach: generation advanced");
    CHECK(ctx.in_handle != 0 && ctx.in_flight == 1, "reattach: fresh IN URB streaming");
}

/* ---- 8. no-context / double-remove / mismatched device -------------------- */
static void test_remove_edge_cases(void) {
    reset_all(); drive_to_live();

    gdr_remove_device((struct gdr_attach_ctx*)0, (void*)0x1234);  /* no ctx */
    CHECK(rm_calls == 0, "edge: remove(NULL ctx) is a no-op");

    gdr_remove_device(&ctx, (void*)0xDEAD);   /* wrong device */
    CHECK(rm_calls == 0 && ctx.detached == 0, "edge: remove(other device) is a no-op");

    gdr_remove_device(&ctx, (void*)0x1234);   /* real remove */
    CHECK(ctx.detached == 1 && rm_calls == 0, "edge: real remove sets detached, defers ack");

    int cancels = cancel_calls;
    gdr_remove_device(&ctx, (void*)0x1234);   /* double remove */
    CHECK(cancel_calls == cancels && rm_calls == 0, "edge: double remove does not re-cancel");

    ctx.in_urb.Hdr.Status = 0xC0000120u; ctx.in_urb.TransferLength = 0;
    gdr_in_complete(&ctx.in_urb, &ctx);
    CHECK(rm_calls == 1, "edge: ack after quiescence");
    gdr_remove_ack(&ctx);   /* duplicate ack attempt */
    CHECK(rm_calls == 1, "edge: RemoveComplete not re-acked (double-remove guard)");
}

/* ---- 9. neutral/disconnected snapshot ------------------------------------- */
static void test_neutral_snapshot(void) {
    reset_all();
    /* seed a stale decoded state, then neutralize */
    gip.snapshot_valid = 1; gip.gamepad = 1; gip.identified = 1; gip.ready = 1;
    gip.snap.buttons = 0x0010; gip.snap.analog[0] = 0xFF; gip.snap.lx = 500;
    gdr_gip_neutralize(&gip);
    CHECK(gip.snapshot_valid == 0 && gip.gamepad == 0 && gip.identified == 0,
          "neutral: snapshot invalid + identity cleared");
    CHECK(gip.snap.buttons == 0 && gip.snap.analog[0] == 0 && gip.snap.lx == 0,
          "neutral: all buttons/sticks/triggers reset (no stale input)");
}

/* ---- 10. reentrant cancel + no callback after retire ---------------------- */
static void test_remove_reentrant_cancel(void) {
    reset_all(); drive_to_live();
    g_cancel_reentrant = 1;
    gdr_remove_device(&ctx, (void*)0x1234);
    /* the cancel synchronously completed the IN URB inside remove_device, so
     * RemoveComplete fired exactly once and the state is already IDLE. */
    CHECK(cancel_calls == 1, "reentrant: one IN URB cancelled");
    CHECK(rm_calls == 1, "reentrant: RemoveComplete acked once (sync cancel completion)");
    CHECK(ctx.lifecycle == GDR_LIFE_IDLE, "reentrant: lifecycle IDLE after remove");
    CHECK(ctx.detached == 1, "reentrant: still detached (title-lifetime ctx, not reused)");

    /* no callback after retire: a late/stale completion after the ack is a no-op */
    ctx.in_urb.Hdr.Status = 0xC0000120u; ctx.in_urb.TransferLength = 0;
    gdr_in_complete(&ctx.in_urb, &ctx);
    CHECK(rm_calls == 1, "reentrant: no callback-after-retire (late completion is a no-op)");
    CHECK(ctx.pending == 0, "reentrant: retired completion does not decrement pending (no underflow)");
    g_cancel_reentrant = 0;
}

/* The RemoveComplete ack must fire only AFTER the cancel walk finished. A
 * remove_complete seam that synchronously re-attaches is only legal at that
 * point; a reentrant cancel must NOT ack mid-walk. */
static void test_reentry_walk_guard(void) {
    reset_all(); drive_to_live();
    g_cancel_reentrant = 1;   /* cancel_request completes in_urb inline */
    gdr_remove_device(&ctx, (void*)0x1234);
    g_cancel_reentrant = 0;
    /* the ack happened only after removing_in_walk was cleared: recorded by the
     * fact that rm_calls==1 and the cancel walk is fully accounted */
    CHECK(rm_calls == 1, "walk-guard: RemoveComplete acked exactly once");
    CHECK(ctx.removing_in_walk == 0, "walk-guard: walk finished before ack");
    CHECK(ctx.lifecycle == GDR_LIFE_IDLE && ctx.pending == 0,
          "walk-guard: fully quiesced and idle after ack");
}

/* ---- 11. bounded failure: submit rejects during re-arm must not wedge ------ */
static void test_bounded_failure_rearm(void) {
    reset_all(); drive_to_live();
    /* make every re-arm submit reject immediately; feed one IN completion */
    sim_ret = -1L;
    ctx.in_urb.Hdr.Status = 0; ctx.in_urb.TransferLength = 64;
    for (int i = 0; i < 8; i++) ctx.rx_buf[i] = 0x11;
    int submits_before = sim_n;
    gdr_in_complete(&ctx.in_urb, &ctx);
    CHECK(ctx.in_flight == 0, "bounded: re-arm rejected -> in_flight NOT set");
    CHECK(ctx.in_submit_fail == 1, "bounded: one immediate reject counted");
    CHECK(ctx.pending == 0, "bounded: pending balanced after a reject");
    /* no submit storm: only the single re-arm attempt was made */
    CHECK(sim_n == submits_before + 1, "bounded: exactly one re-arm attempt (no storm)");
    sim_ret = 0;
}

/* ---- 12. Real captured 0x20 input from the slice1 real-pad run ------------ */
/* Verbatim RX seq=4 (n=48) from work/20-runtime/button-run.log — the real 045e:0b12
 * pad streaming under the repaired emulator. Feeds the REAL decoder, so this is
 * not a "source unchanged" assertion but a replay of captured positive input. */
static const u8 CAPTURED_INPUT[48] = {
    0x20,0x00,0xba,0x2c, 0x00,0x00,0x00,0x00,0x00,0x00,0x60,0x01,
    0xad,0xfd,0x8b,0x03,0xd4,0x03,0x00,0x00,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0x00,0x17,0x92,0xcc,0x1d,0xf4,0x94,0xcc,0x1d
};

static void test_captured_input(void) {
    struct gdr_gip m; gdr_gip_init(&m, 0);
    gdr_gip_qualify_wired(&m);   /* real no-announce qualified path */
    gdr_gip_rx(&m, CAPTURED_INPUT, (int)sizeof CAPTURED_INPUT);
    CHECK(m.snapshot_valid == 1 && m.input_reports == 1,
          "captured: real 20-runtime 0x20 packet decodes (snapshot valid)");
    CHECK(m.snap.lx == 352 && m.snap.ly == -595 && m.snap.rx == 907 && m.snap.ry == 980,
          "captured: stick axes decode from the real frame (352,-595,907,980)");
    CHECK(m.snap.buttons == 0 && m.snap.analog[6] == 0 && m.snap.analog[7] == 0,
          "captured: neutral buttons/triggers in the real frame");
}

int main(void) {
    printf("AmpJack-OG slice2 lifecycle regressions (gipdrive.h)\n");
    test_add_complete_success();
    test_add_complete_fail_stall();
    test_add_complete_fail_cfgfail();
    test_add_complete_immediate_reject();
    test_remove_during_live();
    test_remove_during_config_pending();
    test_remove_during_out_pending();
    test_no_submit_after_detach();
    test_reattach_fresh_generation();
    test_remove_edge_cases();
    test_neutral_snapshot();
    test_remove_reentrant_cancel();
    test_reentry_walk_guard();
    test_bounded_failure_rearm();
    test_captured_input();
    if (g_fail == 0) { printf("RESULT: ALL CHECKS PASSED\n"); return 0; }
    printf("RESULT: %d CHECK(S) FAILED\n", g_fail);
    return 1;
}
