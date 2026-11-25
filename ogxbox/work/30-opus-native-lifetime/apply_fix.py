#!/usr/bin/env python3
"""apply_fix.py -- one-shot, asserted source transform of gipdrive.h (work/30).
Every replacement must match exactly the expected number of times, else abort
without writing. Run: python3 apply_fix.py <in gipdrive.h> <out gipdrive.h>"""
import re, sys

src = open(sys.argv[1]).read()
s = src

def rep(old, new, count=1):
    global s
    n = s.count(old)
    if n != count:
        sys.exit(f"ABORT: expected {count} match(es), got {n}:\n{old[:200]}")
    s = s.replace(old, new)

def func_region(sig):
    """[start,end) of the function whose definition starts with sig."""
    defs = list(re.finditer(re.escape(sig) + r"[^;{]*\{", s))   # definitions, not prototypes
    if len(defs) != 1:
        sys.exit(f"ABORT: {len(defs)} definitions of {sig!r}")
    a = defs[0].start()
    m = re.compile(r"^}\n", re.M).search(s, a)
    return a, m.end()

def rep_in(sig, old, new, count=1):
    global s
    a, b = func_region(sig)
    body = s[a:b]
    n = body.count(old)
    if n != count:
        sys.exit(f"ABORT: in {sig!r} expected {count} match(es) of {old!r}, got {n}")
    s = s[:a] + body.replace(old, new) + s[b:]

# ---- E1: struct fields (appended; existing fields untouched) + own helpers --
rep("""    volatile u32   close_submit_fail; /* immediate close-submit rejections       */
};
""", """    volatile u32   close_submit_fail; /* immediate close-submit rejections       */

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
""")

rep("""static void gdr_pending_enter(struct gdr_attach_ctx *ctx);
static void gdr_pending_leave(struct gdr_attach_ctx *ctx);
static int  gdr_complete_enter(struct gdr_attach_ctx *ctx);
static void gdr_close_next(struct gdr_attach_ctx *ctx);
""", """static void gdr_retire_check(struct gdr_attach_ctx *ctx);
static void gdr_close_next(struct gdr_attach_ctx *ctx);
""")

# ---- OUT path -------------------------------------------------------------
rep_in("static void gdr_tx_submit_next(", """        gdr_pending_enter(ctx);
        {
            long r = ctx->submit(ctx->device, u);
            if ((long)r < 0) {
                /* immediate rejection: NOT in flight, surface it, do not keep
                 * blindly resubmitting the same URB. */
                ctx->tx_busy = 0;
                ctx->tx_submit_fail++;
                gdr_pending_leave(ctx);
            }
        }""", """        gdr_own_take(ctx, &ctx->tx_busy);
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
        }""")
rep_in("static void GDR_STDCALL gdr_tx_complete(", "    if (!gdr_complete_enter(ctx)) return;\n",
       "    if (!gdr_own_drop(ctx, &ctx->tx_busy)) { ctx->stale_completions++; return; }\n"
       "    if (ctx->detached) { ctx->tx_busy = 0; gdr_retire_check(ctx); return; }\n")

# ---- IN path --------------------------------------------------------------
rep_in("static void GDR_STDCALL gdr_in_complete(", "    if (!gdr_complete_enter(ctx)) return;\n",
       "    if (!gdr_own_drop(ctx, &ctx->in_flight)) { ctx->stale_completions++; return; }\n"
       "    if (ctx->detached) { ctx->in_flight = 0; gdr_retire_check(ctx); return; }\n")
rep_in("static void GDR_STDCALL gdr_in_complete(", "gdr_pending_enter(ctx);", "gdr_own_take(ctx, &ctx->in_flight);")
rep_in("static void GDR_STDCALL gdr_in_complete(", "gdr_pending_leave(ctx);", "gdr_own_drop(ctx, &ctx->in_flight);")

# ---- lifecycle helpers ------------------------------------------------------
a = s.index("/* Honest pending accounting.")
b = s.index("/* Ack removal: call RemoveComplete exactly once")
s = s[:a] + """/* Retirement driver (any context; bounded, no wait). Runs after RemoveDevice
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

""" + s[b:]

# ---- close chain ------------------------------------------------------------
a, b = func_region("static void gdr_close_next(")
s = s[:a] + """static void gdr_close_next(struct gdr_attach_ctx *ctx) {
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
""" + s[b:]

a, b = func_region("static void GDR_STDCALL gdr_close_complete(")
s = s[:a] + """static void GDR_STDCALL gdr_close_complete(void *urb, void *ctxv) {
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
""" + s[b:]

rep_in("static void gdr_remove_device(", "    ctx->in_flight  = 0;\n    ctx->tx_busy    = 0;\n",
       "    /* in_flight / tx_busy are NOT cleared: they are the IN / OUT URB\n"
       "     * ownership words and stay set until that URB's completion arrives or\n"
       "     * its pipe's close completes (gdr_close_complete). */\n")
rep_in("static void gdr_remove_device(", "    ctx->close_pending = 0;\n",
       "    ctx->close_pending = 0;\n    ctx->close_which = 0;\n")
rep_in("static void gdr_remove_device(",
       "    if (!ctx->close_started) { ctx->close_started = 1; gdr_close_next(ctx); }\n",
       "    if (!ctx->close_started) { ctx->close_started = 1; gdr_retire_check(ctx); }\n")

# ---- enumeration chain ------------------------------------------------------
rep_in("static void gdr_ctrl_get_desc(", "gdr_pending_enter(ctx);", "gdr_own_take(ctx, &ctx->own_ctrl);")
rep_in("static void gdr_ctrl_get_desc(", "gdr_pending_leave(ctx);", "gdr_own_drop(ctx, &ctx->own_ctrl);")

def open_prologue(slot):
    return ("    if (!gdr_own_drop(ctx, &ctx->own_open)) { ctx->stale_completions++; return; }\n"
            f"    if (ctx->detached) {{ gdr_late_open(ctx, u, &ctx->{slot}); return; }}\n")
CTRL_PRO = ("    if (!gdr_own_drop(ctx, &ctx->own_ctrl)) { ctx->stale_completions++; return; }\n"
            "    if (ctx->detached) { gdr_retire_check(ctx); return; }\n")
OLD_PRO = "    if (!gdr_complete_enter(ctx)) return;\n"
rep_in("static void GDR_STDCALL gdr_step_s0c(", OLD_PRO, open_prologue("close_ctrl"))
rep_in("static void GDR_STDCALL gdr_step_s1(", OLD_PRO, CTRL_PRO)
rep_in("static void GDR_STDCALL gdr_step_s2(", OLD_PRO, CTRL_PRO)
rep_in("static void GDR_STDCALL gdr_step_s2(", "gdr_pending_enter(ctx);", "gdr_own_take(ctx, &ctx->own_ctrl);")
rep_in("static void GDR_STDCALL gdr_step_s2(", "gdr_pending_leave(ctx);", "gdr_own_drop(ctx, &ctx->own_ctrl);")
rep_in("static void GDR_STDCALL gdr_step_s3(", OLD_PRO, CTRL_PRO)
rep_in("static void GDR_STDCALL gdr_step_s3(", "gdr_pending_enter(ctx);", "gdr_own_take(ctx, &ctx->own_open);")
rep_in("static void GDR_STDCALL gdr_step_s3(", "gdr_pending_leave(ctx);", "gdr_own_drop(ctx, &ctx->own_open);")
rep_in("static void GDR_STDCALL gdr_step_s4(", OLD_PRO, open_prologue("close_in"))
rep_in("static void GDR_STDCALL gdr_step_s4(", "gdr_pending_enter(ctx);", "gdr_own_take(ctx, &ctx->own_open);")
rep_in("static void GDR_STDCALL gdr_step_s4(", "gdr_pending_leave(ctx);", "gdr_own_drop(ctx, &ctx->own_open);")
rep_in("static void GDR_STDCALL gdr_step_s5(", OLD_PRO, open_prologue("close_out"))
rep_in("static void GDR_STDCALL gdr_step_s5(", "gdr_pending_enter(ctx);", "gdr_own_take(ctx, &ctx->in_flight);")
rep_in("static void GDR_STDCALL gdr_step_s5(", "gdr_pending_leave(ctx);", "gdr_own_drop(ctx, &ctx->in_flight);")

rep_in("static int gdr_attach_begin(",
       "    if (ctx->lifecycle == GDR_LIFE_REMOVING || ctx->pending != 0) return 1;\n",
       "    if (ctx->lifecycle == GDR_LIFE_REMOVING || ctx->pending != 0 || gdr_own_any(ctx)) return 1;\n")
rep_in("static int gdr_attach_begin(", "    ctx->close_pending = 0;\n",
       "    ctx->close_pending = 0;\n    ctx->close_which = 0;\n")
rep_in("static int gdr_attach_begin(", "gdr_pending_enter(ctx);", "gdr_own_take(ctx, &ctx->own_open);")
rep_in("static int gdr_attach_begin(", "gdr_pending_leave(ctx);", "gdr_own_drop(ctx, &ctx->own_open);")

for gone in ("gdr_pending_enter", "gdr_pending_leave", "gdr_complete_enter", "ctx->pending = 0;                   /* endpoints closed"):
    if gone in s:
        sys.exit(f"ABORT: leftover {gone}")
open(sys.argv[2], "w").write(s)
print("ok", len(src), "->", len(s))
