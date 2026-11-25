/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * lifetime_test.c -- work/30 native endpoint-lifetime variants (F4/F5/F6).
 *
 * Reuses the work/28 harness UNMODIFIED by textual inclusion (its main() is
 * renamed), so the same PRODUCTION objects (ogx_transport.c, ogx_present.c,
 * ogx_stub.c, xinput_model.c + the live gipdrive.h) and the same SYNTHETIC
 * title-side doubles (native_mock.c: thiscall SubmitRequest/AddComplete/
 * RemoveComplete, stdcall URB completions, async by default) are exercised.
 *
 * Added here only: thiscall wrappers around the mock's SubmitRequest (selective
 * immediate rejection) and RemoveComplete (quiescence audit AT the ack), plus a
 * per-handle open/close ledger. Nothing in the module is driven directly except
 * through ogx_findclassdriver -> Attach/RemoveDevice and URB completions.
 */
#define main lifecycle28_main
#include "../../28-opus-controller-review/tests/lifecycle_test.c"
#undef main

#define TC __attribute__((thiscall))
typedef long (TC *t_submit)(void *, void *);
typedef void (TC *t_rc)(void *);
static t_submit real_submit;
static t_rc real_rc;
static int reject_fn = -1, reject_after = 0;   /* reject the Nth next submit of fn */
static int rc_bad, rc_seen;

#define ATT ogx_g_module.att
#ifdef GDR_BASELINE   /* RED run on the pre-fix header: new fields absent */
#define CNT(f) 0xFFFFFFFFu
#define OWNF(f) 0u
static int own_any(void) { return ATT.pending || ATT.open_pending || ATT.ctrl_pending || ATT.in_flight || ATT.tx_busy; }
#else
#define CNT(f) (ATT.f)
#define OWNF(f) (ATT.f)
static int own_any(void) { return ATT.own_open || ATT.own_ctrl || ATT.in_flight || ATT.tx_busy; }
#endif

/* handle ledger: opened (successful open completion observed by the test) */
static uint32_t opened[16]; static int nopened;
static int closes_of(uint32_t h) { int n = 0; for (int i = 0; i < M.nclose; i++) n += M.close_h[i] == h; return n; }

static long TC wrap_submit(void *self, void *urb)
{
	gdr_urb_header *h = (gdr_urb_header *)urb;
	if (reject_fn >= 0 && h->Function == (uint8_t)reject_fn) {
		if (reject_after-- <= 0) { reject_fn = -1; return (long)0xC0000001u; }
	}
	return real_submit(self, urb);
}
static void TC wrap_rc(void *self)
{
	struct fake_dev *d = self;
	rc_seen++;
	/* RemoveComplete is legal only at full quiescence of THIS device */
	int pend_dev = 0; for (int i = 0; i < M.npend; i++) pend_dev += M.pend[i].dev == d;
	int in_dev = M.in_urb && M.in_dev == d && own_any();
	int open_left = 0; for (int i = 0; i < nopened; i++) if (((opened[i] >> 8) & 0xF) == (uint32_t)d->id || opened[i] == 0x1000u + d->id) open_left += closes_of(opened[i]) == 0;
	if (pend_dev || in_dev || own_any() || ATT.close_pending || ATT.pending || ATT.close_ctrl || ATT.close_in || ATT.close_out || open_left) {
		rc_bad++;
		printf("    info RC audit: pend_dev=%d in=%d own=%d/%d/%d/%d close_pending=%u pending=%u slots=%x/%x/%x open_left=%d\n",
		       pend_dev, in_dev, OWNF(own_open), OWNF(own_ctrl), OWNF(in_flight), OWNF(tx_busy), ATT.close_pending, ATT.pending,
		       ATT.close_ctrl, ATT.close_in, ATT.close_out, open_left);
	}
	real_rc(self);
}
static void init30(void)
{
	harness_init();
	real_submit = (t_submit)(uintptr_t)ogx_g_module.host.submit_request;
	real_rc = (t_rc)(uintptr_t)ogx_g_module.host.remove_complete;
	ogx_g_module.host.submit_request = (uint32_t)(uintptr_t)wrap_submit;
	ogx_g_module.host.remove_complete = (uint32_t)(uintptr_t)wrap_rc;
}

/* complete one specific pending URB (status) and record successful opens */
static int complete_urb(void *urb, uint32_t status)
{
	for (int j = 0; j < M.npend; j++) if (M.pend[j].urb == urb) {
		memmove(&M.pend[j], &M.pend[j + 1], (size_t)(M.npend - j - 1) * sizeof M.pend[0]); M.npend--;
		gdr_urb_header *h = urb;
		if ((h->Function == 0x02 || h->Function == 0x82) && (int)status >= 0 && nopened < 16)
			opened[nopened++] = ((gdr_urb_open *)urb)->EndpointHandle;
		mock_complete(urb, status);
		return 1;
	}
	return 0;
}
/* async FIFO step that records opens; returns 0 if nothing pending */
static int step(void) { return M.npend ? complete_urb(M.pend[0].urb, 0) : 0; }
static int run_all(void) { int n = 0; while (step()) n++; return n; }
/* complete everything EXCEPT `keep`, FIFO, bounded */
static void run_except(void *keep)
{
	for (int k = 0; k < 16; k++) {
		int j = 0; while (j < M.npend && M.pend[j].urb == keep) j++;
		if (j >= M.npend) return;
		complete_urb(M.pend[j].urb, 0);
	}
}
/* enumerate to just before step n completes: n=0 default-open pending,
 * 4 = open-IN pending, 5 = open-OUT pending */
static void *enum_to(struct fake_dev *d, int n)
{
	attach(d);
	for (int i = 0; i < n; i++) step();
	return M.npend ? M.pend[0].urb : 0;
}
static int nclose_dev(int id) { int n = 0; for (int i = 0; i < M.nclose; i++) n += M.close_dev[i] == id; return n; }

static void common_tail(struct fake_dev *d, int want_rc)
{
	CHECK(d->remove_completes == want_rc, "RemoveComplete count %d (want %d)", d->remove_completes, want_rc);
	CHECK(rc_bad == 0, "RemoveComplete only at full quiescence (audit violations=%d)", rc_bad);
	int dbl = 0; for (int i = 0; i < M.nclose; i++) dbl += closes_of(M.close_h[i]) > 1;
	CHECK(dbl == 0, "no endpoint handle closed twice");
	CHECK(M.freed_calls == 0 && M.violations == 0, "no native call on freed device (freed=%d viol=%d)", M.freed_calls, M.violations);
	CHECK((int)ATT.pending >= 0 && ATT.pending <= 4, "pending sane, no underflow (%u)", ATT.pending);
}

/* V01 remove while DEFAULT-pipe open (S0, fn 0x82) is accepted+outstanding */
static void v01_default_open_late(void)
{
	void *o = enum_to(&D1, 0);
	detach(&D1);
	CHECK(D1.remove_completes == 0, "no ack while default open outstanding");
	complete_urb(o, 0);                        /* late success -> handle 0x1001 */
	run_all();
	CHECK(closes_of(0x1001) == 1 && M.close_fn[0] == 0xc3, "late default handle closed once with fn 0xc3 (n=%d)", closes_of(0x1001));
	CHECK(CNT(late_open_captured) == 1, "late open captured (%u)", CNT(late_open_captured));
	common_tail(&D1, 1);
}
/* V02 = T10 shape with ledger: open-IN outstanding */
static void v02_in_open_late(void)
{
	void *o = enum_to(&D1, 4);
	detach(&D1);
	run_except(o);
	CHECK(D1.remove_completes == 0 && closes_of(0x1001) == 1, "ctrl closed, no ack while open-IN outstanding");
	complete_urb(o, 0);
	run_all();
	CHECK(closes_of(0x2182) == 1 && nclose_dev(1) == 2, "late IN handle 0x2182 closed once (total closes %d)", nclose_dev(1));
	common_tail(&D1, 1);
}
/* V03 open-OUT outstanding: ctrl + IN known, OUT arrives late */
static void v03_out_open_late(void)
{
	void *o = enum_to(&D1, 5);
	detach(&D1);
	run_except(o);
	CHECK(D1.remove_completes == 0 && closes_of(0x1001) == 1 && closes_of(0x2182) == 1, "ctrl+IN closed serially, no ack yet");
	complete_urb(o, 0);
	run_all();
	CHECK(closes_of(0x2102) == 1 && nclose_dev(1) == 3, "late OUT 0x2102 closed; 3 closes total (%d)", nclose_dev(1));
	CHECK(D1.add_completes == 0, "detached generation never reports AddComplete(0) (n=%d)", D1.add_completes);
	common_tail(&D1, 1);
}
/* V04 late open completes with FAILURE: owns nothing, nothing extra closed */
static void v04_late_open_fails(void)
{
	void *o = enum_to(&D1, 4);
	detach(&D1); run_except(o);
	complete_urb(o, 0xC0000001u); run_all();
	CHECK(nclose_dev(1) == 1 && CNT(late_open_captured) == 0, "failed late open: only ctrl closed (%d)", nclose_dev(1));
	common_tail(&D1, 1);
}
/* V05 late open completes WHILE the ctrl close is still in flight */
static void v05_open_during_close(void)
{
	void *o = enum_to(&D1, 4);
	detach(&D1);                               /* ctrl close accepted, pending */
	complete_urb(o, 0);                        /* open finishes first */
	CHECK(M.nclose == 1, "captured handle waits; one close in flight at a time (%d)", M.nclose);
	run_all();
	CHECK(closes_of(0x1001) == 1 && closes_of(0x2182) == 1, "both closed after serial chain");
	common_tail(&D1, 1);
}
/* V06 synchronous disconnect re-entered from INSIDE the open-IN submit, then
 * the open completes inline (inline completion after RemoveDevice) */
static int g_v06;
static int v06_reenter(void *urb)
{
	gdr_urb_header *h = urb;
	if (h->Function == 0x02 && !g_v06) { g_v06 = 1; detach(&D1); M.inline_all = 1; }
	return 0;
}
static void v06_remove_inside_open_submit(void)
{
	M.reenter_on_submit = v06_reenter;
	attach(&D1); run_all();                   /* S0..S3; S4 submit re-enters remove */
	M.reenter_on_submit = 0;
	run_all();
	CHECK(g_v06 == 1, "precondition: remove ran inside the open-IN submit");
	CHECK(closes_of(0x1001) == 1 && closes_of(0x2182) == 1, "ctrl + inline-late IN closed (ctrl=%d in=%d)", closes_of(0x1001), closes_of(0x2182));
	M.inline_all = 0;
	for (int i = 0; i < M.nclose; i++) if (M.close_h[i] == 0x2182) opened[nopened++] = 0x2182;
	common_tail(&D1, 1);
}
/* V07 close SUBMIT of the late-captured handle rejected -> quarantine */
static void v07_late_close_rejected(void)
{
	void *o = enum_to(&D1, 4);
	detach(&D1); run_except(o);
	reject_fn = 0x43; reject_after = 0;
	complete_urb(o, 0); run_all();
	CHECK(D1.remove_completes == 0 && ATT.failed == 3, "rejected close -> quarantine, no ack (failed=%u)", ATT.failed);
	attach(&D2); run_all();
	CHECK(D2.add_completes == 1 && D2.add_status < 0, "re-attach refused while quarantined");
	CHECK(M.freed_calls == 0, "no freed-device call");
}
/* V08 async close FAILURE of the late handle -> quarantine */
static void v08_late_close_fails(void)
{
	void *o = enum_to(&D1, 4);
	detach(&D1); run_except(o);
	complete_urb(o, 0);                        /* IN close submitted, pending */
	CHECK(M.npend == 1, "late close pending");
	complete_urb(M.pend[0].urb, 0xC0000001u);
	run_all();
	CHECK(D1.remove_completes == 0 && ATT.failed == 3 && ATT.close_in == 0x2182, "failed close keeps handle, quarantined, no ack");
	CHECK(M.freed_calls == 0, "no freed-device call");
}
/* V09 duplicate open completion after consumption: ignored, no double close */
static void v09_duplicate_open_completion(void)
{
	void *o = enum_to(&D1, 4);
	detach(&D1); run_except(o);
	complete_urb(o, 0); run_all();
	uint32_t st0 = CNT(stale_completions);
	mock_complete(o, 0);                       /* native duplicate (contract violation) */
	run_all();
	CHECK(CNT(stale_completions) == st0 + 1 && closes_of(0x2182) == 1, "duplicate open completion fenced (stale=%u)", CNT(stale_completions));
	common_tail(&D1, 1);
}
/* V10 partial setup: open-IN SUBMIT rejected (STEPFAIL), then remove */
static void v10_partial_setup_rejected(void)
{
	reject_fn = 0x02; reject_after = 0;
	attach(&D1); run_all();
	CHECK(D1.add_completes == 1 && D1.add_status < 0 && !own_any(), "rejected open -> AddComplete(<0), nothing owned");
	detach(&D1); run_all();
	CHECK(nclose_dev(1) == 1 && closes_of(0x1001) == 1, "only the default pipe closed (%d)", nclose_dev(1));
	common_tail(&D1, 1);
}
/* V11 ordinary reconnect x3 (native contract: IN retired by its close): every
 * cycle 3 closes then one ack, next generation LIVE -- no quarantine */
static struct fake_dev D3 = { .id = 3 }, D4 = { .id = 4 };
static void v11_three_cycles(void)
{
	struct fake_dev *d[4] = { &D1, &D2, &D3, &D4 };
	bring_up(d[0]);
	for (int c = 0; c < 3; c++) {
		int base = M.nclose;
		mock_in_frame(k_rel, 48); tick();
		detach(d[c]); run_all();
		CHECK(M.nclose - base == 3 && d[c]->remove_completes == 1, "cycle %d: 3 closes then 1 ack (%d,%d)", c, M.nclose - base, d[c]->remove_completes);
		bring_up(d[c + 1]);
		CHECK(d[c + 1]->add_completes == 1 && d[c + 1]->add_status == 0 && M.in_urb && M.in_dev == d[c + 1], "cycle %d: next generation LIVE with IN armed", c);
	}
	CHECK(CNT(retired_by_close) == 0 && CNT(stale_completions) == 0, "native-contract ordering: no retire-by-close, no stale (%u,%u)", CNT(retired_by_close), CNT(stale_completions));
	CHECK(rc_bad == 0 && M.freed_calls == 0 && ATT.failed == 0, "no audit/freed/quarantine");
}
/* V12 F5 isolated from F1: gen1 RELEASED, late gen1 IN carrying A arrives after
 * gen2 Attach (out-of-contract ordering) -> fenced, never published, accounting
 * intact; gen2 then streams normally */
static void v12_late_in_fenced(void)
{
	uint8_t st[22];
	bring_up(&D1); mock_in_frame(k_rel, 48); tick();
	M.late_in = 1; void *g1 = M.in_urb;
	detach(&D1); run_all();
	CHECK(D1.remove_completes == 1 && CNT(retired_by_close) == 1, "IN retired by its successful close (%u)", CNT(retired_by_close));
	attach(&D2); M.late_in = 0;
	gdr_urb_transfer *t = g1; memcpy((void *)(uintptr_t)t->TransferBuffer, k_a, 48); t->TransferLength = 48;
	uint32_t rx0 = ATT.rx_events;
	mock_complete(g1, 0);
	CHECK(CNT(stale_completions) == 1 && ATT.rx_events == rx0, "late gen1 IN fenced as stale (stale=%u rx %u->%u)", CNT(stale_completions), rx0, ATT.rx_events);
	run_all(); for (int i = 0; i < 3; i++) { tick(); run_all(); }
	uintptr_t h2 = open_port1(); uint32_t r = h2 ? getstate(h2, st) : 0x48F;
	CHECK(!(r == 0 && ST_A(st) == 255), "gen1 A never published on gen2 (r=0x%x A=%u)", r, ST_A(st));
	CHECK(ATT.pending == (uint32_t)(M.in_urb ? 1 : 0) + (uint32_t)M.npend, "gen2 pending honest (%u)", ATT.pending);
	mock_in_frame(k_a, 48); tick(); tick(); h2 = open_port1(); r = getstate(h2, st);
	CHECK(r == 0 && ST_A(st) == 255, "gen2 real input still flows (r=0x%x A=%u)", r, ST_A(st));
}
/* V13 F6 narrowing: RemoveDevice preempts between tx entry check and submit.
 * Modelled by detaching from inside the first gen OUT submit's re-entry hook is
 * not possible (submit already happening); instead verify no OUT submit is
 * issued for a detached ctx when the main loop services after a DPC remove. */
static void v13_no_out_after_remove(void)
{
	bring_up(&D1);
	int out0 = M.out_frames;
	gdr_tx_enqueue(&ATT, (const uint8_t *)"\x05\x20\x00\x01\x00", 5);
	detach(&D1);
	gdr_tx_submit_next(&ATT); tick(); run_all();
	CHECK(M.out_frames == out0, "no OUT submit after RemoveDevice (%d->%d)", out0, M.out_frames);
	common_tail(&D1, 1);
}

static const struct test V[] = {
	{"V01", "remove while default-pipe open outstanding; late success closed", v01_default_open_late},
	{"V02", "remove while open-IN outstanding (T10 + ledger)", v02_in_open_late},
	{"V03", "remove while open-OUT outstanding", v03_out_open_late},
	{"V04", "late open completes with failure", v04_late_open_fails},
	{"V05", "late open completes while ctrl close in flight", v05_open_during_close},
	{"V06", "remove re-entered inside open submit + inline completion", v06_remove_inside_open_submit},
	{"V07", "late-handle close submit rejected -> quarantine", v07_late_close_rejected},
	{"V08", "late-handle close fails async -> quarantine", v08_late_close_fails},
	{"V09", "duplicate open completion fenced", v09_duplicate_open_completion},
	{"V10", "partial setup (open submit rejected) then remove", v10_partial_setup_rejected},
	{"V11", "ordinary reconnect x3 not quarantined", v11_three_cycles},
	{"V12", "F5 late gen1 IN after gen2 attach fenced (released pad)", v12_late_in_fenced},
	{"V13", "F6 no OUT submit on detached ctx", v13_no_out_after_remove},
};

int main(int argc, char **argv)
{
	const char *only = argc > 1 ? argv[1] : 0;
	g_explicit = getenv("OGX_EXPLICIT_PUMP") && atoi(getenv("OGX_EXPLICIT_PUMP"));
	printf("work30 lifetime variants mode=%s\n", g_explicit ? "explicit-pump" : "stubs-only");
	int failed = 0, n = 0;
	for (unsigned i = 0; i < sizeof V / sizeof V[0]; i++) {
		if (only && strcmp(only, V[i].id)) continue;
		fflush(stdout);
		pid_t p = fork();
		if (p == 0) { printf("%s %s\n", V[i].id, V[i].what); init30(); V[i].fn(); fflush(stdout); _exit(g_fail ? 1 : 0); }
		int st = 0; waitpid(p, &st, 0);
		int bad = !WIFEXITED(st) || WEXITSTATUS(st) != 0;
		if (!WIFEXITED(st)) printf("    FAIL crashed (signal %d)\n", WTERMSIG(st));
		printf("  => %s %s\n", V[i].id, bad ? "RED" : "GREEN");
		failed += bad; n++;
	}
	printf("SUMMARY tests=%d red=%d green=%d\n", n, failed, n - failed);
	return failed ? 1 : 0;
}
