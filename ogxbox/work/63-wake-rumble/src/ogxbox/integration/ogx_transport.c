/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * ogx_transport.c -- the PROVEN GIP USB transport, retargeted to the Halo 2 u803
 * title. It is the thin platform wrapper over ogxbox/gipdriver/gipdrive.h: it
 * does NOT duplicate the USB stack or rewrite the GIP protocol. It only supplies
 * the injected title call surface (SubmitRequest / AddComplete / CancelRequest /
 * RemoveComplete, all VERIFIED/UNKNOWN VAs from ogx_module.h) and the
 * FindClassDriver class-match hook, then bridges the decoded gdr_snapshot into
 * the og_gip_port snapshot that ogx_present.c serves.
 *
 * DPC contract (unchanged from the proven probe): every completion callback only
 * pushes one bounded ring event and re-submits; no file I/O, no malloc, no
 * unbounded formatting and no parse happens in the DPC. All decoding, snapshot
 * publication and OUT queuing happen here in ogx_module_pump(), on the title
 * thread, which is the single owner. No waiting on the title thread, no timers
 * and no blocking in the XInput hook.
 */
#include "ogx_module.h"
#include "ogx_log.h"

/* ---- chain trampolines (trampoline.S) + the stub ctx binder (ogx_stub.c) ---- */
void   ogx_stub_bind_ctx(struct ogx_host_ctx *ctx);
/* The trampolines are tail-jump stubs that re-run the displaced bytes and jmp to
 * the original body; the original body does the final `ret N`. Declare them with
 * the title's stdcall signature so ogx_present.c calls them with the right arg
 * count (their asm body reads the args from the stack and never returns). */
uint32_t  OGX_STDCALL ogx_chain_getdevicechanges(uintptr_t, uint32_t *, uint32_t *);
uintptr_t OGX_STDCALL ogx_chain_inputopen(uintptr_t, uint32_t, uint32_t, uintptr_t);
void      OGX_STDCALL ogx_chain_inputclose(uintptr_t);
uint32_t  OGX_STDCALL ogx_chain_getcaps(uintptr_t, uintptr_t);
uint32_t  OGX_STDCALL ogx_chain_getstate(uintptr_t, uintptr_t);
uint32_t  OGX_STDCALL ogx_chain_setstate(uintptr_t, uintptr_t);

/* -- thiscall thunks: C cannot put `self` in ECX portably, so the injected VAs
 *    are cast to OGX_THISCALL function pointers (i386 __thiscall on the title,
 *    plain function pointers on the host-test build). ---- */
typedef long (OGX_THISCALL *ogx_thiscall_submit)(void *self, void *urb);
typedef void (OGX_THISCALL *ogx_thiscall_addcomplete)(void *self, long status);
typedef long (OGX_THISCALL *ogx_thiscall_cancel)(void *self, void *urb);
typedef void (OGX_THISCALL *ogx_thiscall_removecomplete)(void *self);

/* ---- module singleton (declared extern in ogx_module.h). The injector fills
 *      ogx_g_module.host BEFORE ogx_module_entry(): BSS is zero at load, and
 *      entry does NOT re-zero host. ---------------------------------------------- */
struct ogx_module ogx_g_module;

/* ---- W63 diagnostics. The USB callbacks (DPC) ONLY increment these; every
 *      log line is formatted on the title thread. ---------------------------- */
static volatile uint32_t ogx_attach_calls, ogx_remove_calls, ogx_attach_refused;
static uint32_t ogx_rumble_sent;      /* last rumble value enqueued (l | r<<16) */
static uint32_t ogx_rumble_frames;    /* rumble frames enqueued                 */
static uint32_t ogx_rumble_logged, ogx_rumble_hev_logged;
static uint32_t ogx_l_att[5], ogx_l_att_valid;
static uint32_t ogx_l_in_seen, ogx_l_in_reports, ogx_l_in_ms;
static uint32_t ogx_l_cnt[10], ogx_l_cnt_ms, ogx_l_cnt_valid;

/* ---- transport seams: gdr_*_fn are plain function pointers in gipdrive.h;
 *      these wrappers do the thiscall through the injected VA. ------------------ */
static long ogx_usb_submit(void *device, void *urb)
{
	if (!ogx_g_module.host.submit_request)
		return -1;
	return ((ogx_thiscall_submit)(uintptr_t)ogx_g_module.host.submit_request)(device, urb);
}
static void ogx_usb_add_complete(void *device, long status)
{
	/* REQUIRED seam (0x416992): enumeration MUST signal AddComplete exactly once
	 * so the device leaves the pending-enum list. A zero injection is a refusal
	 * at install time, never a runtime no-op. */
	if (ogx_g_module.host.add_complete)
		((ogx_thiscall_addcomplete)(uintptr_t)ogx_g_module.host.add_complete)(device, status);
}
static long ogx_usb_cancel(void *device, void *urb)
{
	if (!ogx_g_module.host.cancel_request)
		return -1;
	return ((ogx_thiscall_cancel)(uintptr_t)ogx_g_module.host.cancel_request)(device, urb);
}
static void ogx_usb_remove_complete(void *device)
{
	/* REQUIRED seam (0x4165C6): native removal MUST close owned endpoints before
	 * this fires (gdr_close_next runs the default->IN->OUT close chain first). */
	if (ogx_g_module.host.remove_complete)
		((ogx_thiscall_removecomplete)(uintptr_t)ogx_g_module.host.remove_complete)(device);
}

/* ---- GIP class-driver description + callbacks ------------------------------ */

static void OGX_STDCALL ogx_gip_register(void *iUsbInit) { (void)iUsbInit; }
static void OGX_STDCALL ogx_gip_attach(void *device);
static void OGX_STDCALL ogx_gip_remove(void *device);

/* ---- F6 critical span: DISPATCH_LEVEL through the title's own imports -------
 * Xbox is uniprocessor. RemoveDevice and every URB completion run as DPCs, so
 * holding DISPATCH_LEVEL on the title thread defers them until KfLowerIrql;
 * that is real interruption exclusion, not a reentrancy flag. Raise/lower go
 * through the title's resolved kernel import slots (see ogx_module.h):
 *   KeRaiseIrqlToDpcLevel  stdcall(void) -> old KIRQL (AL)
 *   KfLowerIrql            fastcall(KIRQL NewIrql in CL)
 * Spans are short and bounded: one revalidation plus one gdr_tx_enqueue copy,
 * or one gdr_tx_submit_next (one SubmitRequest; inline completions re-enter it
 * at most GDR_TX_SLOTS times). No wait, spin, heap, file I/O, decode or
 * original XInput call ever runs inside a span. SubmitRequest at DISPATCH is
 * the same context the completion path already re-submits from. */
typedef uint8_t (OGX_STDCALL  *ogx_raise_fn)(void);
typedef void    (OGX_FASTCALL *ogx_lower_fn)(uint8_t new_irql);

static volatile uint32_t ogx_span_refused;   /* title build: OUT skipped, no span */
static volatile uint32_t ogx_span_revalid;   /* revalidation inside span refused  */

static int ogx_span_enter(uint8_t *old)
{
	uint32_t rs = ogx_g_module.host.irql_raise_slot;
	uint32_t ls = ogx_g_module.host.irql_lower_slot;
	ogx_raise_fn r;
	if (!rs || !ls || !*(volatile uint32_t *)(uintptr_t)ls)
		return 0;
	r = *(ogx_raise_fn volatile *)(uintptr_t)rs;
	if (!r)
		return 0;
	*old = r();
	return 1;
}
static void ogx_span_leave(uint8_t old)
{
	(*(ogx_lower_fn volatile *)(uintptr_t)ogx_g_module.host.irql_lower_slot)(old);
}

static volatile uint32_t ogx_attach_ran;
static uint32_t ogx_seen_generation;

/* OUT path validity, evaluated INSIDE the span: the caller's earlier
 * transport-live check may predate a RemoveDevice (and a re-attach). */
static int ogx_tx_valid(void)
{
	const struct gdr_attach_ctx *a = &ogx_g_module.att;
	return ogx_attach_ran && a->device && !a->detached && a->out_handle &&
	       a->generation == ogx_seen_generation;
}

/* op 0: enqueue one drained frame; op 1: submit the next queued frame */
static void ogx_tx_locked(int op, const u8 *pkt, int n)
{
	uint8_t old;
	if (!ogx_span_enter(&old)) {
#if __STDC_HOSTED__
		/* hosted regression builds that inject no IRQL doubles keep the
		 * pre-work/32 behaviour; the title build is freestanding. */
		if (op) gdr_tx_submit_next(&ogx_g_module.att);
		else    gdr_tx_enqueue(&ogx_g_module.att, pkt, n);
#else
		ogx_span_refused++;     /* fail closed: no OUT without exclusion */
#endif
		return;
	}
	if (!ogx_tx_valid())
		ogx_span_revalid++;
	else if (op)
		gdr_tx_submit_next(&ogx_g_module.att);
	else
		gdr_tx_enqueue(&ogx_g_module.att, pkt, n);
	ogx_span_leave(old);
}

/* ---- FindClassDriver E9 hook target ---------------------------------------- */
/*
 * u803 FindClassDriver @0x41517D VERIFIED (pin_u803.py, frozen bytes
 * 56 B8 B4 27 41 00 BE CC 27 41 00 3B C6 8B C8 73 ...):
 *     for (p = begin; p < end; p += 4) { if (!(d=*p)) continue;
 *         if (Lo(classId)==d->MatchByte0 && Hi(classId)==d->MatchByte1) return d; }
 *     return 0;
 * Reimplement that exact loop (pure C, IRQL-safe, no nested call) so every stock
 * class returns the identical descriptor; only 0xFF81 (GIP, measured on the real
 * device) returns ours. begin/end are INJECTED so a mismatched build fails closed.
 */
uintptr_t OGX_STDCALL ogx_findclassdriver(uint32_t classId)
{
	uint32_t begin = ogx_g_module.host.class_table_begin;
	uint32_t end   = ogx_g_module.host.class_table_end;
	uint32_t addr;

	if ((classId & 0xffffu) == (uint32_t)GDR_PNP_GIP)
		return (uintptr_t)&ogx_g_module.desc;

	for (addr = begin; addr + 4 <= end; addr += 4) {
		uintptr_t d = *(volatile uint32_t *)addr;
		if (!d)
			continue;
		if ((uint8_t)classId == *(volatile uint8_t *)d &&
		    (uint8_t)(classId >> 8) == *((volatile uint8_t *)d + 1))
			return d;
	}
	return 0;
}

/* attach-ran flag (separate from the derived "transport live" state);
 * declared above the F6 span helpers */

static void OGX_STDCALL ogx_gip_attach(void *device)
{
	/* native USB callback: run the producer body inside the span so its ring
	 * pushes / submits cannot interleave with a completion DPC even if the
	 * stack ever calls this below DISPATCH (at DISPATCH raise/lower is a
	 * same-level no-op). The body is bounded (one SubmitRequest). */
	uint8_t old;
	int span = ogx_span_enter(&old);
	ogx_attach_calls++;                              /* W63 counter only */
	ogx_attach_ran = 1;
	ogx_g_module.att.in_complete = gdr_in_complete;  /* shared completion (gipdrive.h) */
	ogx_g_module.att.cb_log = 0;                     /* no per-completion CB events    */
	if (gdr_attach_begin(&ogx_g_module.att, device, ogx_usb_submit, &ogx_g_module.ring)) {
		/* refused: previous generation still quiescing -> fail closed, abort THIS
		 * enumeration instead of clobbering a live context. */
		ogx_attach_refused++;                    /* W63 counter only */
		ogx_g_module.att.add_complete(device, (long)(int)0xC0000001L);
	}
	if (span) ogx_span_leave(old);
}
static void OGX_STDCALL ogx_gip_remove(void *device)
{
	uint8_t old;
	int span = ogx_span_enter(&old);
	ogx_remove_calls++;                              /* W63 counter only */
	gdr_remove_device(&ogx_g_module.att, device);
	if (span) ogx_span_leave(old);
}

/* ---- lifecycle truth independent of ring delivery (F1/F2/F3) ----------------
 * All of the state below is owned by the TITLE THREAD only: it is touched from
 * ogx_module_pump() (called from the XGetDeviceChanges stub) and from
 * ogx_transport_sync() (called from the other game-facing stubs). The DPC
 * producers are NOT changed: they still only push bounded ring events. The
 * title thread only READS the producer-owned att.generation / ring.head /
 * ring.overflow (aligned u32 loads) and only advances its own ring.tail by
 * normal pops; it never writes a producer index or counter.
 *
 * Ordering assumption (scoped, not asserted lock-free): RemoveDevice and the
 * URB completions run to completion without being interleaved with each other
 * by the title thread (single CPU; the title thread can be interrupted by them,
 * not the reverse). Under that model RemoveDevice's generation++ and its
 * DETACH push are observed together, and a dropped event can only be newer
 * than everything still queued (drop-newest, and no pop happened since).   */
static uint32_t ogx_stale_until;       /* ring index: events before it predate the
                                        * observed generation change -> discarded  */
static uint32_t ogx_stale_active;
static uint32_t ogx_seen_overflow;     /* last ring.overflow value acted upon      */
static uint32_t ogx_hold_removal;      /* keep the port unpublished until the game
                                        * has been shown the removal edge          */
static uint32_t ogx_pub_seq;           /* game-facing snapshot sequence            */
static uint32_t ogx_pub_reports;       /* gip.input_reports last published         */
static uint32_t ogx_pub_force;         /* republish even without a new report      */
static uint32_t ogx_lost_events;       /* diagnostics: events lost to overflow     */
static uint32_t ogx_gen_resyncs;       /* diagnostics: generation-driven resyncs   */

static int ogx_ring_before(uint32_t idx, uint32_t until)
{
	return (int32_t)(idx - until) < 0;      /* wrap-safe ring index compare */
}

static void ogx_gport_neutral(struct og_gip_port *gp)
{
	gp->ready = false;
	gp->snapshot_valid = false;
	memset(&gp->gamepad, 0, sizeof(gp->gamepad));
}

/* Generation-driven resync: called on the title thread whenever the real
 * att.generation differs from the last one acted upon, whether or not the
 * DETACH event survived the ring. Neutralizes the decoder (gen2 requalifies and
 * gets its own power-on), the published snapshot and every live virtual handle
 * of the port, and holds the port unpublished until the game's next
 * XGetDeviceChanges has reported the removal edge (prev_present is untouched,
 * so the game's removal event is not consumed). Events queued before this point
 * belong (in part) to the old generation and are discarded, never decoded. */
void ogx_transport_sync(void)
{
	uint32_t g = ogx_g_module.att.generation;
	if (g == ogx_seen_generation)
		return;
	ogx_seen_generation = g;
	ogx_rumble_sent = 0;          /* W63: re-send a nonzero rumble after replug */
	ogx_l_in_seen = 0;
	{
		struct ogx_log_line l;
		ogx_ll_begin(&l, "GEN");
		ogx_ll_dec(&l, "gen", g);
		ogx_ll_dec(&l, "attach", ogx_attach_calls);
		ogx_ll_dec(&l, "remove", ogx_remove_calls);
		ogx_ll_dec(&l, "refused", ogx_attach_refused);
		ogx_ll_end(&l);
	}
	ogx_stale_until  = ogx_g_module.ring.head;   /* read AFTER generation */
	ogx_stale_active = 1;
	ogx_gen_resyncs++;
	gdr_gip_neutralize(&ogx_g_module.gip);
	ogx_gport_neutral(&ogx_g_module.gport[OGX_TRANSPORT_PORT]);
	ogx_g_module.present.attached_mask &= ~(1u << OGX_TRANSPORT_PORT);
	ogx_hold_removal = 1;
	ogx_pub_force = 1;
	ogx_present_port_lost(&ogx_g_module.present, OGX_TRANSPORT_PORT);
}

/* Overflow fail-closed (F3): events were dropped (drop-newest), so the newest
 * physical state is unknown. Clear the decoded snapshot to neutral (all
 * buttons released, sticks centred) and republish with a new packet number.
 * The pad stays connected; it shows real input again on its next report. If
 * the user is still holding a button when the overflow ends, it reads as
 * released until the pad reports a change: fail CLOSED, never a stuck press. */
static void ogx_overflow_neutral(void)
{
	memset(&ogx_g_module.gip.snap, 0, sizeof(ogx_g_module.gip.snap));
	ogx_pub_force = 1;
}

/* ---- snapshot -> presentation bridge ----------------------------------------
 * gdr_snapshot and og_gamepad share the SAME 18-byte wire layout (asserted).    */
static void ogx_bridge_publish(void)
{
	struct ogx_host_ctx *p = &ogx_g_module.present;
	struct og_gip_port *gp = &ogx_g_module.gport[OGX_TRANSPORT_PORT];
	uint32_t mask = 1u << OGX_TRANSPORT_PORT;
	int live = gdr_transport_live((int)ogx_attach_ran, ogx_g_module.att.in_handle);

	/* removal hold: release only once the game has been shown the removal
	 * (effective presence already 0), so a fast replug always produces a
	 * rem edge before the next ins edge. */
	if (ogx_hold_removal && !p->prev_present[OGX_TRANSPORT_PORT])
		ogx_hold_removal = 0;
	if (ogx_hold_removal)
		live = 0;

	if (live) {
		/* powered-readable = gdr_gip.ready (set once minimal power-on accepted).
		 * Same "powered-ready, NOT input-seen" contract og_gip.h documents. */
		gp->ready = ogx_g_module.gip.ready ? true : false;
		if (ogx_pub_force || ogx_g_module.gip.input_reports != ogx_pub_reports) {
			ogx_pub_seq++;
			ogx_pub_reports = ogx_g_module.gip.input_reports;
			ogx_pub_force = 0;
		}
		gp->seq = ogx_pub_seq;
		if (ogx_g_module.gip.snapshot_valid) {
			gp->snapshot_valid = true;
			memcpy(&gp->gamepad, &ogx_g_module.gip.snap, sizeof(gp->gamepad));
		} else {
			/* no trusted frame in THIS generation: never keep an older one */
			gp->snapshot_valid = false;
			memset(&gp->gamepad, 0, sizeof(gp->gamepad));
		}
		p->attached_mask |= mask;
	} else {
		if (p->attached_mask & mask) {
			gp->ready = false;
			gp->snapshot_valid = false;
			memset(&gp->gamepad, 0, sizeof(gp->gamepad));
		}
		p->attached_mask &= ~mask;
	}
}

/* ---- W63 log helpers (title thread only) ---------------------------------- */
static int ogx_is_virtual(uintptr_t h)
{
	const struct ogx_host_ctx *p = &ogx_g_module.present;
	return h >= (uintptr_t)&p->vh[0] && h < (uintptr_t)&p->vh[OGX_HANDLE_ARENA];
}
void ogx_log_gdc(uintptr_t dtype, uint32_t ins, uint32_t rem)
{
	struct ogx_log_line l;
	ogx_ll_begin(&l, "GDC");
	ogx_ll_hex(&l, "type", (uint32_t)dtype);
	ogx_ll_dec(&l, "gamepad", dtype == ogx_g_module.present.xdevice_type_gamepad);
	ogx_ll_hex(&l, "ins", ins);
	ogx_ll_hex(&l, "rem", rem);
	ogx_ll_end(&l);
}
void ogx_log_xi(int open, uint32_t port, uintptr_t handle)
{
	struct ogx_log_line l;
	ogx_ll_begin(&l, open ? "XIOPEN" : "XICLOSE");
	if (open) ogx_ll_dec(&l, "port", port);
	ogx_ll_str(&l, "kind", !handle ? "none" : ogx_is_virtual(handle) ? "virtual" : "native");
	ogx_ll_hex(&l, open ? "result" : "handle", (uint32_t)handle);
	ogx_ll_end(&l);
}
static void ogx_log_rx(const u8 *d, u32 len)
{
	struct ogx_log_line l;
	if (!ogx_log_on())
		return;
	while (len > 3) {
		u8 cmd = d[0], opt = d[1], sq = d[2];
		u32 pl = 0, avail, nb; int c = 0, hdr, i;
		for (i = 0; i < 4 && 3 + i < (int)len; i++) {
			pl |= (u32)(d[3 + i] & 0x7f) << (7 * i); c++;
			if (!(d[3 + i] & 0x80)) break;
		}
		hdr = 3 + c;
		if (opt & GIP_OPT_CHUNK) {
			while (hdr < (int)len && (d[hdr] & 0x80)) hdr++;
			hdr++;
		}
		avail = (u32)hdr < len ? len - (u32)hdr : 0;
		if (cmd != GIP_CMD_INPUT) {
			nb = pl < avail ? pl : avail;
			if (nb > 32) nb = 32;
			ogx_ll_begin(&l, "RX");
			ogx_ll_hex(&l, "cmd", cmd);
			ogx_ll_hex(&l, "opt", opt);
			ogx_ll_dec(&l, "seq", sq);
			ogx_ll_dec(&l, "len", pl);
			ogx_ll_bytes(&l, "data", d + hdr, nb);
			ogx_ll_end(&l);
		}
		if ((u32)hdr > len || pl > avail)
			break;
		d += (u32)hdr + pl;
		len -= (u32)hdr + pl;
	}
}
static void ogx_log_att(void)
{
	const struct gdr_attach_ctx *a = &ogx_g_module.att;
	u32 v[5] = { a->state, a->lifecycle, a->in_handle, a->out_handle, a->failed };
	struct ogx_log_line l;
	int i, same = ogx_l_att_valid;
	if (!ogx_log_on())
		return;
	for (i = 0; i < 5; i++) if (v[i] != ogx_l_att[i]) same = 0;
	if (same)
		return;
	for (i = 0; i < 5; i++) ogx_l_att[i] = v[i];
	ogx_l_att_valid = 1;
	ogx_ll_begin(&l, "ATT");
	ogx_ll_dec(&l, "state", v[0]);
	ogx_ll_dec(&l, "life", v[1]);
	ogx_ll_hex(&l, "in", v[2]);
	ogx_ll_hex(&l, "out", v[3]);
	ogx_ll_dec(&l, "failed", v[4]);
	ogx_ll_dec(&l, "gen", a->generation);
	ogx_ll_end(&l);
}
static void ogx_log_periodic(u32 now)
{
	struct ogx_host_ctx *p = &ogx_g_module.present;
	struct gdr_gip *m = &ogx_g_module.gip;
	struct ogx_log_line l;
	u32 w = p->rumble_want[OGX_TRANSPORT_PORT];
	int i, same;
	if (!ogx_log_on())
		return;
	if (m->input_reports && (!ogx_l_in_seen ||
	    (m->input_reports != ogx_l_in_reports && (u32)(now - ogx_l_in_ms) >= 1000u))) {
		ogx_ll_begin(&l, "IN");
		ogx_ll_dec(&l, "first", !ogx_l_in_seen);
		ogx_ll_dec(&l, "reports", m->input_reports);
		ogx_ll_hex(&l, "buttons", m->snap.buttons);
		ogx_ll_end(&l);
		ogx_l_in_seen = 1; ogx_l_in_reports = m->input_reports; ogx_l_in_ms = now;
	}
	if (p->rumble_calls && (w != ogx_rumble_logged || !ogx_rumble_hev_logged)) {
		ogx_ll_begin(&l, "RUMBLE");
		ogx_ll_hex(&l, "l", w & 0xffffu);
		ogx_ll_hex(&l, "r", w >> 16);
		ogx_ll_dec(&l, "calls", p->rumble_calls);
		if (!ogx_rumble_hev_logged) ogx_ll_hex(&l, "hevent", p->rumble_hevent);
		ogx_ll_end(&l);
		ogx_rumble_logged = w; ogx_rumble_hev_logged = 1;
	}
	if ((u32)(now - ogx_l_cnt_ms) >= 5000u) {
		u32 v[10] = { ogx_lost_events, ogx_gen_resyncs, ogx_span_refused, ogx_span_revalid,
		              m->tx_dropped, m->unknown_cmds, m->announces, m->rehandshakes,
		              p->rumble_calls, ogx_rumble_frames };
		ogx_l_cnt_ms = now;
		same = ogx_l_cnt_valid;
		for (i = 0; i < 10; i++) if (v[i] != ogx_l_cnt[i]) same = 0;
		if (!same) {
			for (i = 0; i < 10; i++) ogx_l_cnt[i] = v[i];
			ogx_l_cnt_valid = 1;
			ogx_ll_begin(&l, "CNT");
			ogx_ll_dec(&l, "lost_events", v[0]);
			ogx_ll_dec(&l, "gen_resyncs", v[1]);
			ogx_ll_dec(&l, "span_refused", v[2]);
			ogx_ll_dec(&l, "span_revalid", v[3]);
			ogx_ll_dec(&l, "tx_dropped", v[4]);
			ogx_ll_dec(&l, "unknown_cmds", v[5]);
			ogx_ll_dec(&l, "announces", v[6]);
			ogx_ll_dec(&l, "rehandshakes", v[7]);
			ogx_ll_dec(&l, "setstate", v[8]);
			ogx_ll_dec(&l, "rumble_frames", v[9]);
			ogx_ll_end(&l);
		}
	}
}

/* ---- W63 rumble: ONE frame when the whole OUT path is idle (latest wins) ----
 * xpad Xbox One form: 09 00 <seq> 09 | 00 0F 00 00 <L> <R> FF 00 FF, with
 * L = OG left (low-frequency) speed >> 9, R = right speed >> 9. Never between a
 * power-on and its S-init. Title thread only; the frame goes through the normal
 * drain -> span-locked enqueue -> submit path. */
static void ogx_rumble_service(void)
{
	struct gdr_gip *m = &ogx_g_module.gip;
	const struct gdr_attach_ctx *a = &ogx_g_module.att;
	u32 want = ogx_g_module.present.rumble_want[OGX_TRANSPORT_PORT];
	u8 p[9] = { 0x00, 0x0F, 0x00, 0x00, 0, 0, 0xFF, 0x00, 0xFF };
	u8 f[64]; int n;
	if (!m->ready || m->s_init_pending || want == ogx_rumble_sent)
		return;
	if (m->txh != m->txt || a->tx_head != a->tx_tail || a->tx_busy)
		return;
	p[4] = (u8)((want & 0xffffu) >> 9);
	p[5] = (u8)((want >> 16) >> 9);
	n = gdr_gip_frame(f, GIP_CMD_RUMBLE, 0, gdr_next_seq(m), p, 9);
	if (gdr_tx_send(m, f, n)) {
		ogx_rumble_sent = want;
		ogx_rumble_frames++;
	}
}

void ogx_transport_init(void)
{
	struct ogx_host_ctx *p = &ogx_g_module.present;
	uint32_t i;

	/* the six XInput stubs reach THIS presentation ctx */
	ogx_stub_bind_ctx(p);

#ifdef __i386__
	/* chain trampolines: native handles pass through these back to the title.
	 * Declared stdcall (above) so the call site's argument count matches the
	 * original function's `ret N`; the trampoline body tail-jumps and never
	 * returns itself. i386/title-only: on the host-test build the trampolines
	 * are undefined and orig_* stay NULL (the test injects its own fakes). */
	p->orig_XGetDeviceChanges     = ogx_chain_getdevicechanges;
	p->orig_XInputOpen            = ogx_chain_inputopen;
	p->orig_XInputClose           = ogx_chain_inputclose;
	p->orig_XInputGetCapabilities = ogx_chain_getcaps;
	p->orig_XInputGetState        = ogx_chain_getstate;
	p->orig_XInputSetState        = ogx_chain_setstate;
#endif

	/* the GAMEPAD device-type POINTER IDENTITY (host.xdevice_type_gamepad is
	 * the title's 0x4127D8 address, injected; the runtime compares pointer
	 * equality only and never dereferences it). */
	p->xdevice_type_gamepad = ogx_g_module.host.xdevice_type_gamepad;
	for (i = 0; i < OGX_MAX_PORTS; i++)
		p->ports[i] = &ogx_g_module.gport[i];

	gdr_gip_init(&ogx_g_module.gip, 0);
	gdr_ring_reset(&ogx_g_module.ring);
	ogx_seen_generation = ogx_g_module.att.generation;
	ogx_seen_overflow   = ogx_g_module.ring.overflow;
	ogx_stale_active = 0;
	ogx_hold_removal = 0;

	/* 24-byte VERIFIED class description */
	ogx_g_module.desc.MatchByte0 = 0x81;   /* low byte of measured PNP_CLASS_ID 0xFF81 */
	ogx_g_module.desc.MatchByte1 = 0xFF;   /* high byte                              */
	ogx_g_module.desc.pad[0] = 0xFF; ogx_g_module.desc.pad[1] = 0xFF;
	ogx_g_module.desc.Register       = (uint32_t)(uintptr_t)&ogx_gip_register;
	ogx_g_module.desc.Attach         = (uint32_t)(uintptr_t)&ogx_gip_attach;
	ogx_g_module.desc.RemoveDevice   = (uint32_t)(uintptr_t)&ogx_gip_remove;
	ogx_g_module.desc.TypeInfo       = 0;   /* 0xFF device: AddComplete never reads it */
	ogx_g_module.desc.DispatchTable  = 0;

	/* lifecycle seams persist across re-attach (attach resets per-generation) */
	ogx_g_module.att.add_complete    = ogx_usb_add_complete;
	ogx_g_module.att.cancel_request  = ogx_usb_cancel;
	ogx_g_module.att.remove_complete = ogx_usb_remove_complete;
}

/* ---- per-title-tick pump (single owner thread) ---------------------------- */
void ogx_module_pump(void)
{
	struct gdr_evt ev;
	u32 now, ov, ov_until = 0, idx;
	int ov_pending = 0;

	/* 1. lifecycle truth from the real generation, not from ring delivery */
	ogx_transport_sync();
	ogx_log_att();

	/* 2. overflow: everything queued NOW is older than the dropped events
	 *    (drop-newest; no pop since the drop). Decode it as history, then
	 *    neutralize at that boundary; events pushed later are newer and
	 *    trusted. overflow is read, never cleared (producer-owned). */
	ov = ogx_g_module.ring.overflow;
	if (ov != ogx_seen_overflow) {
		ogx_lost_events += ov - ogx_seen_overflow;
		ogx_seen_overflow = ov;
		ov_until = ogx_g_module.ring.head;       /* read AFTER overflow */
		ov_pending = 1;
	}

	for (;;) {
		idx = ogx_g_module.ring.tail;            /* consumer-owned */
		if (ov_pending && !ogx_ring_before(idx, ov_until)) {
			ogx_overflow_neutral();
			ov_pending = 0;
		}
		if (!gdr_ring_pop(&ogx_g_module.ring, &ev))
			break;
		if (ogx_stale_active) {
			if (ogx_ring_before(idx, ogx_stale_until))
				continue;                /* predates the generation change */
			ogx_stale_active = 0;
		}
		if (ev.kind == GDR_EVT_RX) {
			u32 rh = ogx_g_module.gip.rehandshakes;
			u32 rl = ev.len > GDR_PKT_MAX ? GDR_PKT_MAX : ev.len;
			ogx_log_rx(ev.data, rl);
			gdr_gip_rx(&ogx_g_module.gip, ev.data, (int)ev.len);
			if (ogx_g_module.gip.rehandshakes != rh) {
				struct ogx_log_line l;
				ogx_ll_begin(&l, "REHS");
				ogx_ll_dec(&l, "n", ogx_g_module.gip.rehandshakes);
				ogx_ll_dec(&l, "announces", ogx_g_module.gip.announces);
				ogx_ll_dec(&l, "s_init_pending", (u32)ogx_g_module.gip.s_init_pending);
				ogx_ll_end(&l);
			}
		} else if (ev.kind == GDR_EVT_TXDONE) {
			struct ogx_log_line l;
			ogx_ll_begin(&l, "TXDONE");
			ogx_ll_hex(&l, "cmd", ev.b);
			ogx_ll_hex(&l, "status", ev.a);
			ogx_ll_dec(&l, "len", ev.len);
			ogx_ll_end(&l);
			if (ev.b == GIP_CMD_POWER && (long)(int)ev.a >= 0)
				gdr_gip_on_power_done(&ogx_g_module.gip);
		} else if (ev.kind == GDR_EVT_DETACH) {
			/* a removal pushed while we were draining: same generation
			 * resync (discards what remains of the old generation) */
			ogx_transport_sync();
		}
	}
	if (ov_pending)
		ogx_overflow_neutral();

	/* now_ms is UNUSED by gdr_gip_poll (a no-op) -- all timing is
	 * completion-driven. It is read here only to keep the (correctly typed u32
	 * stdcall) injected clock plumbed for a future keepalive; no timing
	 * dependency exists today. */
	now = ogx_g_module.host.now_ms ? ogx_g_module.host.now_ms() : 0u;

	if (gdr_transport_live((int)ogx_attach_ran, ogx_g_module.att.in_handle)) {
		if (ogx_g_module.att.state >= 6u && ogx_g_module.gip.gamepad == 0) {
			struct ogx_log_line l;
			gdr_gip_qualify_wired(&ogx_g_module.gip);  /* minimal power-on, S-init on done */
			ogx_ll_begin(&l, "QUAL");
			ogx_ll_dec(&l, "ready", (u32)ogx_g_module.gip.ready);
			ogx_ll_dec(&l, "s_init_pending", (u32)ogx_g_module.gip.s_init_pending);
			ogx_ll_end(&l);
		}
		gdr_gip_poll(&ogx_g_module.gip, now);
		ogx_rumble_service();

		/* OUT: drain (title-thread decoder state, outside any span), then
		 * enqueue and submit each in its own short DISPATCH span with the
		 * context revalidated inside it (F6). */
		u8 out_pkt[64]; int out_n;
		while ((out_n = gdr_tx_drain(&ogx_g_module.gip, out_pkt, 64)) > 0) {
			struct ogx_log_line l;
			ogx_ll_begin(&l, "TX");
			ogx_ll_hex(&l, "cmd", out_pkt[0]);
			ogx_ll_dec(&l, "seq", out_pkt[2]);
			ogx_ll_dec(&l, "len", (u32)out_n);
			ogx_ll_end(&l);
			ogx_tx_locked(0, out_pkt, out_n);
		}
		ogx_tx_locked(1, 0, 0);
	}

	ogx_bridge_publish();

	/* W63: IN / RUMBLE / CNT lines, then the only file I/O (PASSIVE only) */
	ogx_log_periodic(ogx_log_ms());
	ogx_log_service();
}

/* ---- status for the parent's readback (bits) ------------------------------ */
uint32_t ogx_module_status(void)
{
	uint32_t s = ogx_g_module.installed_hooks;              /* bits 0..7 (0..6 XInput, 7 FindClass) */
	if (ogx_g_module.installed_hooks & (1u << 8)) s |= (1u << 8);
	if (gdr_transport_live((int)ogx_attach_ran, ogx_g_module.att.in_handle)) s |= (1u << 9);
	if (ogx_g_module.gip.snapshot_valid)     s |= (1u << 10);
	if (ogx_g_module.install_failed)         s |= (1u << 11);
	if (ogx_g_module.host.cancel_request == 0) s |= (1u << 12);  /* cancel optional/unresolved */
	if (ogx_lost_events)                     s |= (1u << 13);  /* ring overflow -> fail-closed neutral ran */
	if (ogx_gen_resyncs)                     s |= (1u << 14);  /* generation-driven resync ran */
	if (ogx_span_refused)                    s |= (1u << 15);  /* OUT skipped: no IRQL span (title build) */
	if (ogx_span_revalid)                    s |= (1u << 16);  /* OUT refused by in-span revalidation */
	return s;
}

_Static_assert(sizeof(struct gdr_snapshot) == 18, "gdr_snapshot 18B");
_Static_assert(sizeof(struct og_gamepad) == 18, "og_gamepad 18B");
