/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * f6_test.c -- work/32 F6 submit/remove window regressions.
 *
 * Links the PRODUCTION objects (ogx_transport.c, ogx_present.c, ogx_stub.c,
 * ogx_install.c, xinput_model.c + live gipdrive.h) and the work/28 SYNTHETIC
 * title doubles (native_mock.c, unmodified; harness reused by textual
 * inclusion with main renamed, as work/30 does). No guard logic is duplicated
 * here: the test only supplies
 *   - an IRQL double behind the two import SLOTS the module calls through
 *     (stdcall raise -> old in AL, fastcall lower(CL)), with kernel-like DPC
 *     deferral: a DPC requested at >= DISPATCH runs when KfLowerIrql drops
 *     below DISPATCH, otherwise it interrupts immediately;
 *   - a thiscall SubmitRequest wrapper that, at the native-call entry of an
 *     OUT URB (= after every module-side validity check), requests a USB
 *     removal DPC burst (RemoveDevice + all close completions -> RemoveComplete
 *     -> device freed). That is the F6 window.
 * Baseline (pre-work/32 integration) has no span: the burst interrupts and
 * the submit lands on the freed device (RED).
 */
#define main lifecycle28_main
#include "../../28-opus-controller-review/tests/lifecycle_test.c"
#undef main

#define TC  __attribute__((thiscall))
#define FC  __attribute__((fastcall))
typedef long (TC *t_submit)(void *, void *);
static t_submit real_submit;
#define ATT ogx_g_module.att

/* ---------------- IRQL double + DPC deferral ---------------------------- */
static uint8_t cur_irql;                       /* 0 PASSIVE, 2 DISPATCH */
static int n_raise, n_lower, irql_bad;
static uint8_t ret_stack[64]; static int ret_sp;
typedef void (*dpc_fn)(void);
static dpc_fn dq[8]; static int dqn, dpc_deferred, dpc_immediate;
static int seq, seq_submit_ret, seq_burst;
static dpc_fn pre_raise_dpc;                   /* fires just before a raise takes effect */

static void dpc_run(dpc_fn f)
{
	uint8_t save = cur_irql;
	cur_irql = 2;                              /* DPCs run at DISPATCH */
	f();
	cur_irql = save;
}
static void dpc_request(dpc_fn f)
{
	if (cur_irql >= 2) { if (dqn < 8) dq[dqn++] = f; dpc_deferred++; }
	else { dpc_immediate++; dpc_run(f); }
}
static uint8_t __attribute__((stdcall)) fk_raise(void)
{
	if (pre_raise_dpc) { dpc_fn f = pre_raise_dpc; pre_raise_dpc = 0; dpc_request(f); }
	uint8_t old = cur_irql;
	if (old > 2) irql_bad++;                   /* KeRaiseIrqlToDpcLevel above DISPATCH */
	n_raise++;
	if (ret_sp < 64) ret_stack[ret_sp++] = old;
	cur_irql = 2;
	return old;
}
static void FC fk_lower(uint8_t newirql)
{
	n_lower++;
	if (ret_sp <= 0 || ret_stack[--ret_sp] != newirql) irql_bad++;   /* unbalanced / wrong value */
	if (newirql > cur_irql) irql_bad++;
	cur_irql = newirql;
	while (cur_irql < 2 && dqn) {
		dpc_fn f = dq[0]; memmove(&dq[0], &dq[1], (size_t)(dqn - 1) * sizeof dq[0]); dqn--;
		dpc_run(f);
	}
}
/* the import SLOTS (title: 0x41B700 / 0x41B6FC) hold the resolved addresses */
static uint32_t slot_raise, slot_lower;

/* ---------------- SubmitRequest wrapper (F6 window) ---------------------- */
static int arm_out_race, reject_out, out_submits, out_irql_bad, out_on_d2;
static struct fake_dev *race_dev;
static dpc_fn race_dpc;
static int is_out(void *urb)
{
	gdr_urb_header *h = urb;
	return h->Function == 0x41 && ((gdr_urb_transfer *)urb)->FlagB0 == 1;
}
static long TC wrap_submit(void *self, void *urb)
{
	if (is_out(urb)) {
		out_submits++;
		if (cur_irql < 2) out_irql_bad++;
		if (self == &D2) out_on_d2++;
		if (arm_out_race && self == race_dev) {      /* window: after all checks, before native */
			arm_out_race = 0;
			dpc_request(race_dpc);
		}
		if (reject_out) { reject_out = 0; return (long)0xC0000001u; }
		long r = real_submit(self, urb);
		seq_submit_ret = ++seq;
		return r;
	}
	return real_submit(self, urb);
}

static void burst_remove_d1(void)
{
	seq_burst = ++seq;
	detach(&D1);
	mock_run();                                /* every close completes -> RemoveComplete */
}
static void burst_remove_d1_attach_d2(void)
{
	burst_remove_d1();
	attach(&D2);
	mock_run();                                /* gen2 enumerates to LIVE */
}
static void in_frame_dpc(void) { mock_in_frame(k_a, 48); }

static void init32(void)
{
	real_submit = (t_submit)(uintptr_t)ogx_g_module.host.submit_request;
	ogx_g_module.host.submit_request = (uint32_t)(uintptr_t)wrap_submit;
	slot_raise = (uint32_t)(uintptr_t)fk_raise;
	slot_lower = (uint32_t)(uintptr_t)fk_lower;
#ifdef OGX_HAS_IRQL_SPAN
	ogx_g_module.host.irql_raise_slot = (uint32_t)(uintptr_t)&slot_raise;
	ogx_g_module.host.irql_lower_slot = (uint32_t)(uintptr_t)&slot_lower;
#endif
}
/* attach + enumerate, then pump until OUT traffic is possible */
static void up_no_out(struct fake_dev *d) { attach(d); mock_run(); }
static int tick_until_out(int max)
{
	int before = out_submits;
	for (int i = 0; i < max && out_submits == before; i++) { tick(); }
	return out_submits - before;
}
static void balanced(void)
{
	CHECK(n_raise > 0, "the production path raised IRQL (raise=%d)", n_raise);
	CHECK(n_raise == n_lower && ret_sp == 0 && irql_bad == 0,
	      "every raise restored with its own old IRQL (raise=%d lower=%d open=%d bad=%d)", n_raise, n_lower, ret_sp, irql_bad);
	CHECK(cur_irql == 0 && dqn == 0, "back at PASSIVE, no DPC stranded (irql=%u queued=%d)", cur_irql, dqn);
}

/* F01 removal DPC between the last validity check and native OUT submit */
static void f01_remove_in_submit_window(void)
{
	up_no_out(&D1);
	race_dev = &D1; race_dpc = burst_remove_d1; arm_out_race = 1;
	tick_until_out(8);
	mock_run(); tick(); tick();
	CHECK(seq_burst != 0, "removal burst ran");
	CHECK(M.freed_calls == 0 && M.violations == 0, "no native call on the freed device (freed=%d viol=%d)", M.freed_calls, M.violations);
	CHECK(seq_burst > seq_submit_ret && dpc_deferred >= 1, "removal deferred until the submit span ended (burst#%d submit#%d deferred=%d)",
	      seq_burst, seq_submit_ret, dpc_deferred);
	CHECK(D1.remove_completes == 1, "RemoveComplete exactly once (%d)", D1.remove_completes);
	CHECK(ATT.tx_busy == 0 && ATT.pending == 0, "OUT ownership retired (tx_busy=%d pending=%u)", ATT.tx_busy, ATT.pending);
	CHECK(out_irql_bad == 0, "every OUT SubmitRequest issued at DISPATCH (bad=%d)", out_irql_bad);
	balanced();
}
/* F02 accepted submit completing INLINE inside the span */
static void f02_inline_completion(void)
{
	up_no_out(&D1);
	M.inline_all = 1;
	int n = tick_until_out(8);
	for (int i = 0; i < 4; i++) tick();
	CHECK(n > 0 && M.out_frames > 0, "OUT frames submitted and completed inline (%d)", M.out_frames);
	CHECK(ATT.tx_busy == 0 && ATT.tx_submit_fail == 0, "inline completion consumed ownership once (tx_busy=%d fail=%u)", ATT.tx_busy, ATT.tx_submit_fail);
	CHECK(out_irql_bad == 0, "inline re-submit chain stayed at DISPATCH (bad=%d)", out_irql_bad);
	CHECK(M.max_depth <= 1 + GDR_TX_SLOTS, "inline recursion bounded (depth=%d)", M.max_depth);
	balanced();
}
/* F03 SubmitRequest immediate rejection (source API error) */
static void f03_submit_rejected(void)
{
	up_no_out(&D1);
	reject_out = 1;
	tick_until_out(8);
	CHECK(ATT.tx_submit_fail == 1 && ATT.tx_busy == 0, "rejection surfaced, ownership dropped (fail=%u busy=%d)", ATT.tx_submit_fail, ATT.tx_busy);
	CHECK(out_irql_bad == 0, "rejected submit was inside the span");
	balanced();
	detach(&D1); mock_run();
	CHECK(D1.remove_completes == 1 && M.freed_calls == 0, "clean removal afterwards");
}
/* F04 removal + re-attach land after the pump's live check, before the span */
static void f04_revalidate_inside_span(void)
{
	up_no_out(&D1);
	for (int i = 0; i < 6; i++) { tick(); mock_run(); }    /* gen1 LIVE, startup OUT done */
	int nraise0 = n_raise;
	pre_raise_dpc = burst_remove_d1_attach_d2;           /* fires at the next raise entry */
	mock_in_frame(k_a, 48);
	ogx_module_pump();
	CHECK(seq_burst != 0 && n_raise > nraise0, "removal+re-attach interrupted the pump at the span entry");
	CHECK(out_on_d2 == 0, "no gen1 OUT work reached the gen2 device in that pump (%d)", out_on_d2);
	CHECK(ogx_module_status() & (1u << 16), "in-span revalidation refused (status bit16, status=%#x)", ogx_module_status());
	CHECK(M.freed_calls == 0 && M.violations == 0, "no native call on the freed device");
	for (int i = 0; i < 6; i++) { tick(); mock_run(); }
	CHECK(out_power_for(2) >= 1, "gen2 gets its own power-on on the next pumps (%d)", out_power_for(2));
	balanced();
}
/* F05 producer interleaving: an IN-data DPC requested while the title thread
 * is inside an inline OUT completion (title-side TXDONE push) is deferred, so
 * the two ring producers never overlap and nothing is lost. */
static void f05_ring_producers_serialized(void)
{
	up_no_out(&D1);
	for (int i = 0; i < 6; i++) { tick(); mock_run(); }
	M.inline_all = 1;
	uint32_t h0 = ogx_g_module.ring.head, ov0 = ogx_g_module.ring.overflow, rx0 = ATT.rx_events;
	gdr_tx_enqueue(&ATT, (const u8 *)"\x05\x20\x00\x01\x00", 5);   /* one queued OUT frame */
	race_dev = &D1; race_dpc = in_frame_dpc; arm_out_race = 1;
	ogx_module_pump();
	CHECK(dpc_deferred >= 1 && dpc_immediate == 0, "IN DPC deferred past the title-side producer span (def=%d imm=%d)", dpc_deferred, dpc_immediate);
	CHECK(ATT.rx_events == rx0 + 1, "IN frame delivered after the span (%u)", ATT.rx_events - rx0);
	CHECK(ogx_g_module.ring.overflow == ov0 && ogx_g_module.ring.head - h0 >= 2,
	      "ring: TXDONE + RX both recorded, no overflow (head +%u)", ogx_g_module.ring.head - h0);
	balanced();
}
/* F06 install refuses without both resolved IRQL import slots */
static void f06_install_requires_slots(void)
{
#ifdef OGX_HAS_IRQL_SPAN
	uint32_t zero = 0;
	ogx_g_module.host.irql_raise_slot = 0;
	int r1 = ogx_install_hooks();
	ogx_g_module.install_failed = 0;
	ogx_g_module.host.irql_raise_slot = (uint32_t)(uintptr_t)&slot_raise;
	ogx_g_module.host.irql_lower_slot = (uint32_t)(uintptr_t)&zero;     /* unresolved slot */
	int r2 = ogx_install_hooks();
	CHECK(r1 < 0 && r2 < 0 && ogx_g_module.install_failed == 1 && ogx_g_module.installed_hooks == 0,
	      "refused before any write (r1=%d r2=%d)", r1, r2);
#else
	CHECK(0, "baseline host ABI has no IRQL import slots");
#endif
}

static const struct { const char *id, *what; void (*fn)(void); } T32[] = {
	{"F01", "removal DPC inside validity->SubmitRequest window", f01_remove_in_submit_window},
	{"F02", "inline OUT completion inside span", f02_inline_completion},
	{"F03", "SubmitRequest rejection inside span", f03_submit_rejected},
	{"F04", "remove+reattach before span: in-span revalidation", f04_revalidate_inside_span},
	{"F05", "ring producers serialized (title TXDONE vs IN DPC)", f05_ring_producers_serialized},
	{"F06", "install refuses without IRQL import slots", f06_install_requires_slots},
};

int main(int argc, char **argv)
{
	const char *only = argc > 1 ? argv[1] : 0;
	g_explicit = getenv("OGX_EXPLICIT_PUMP") && atoi(getenv("OGX_EXPLICIT_PUMP"));
	printf("mode=%s\n", g_explicit ? "explicit-pump" : "stubs-only");
	int failed = 0, n = 0;
	for (unsigned i = 0; i < sizeof T32 / sizeof T32[0]; i++) {
		if (only && strcmp(only, T32[i].id)) continue;
		fflush(stdout);
		pid_t p = fork();
		if (p == 0) { printf("%s %s\n", T32[i].id, T32[i].what); harness_init(); init32(); T32[i].fn(); fflush(stdout); _exit(g_fail ? 1 : 0); }
		int st = 0; waitpid(p, &st, 0);
		int bad = !WIFEXITED(st) || WEXITSTATUS(st) != 0;
		if (!WIFEXITED(st)) printf("    FAIL crashed (signal %d)\n", WTERMSIG(st));
		printf("  => %s %s\n", T32[i].id, bad ? "RED" : "GREEN");
		failed += bad; n++;
	}
	printf("SUMMARY tests=%d red=%d green=%d\n", n, failed, n - failed);
	return failed ? 1 : 0;
}
