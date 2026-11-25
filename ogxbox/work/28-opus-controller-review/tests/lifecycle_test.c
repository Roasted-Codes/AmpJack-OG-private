/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * lifecycle_test.c -- independent controller-lifetime / game-input safety tests
 * for the AmpJack-OG Halo 2 title module (work/28, Opus review).
 *
 * Links the PRODUCTION module objects compiled unmodified from SRC
 * (ogx_transport.c, ogx_present.c, ogx_stub.c, ../halo2/xinput_model.c,
 * ../gipdriver/src/gipdrive.h) for i386 (-m32): real __thiscall/__stdcall ABI,
 * real 32-bit VAs in ogx_g_module.host. Only the title side (USB stack +
 * native XInput) is SYNTHETIC (native_mock.c).
 *
 * Entry points exercised: ogx_findclassdriver (real FC hook) -> desc.Attach /
 * desc.RemoveDevice (stdcall class callbacks) -> URB completions -> service ->
 * ogx_stub_* (the six game-facing E9 targets). Each test runs in a fork()ed
 * child so the production singleton starts zeroed like BSS at load.
 *
 * Mode env OGX_EXPLICIT_PUMP=1 additionally calls ogx_module_pump() before
 * every game tick (only if that symbol exists). Default = stubs only, which is
 * what the title actually does (the brief requires pump wiring into the
 * game-called path).
 *
 * Adaptation point if the corrected source renames host fields / init:
 * harness_init() below. Nothing else touches module internals except the
 * documented read-only diagnostics (att.pending/att.lifecycle).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>
#include "native_mock.h"

#define SC __attribute__((stdcall))
uint32_t  SC ogx_stub_xgetdevicechanges(uintptr_t, uint32_t *, uint32_t *);
uintptr_t SC ogx_stub_xinputopen(uintptr_t, uint32_t, uint32_t, uintptr_t);
void      SC ogx_stub_xinputclose(uintptr_t);
uint32_t  SC ogx_stub_xinputgetcaps(uintptr_t, uintptr_t);
uint32_t  SC ogx_stub_xinputgetstate(uintptr_t, uintptr_t);
uint32_t  SC ogx_stub_xinputsetstate(uintptr_t, uintptr_t);
extern void ogx_module_pump(void) __attribute__((weak));
extern void ogx_transport_init(void) __attribute__((weak));
typedef void (SC *class_cb)(void *device);

static int g_fail, g_explicit;
#define CHECK(c, ...) do { if (c) { printf("    ok   "); } else { printf("    FAIL "); g_fail++; } printf(__VA_ARGS__); printf("\n"); } while (0)
#define INFO(...) do { printf("    info "); printf(__VA_ARGS__); printf("\n"); } while (0)

/* XDEVICE_TYPE is a POINTER identity (0x4127D8 on u803); host analogue */
static uint32_t k_xdevice_type_gamepad_obj = 0xDEADBEEFu;   /* content irrelevant */
static uint32_t k_xdevice_type_mu_obj      = 0x0u;
#define DTYPE   ((uintptr_t)&k_xdevice_type_gamepad_obj)
#define DTYPE_MU ((uintptr_t)&k_xdevice_type_mu_obj)

/* fake stock class table (FindClassDriver passthrough) */
static uint8_t  k_stock_xid_desc[24] = { 0x58, 0x00 };
static uint32_t k_class_table[6];

/* CAPTURED real frame: work/20-runtime/E-gip-probe-button.log line 595
 * (RX n=48 ... decoded STATE lx=-22 ly=-595 rx=907 ry=980, all released). */
static const uint8_t k_rel[48] = {
 0x20,0x00,0xc0,0x2c,0x00,0x00,0x00,0x00,0x00,0x00,0xea,0xff,0xad,0xfd,0x8b,0x03,0xd4,0x03,
 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x20,0x8c,0xcd,0x1d,0xfd,0x8e,0xcd,0x1d };
/* DERIVED: same captured frame with A (GIP button bit4, payload byte0 0x10). */
static uint8_t k_a[48];

static struct fake_dev D1 = { .id = 1 }, D2 = { .id = 2 };
static struct gdr_class_desc *g_desc;

static void harness_init(void)
{
	memset(&M, 0, sizeof M);
	M.dtype_gamepad = DTYPE;
	k_class_table[0] = 0; k_class_table[1] = (uint32_t)(uintptr_t)k_stock_xid_desc;
	ogx_g_module.host.submit_request    = mock_va_submit();
	ogx_g_module.host.findclassdriver   = 0x0041517Du;        /* never called by module */
	ogx_g_module.host.add_complete      = mock_va_add();
	ogx_g_module.host.remove_complete   = mock_va_remove();
	ogx_g_module.host.cancel_request    = 0;                  /* unused by close chain */
	ogx_g_module.host.class_table_begin = (uint32_t)(uintptr_t)&k_class_table[0];
	ogx_g_module.host.class_table_end   = (uint32_t)(uintptr_t)&k_class_table[6];
	ogx_g_module.host.xdevice_type_gamepad = (uint32_t)DTYPE;
	if (!ogx_transport_init) { printf("    FAIL no ogx_transport_init host seam\n"); exit(2); }
	ogx_transport_init();
	g_desc = (struct gdr_class_desc *)ogx_findclassdriver(0xFF81u);
	memcpy(k_a, k_rel, sizeof k_a); k_a[4] |= 0x10;
}

/* one title frame: (pump) + XGetDeviceChanges(gamepad), as Halo polls */
static uint32_t g_ins, g_rem, g_ins_acc, g_rem_acc;
static void tick(void)
{
	if (g_explicit && ogx_module_pump) ogx_module_pump();
	g_ins = g_rem = 0;
	ogx_stub_xgetdevicechanges(DTYPE, &g_ins, &g_rem);
	g_ins_acc |= g_ins; g_rem_acc |= g_rem;
}
static uint32_t getstate(uintptr_t h, uint8_t *st22) { memset(st22, 0xEE, 22); return ogx_stub_xinputgetstate(h, (uintptr_t)st22); }
#define ST_A(st) ((st)[6])

static void attach(struct fake_dev *d) { ((class_cb)(uintptr_t)g_desc->Attach)(d); }
static void detach(struct fake_dev *d) { ((class_cb)(uintptr_t)g_desc->RemoveDevice)(d); }

/* enumerate to live + let the game service until GIP startup OUT frames done */
static void bring_up(struct fake_dev *d)
{
	attach(d);
	mock_run();
	for (int i = 0; i < 4; i++) { tick(); mock_run(); }
}
static uintptr_t open_port1(void) { return ogx_stub_xinputopen(DTYPE, 1, 0, 0); }

static int out_power_for(int dev) { int n = 0; for (int i = 0; i < M.nout; i++) if (M.out_dev[i] == dev && M.out_log[i][0] == 0x05 && M.out_log[i][3] == 0x01) n++; return n; }

/* ---------------------------------------------------------------- tests */
static void t01_raw_to_xinput(void)
{
	uint8_t st[22];
	bring_up(&D1);
	CHECK(g_desc && g_desc->MatchByte0 == 0x81 && g_desc->MatchByte1 == 0xFF, "FindClassDriver(0xFF81) -> module GIP desc");
	CHECK(ogx_findclassdriver(0x0058u) == (uintptr_t)k_stock_xid_desc, "FindClassDriver stock class passthrough");
	CHECK(D1.add_completes == 1 && D1.add_status == 0, "AddComplete(self=dev,0) exactly once [%d,%ld]", D1.add_completes, D1.add_status);
	CHECK(out_power_for(1) >= 1, "GIP power-on OUT submitted via game-called service (%d OUT frames)", M.nout);
	uint32_t ins_seen = g_ins_acc;
	for (int i = 0; i < 3 && !(ins_seen & 2u); i++) { tick(); ins_seen |= g_ins; }
	mock_in_frame(k_a, 48);
	tick(); ins_seen |= g_ins;
	CHECK(ins_seen & 2u, "XGetDeviceChanges reports insertion on fixed virtual port index1 (ins=0x%x)", ins_seen);
	uintptr_t h = open_port1();
	CHECK(h && (h & 0xFF000000u) != 0x7A000000u, "XInputOpen(port1) returns module handle (0x%lx)", (unsigned long)h);
	tick();
	uint32_t r = getstate(h, st);
	int16_t lx; memcpy(&lx, st + 14, 2);
	CHECK(r == 0 && ST_A(st) == 255 && lx == -22, "captured raw frame -> published XInput A=255 lx=-22 (r=0x%x A=%u lx=%d)", r, ST_A(st), lx);
	mock_in_frame(k_rel, 48); tick(); getstate(h, st);
	CHECK(ST_A(st) == 0, "captured release frame -> A=0");
	CHECK(M.freed_calls == 0, "no native call on freed device");
}

static void heldA(uintptr_t *h)
{
	bring_up(&D1);
	mock_in_frame(k_a, 48); tick(); tick();
	*h = open_port1(); tick();
}

static void t02_heldA_remove_neutral(void)
{
	uint8_t st[22]; uintptr_t h; heldA(&h);
	getstate(h, st); CHECK(ST_A(st) == 255, "precondition: A held served");
	detach(&D1); mock_run();
	uint32_t rem = 0; for (int i = 0; i < 2; i++) { tick(); rem |= g_rem; }
	CHECK(rem & 2u, "removal edge on port1 (rem=0x%x)", rem);
	uint32_t r = getstate(h, st);
	CHECK(r == OGX_ERR_NOT_CONNECTED, "old handle -> DEVICE_NOT_CONNECTED (r=0x%x A=%u)", r, ST_A(st));
	CHECK(D1.remove_completes == 1, "RemoveComplete exactly once");
	CHECK(M.freed_calls == 0, "no native call on freed device after ack");
}

static void t03_remove_reattach_between_ticks(void)
{
	uint8_t st[22]; uintptr_t h; heldA(&h);
	detach(&D1); mock_run();          /* closes complete, ack */
	attach(&D2); mock_run();          /* gen2 enumerates live, no gen2 input yet */
	tick(); mock_run(); tick(); mock_run();
	uint32_t r = getstate(h, st);
	CHECK(!(r == 0 && ST_A(st) == 255), "gen1 held A NOT resurrected on old handle after fast replug (r=0x%x A=%u)", r, ST_A(st));
	CHECK(r == OGX_ERR_NOT_CONNECTED, "old-generation handle invalid after generation change (r=0x%x)", r);
	uintptr_t h2 = open_port1();
	if (h2 && h2 != h) { r = getstate(h2, st); CHECK(!(r == 0 && ST_A(st) == 255), "fresh handle shows no gen1 A before gen2 input (r=0x%x A=%u)", r, ST_A(st)); }
	CHECK(out_power_for(2) >= 1, "gen2 pad receives its own GIP power-on (%d)", out_power_for(2));
}

static void t04_overflow_drops_detach(void)
{
	uint8_t st[22]; uintptr_t h; heldA(&h);
	getstate(h, st); CHECK(ST_A(st) == 255, "precondition: A held served");
	for (int i = 0; i < 200; i++) mock_in_frame(k_a, 48);   /* title busy (load): no service */
	INFO("ring overflow counter=%u pending=%u", ogx_g_module.ring.overflow, ogx_g_module.ring.head - ogx_g_module.ring.tail);
	detach(&D1); mock_run(); attach(&D2); mock_run();
	for (int i = 0; i < 3; i++) { tick(); mock_run(); }
	uintptr_t h2 = open_port1();
	uint32_t r1 = getstate(h, st); int a1 = (r1 == 0 && ST_A(st) == 255);
	uint32_t r2 = h2 ? getstate(h2, st) : 0x48F; int a2 = (r2 == 0 && ST_A(st) == 255);
	CHECK(!a1 && !a2, "overflowed ring + dropped DETACH does not resurrect gen1 A on gen2 (old=%d new=%d)", a1, a2);
	CHECK(out_power_for(2) >= 1, "gen2 pad still receives GIP power-on after overflow (%d)", out_power_for(2));
}

static void t05_overflow_release_lost(void)
{
	uint8_t st[22]; uintptr_t h; heldA(&h);
	getstate(h, st); CHECK(ST_A(st) == 255, "precondition: A held served");
	for (int i = 0; i < 140; i++) mock_in_frame(k_a, 48);
	mock_in_frame(k_rel, 48);                 /* real release while ring full */
	for (int i = 0; i < 3; i++) tick();        /* pad idle afterwards (reports on change) */
	uint32_t r = getstate(h, st);
	CHECK(!(r == 0 && ST_A(st) == 255), "release arriving during ring overflow not lost -> A not stuck (A=%u, overflow=%u)", ST_A(st), ogx_g_module.ring.overflow);
}

static void t06_late_gen1_in_completion(void)
{
	uint8_t st[22]; uintptr_t h; heldA(&h);
	M.late_in = 1;                            /* native delivers gen1 IN completion late */
	void *gen1_in = M.in_urb;
	detach(&D1); mock_run();
	attach(&D2);                               /* gen2 S0 accepted, not yet completed */
	M.late_in = 0;
	if (gen1_in) { gdr_urb_transfer *t = gen1_in; memcpy((void *)(uintptr_t)t->TransferBuffer, k_a, 48); t->TransferLength = 48; M.in_urb = 0; mock_complete(t, 0); }
	mock_run();
	for (int i = 0; i < 3; i++) { tick(); mock_run(); }
	uintptr_t h2 = open_port1();
	uint32_t r = h2 ? getstate(h2, st) : 0x48F;
	CHECK(!(r == 0 && ST_A(st) == 255), "late gen1 IN data never published as gen2 input (r=0x%x A=%u)", r, ST_A(st));
	uint32_t expect = M.in_urb ? 1u : 0u;      /* only gen2's armed IN may be pending */
	CHECK(ogx_g_module.att.pending == expect + (uint32_t)M.npend, "gen2 pending accounting not corrupted by gen1 completion (pending=%d expect=%u)", (int)ogx_g_module.att.pending, expect + (uint32_t)M.npend);
}

static void t07_three_closes_before_ack(void)
{
	uintptr_t h; heldA(&h); (void)h;
	int base = M.nclose;
	detach(&D1);
	int ok_seq = 1;
	for (int k = 0; k < 3; k++) {
		ok_seq &= (M.nclose - base == k + 1) && D1.remove_completes == 0;
		mock_step();
	}
	CHECK(ok_seq, "one close in flight at a time, no RemoveComplete before third close completes");
	CHECK(M.nclose - base == 3 && M.close_fn[base] == 0xc3 && M.close_fn[base+1] == 0x43 && M.close_fn[base+2] == 0x43,
	      "closes = default(0xc3), IN(0x43), OUT(0x43) [n=%d]", M.nclose - base);
	CHECK(M.close_h[base] == 0x1001 && M.close_h[base+1] == 0x2182 && M.close_h[base+2] == 0x2102, "close handles are gen1 ctrl/IN/OUT");
	CHECK(D1.remove_completes == 1 && D1.closes_at_rc == 3, "RemoveComplete once, after 3 closes (closes_at_rc=%d)", D1.closes_at_rc);
	CHECK(M.freed_calls == 0, "no native call on freed device");
}

static void t08_close_failure_quarantine(void)
{
	uintptr_t h; heldA(&h); (void)h;
	detach(&D1); mock_step();
	void *u = M.pend[0].urb; M.npend = 0; mock_complete(u, 0xC0000001u);  /* IN close fails */
	mock_run();
	CHECK(D1.remove_completes == 0, "failed close => no RemoveComplete (quarantine)");
	attach(&D2); mock_run();
	CHECK(D2.add_completes == 1 && D2.add_status < 0, "re-attach while quarantined refused with AddComplete(<0) [%d,%ld]", D2.add_completes, D2.add_status);
	CHECK(M.freed_calls == 0, "no native call on freed device");
}

static void t09_duplicate_and_inline(void)
{
	uintptr_t h; heldA(&h); (void)h;
	M.inline_all = 1;
	detach(&D1); detach(&D1);
	CHECK(D1.remove_completes == 1 && D1.closes_at_rc == 3, "inline close completions + duplicate remove: 3 closes, 1 ack");
	mock_complete(&ogx_g_module.att.close_urb, 0);    /* duplicate close completion */
	detach(&D1);
	CHECK(D1.remove_completes == 1 && M.freed_calls == 0, "late duplicate close completion / third remove ignored, no freed-device call");
	attach(&D2); tick(); tick();
	CHECK(D2.add_completes == 1 && D2.add_status == 0, "inline-completing re-enumeration reaches AddComplete(0) once [%d,%ld]", D2.add_completes, D2.add_status);
	M.inline_all = 0;
}

static void t10_remove_during_enum_open_inflight(void)
{
	attach(&D1);
	for (int i = 0; i < 4; i++) mock_step();   /* S0c,S1,S2,S3 done; S4 open-IN accepted, pending */
	int inflight = M.npend;
	void *open_urb = inflight ? M.pend[0].urb : 0;
	detach(&D1);
	/* native completes the close chain first, the outstanding open later */
	for (int k = 0; k < 8; k++) {
		int j = 0; while (j < M.npend && M.pend[j].urb == open_urb) j++;
		if (j >= M.npend) break;
		void *u = M.pend[j].urb;
		memmove(&M.pend[j], &M.pend[j + 1], (size_t)(M.npend - j - 1) * sizeof M.pend[0]); M.npend--;
		mock_complete(u, 0);
	}
	int premature = D1.remove_completes;
	mock_run();
	CHECK(inflight == 1, "precondition: open-IN URB accepted and outstanding (%d)", inflight);
	CHECK(premature == 0, "RemoveComplete NOT signalled while an accepted open-endpoint URB is still outstanding (rc=%d)", premature);
	int closed_in = 0; for (int i = 0; i < M.nclose; i++) if (M.close_h[i] == 0x2182) closed_in++;
	CHECK(D1.remove_completes == 0 || closed_in == 1, "endpoint opened by the outstanding URB is closed before/at ack (closed_in=%d rc=%d)", closed_in, D1.remove_completes);
	CHECK(M.freed_calls == 0, "no native call on freed device (%d)", M.freed_calls);
}

static void t11_native_slot_passthrough(void)
{
	uint8_t st[22];
	M.native_ins = 0x3u;                       /* stock pads on port0 AND fixed slot1 */
	tick();
	CHECK(g_ins == 0x3u, "native insertions passed through unchanged (ins=0x%x)", g_ins);
	bring_up(&D1); mock_in_frame(k_a, 48);
	uint32_t vins = 0; for (int i = 0; i < 3; i++) { tick(); vins |= g_ins; }
	CHECK(vins == 0, "virtual pad suppressed while native owns port1 (ins=0x%x)", vins);
	int n0 = M.n_open; uintptr_t h = open_port1();
	CHECK(M.n_open == n0 + 1 && M.open_port == 1 && (h & 0xFF000000u) == 0x7A000000u, "XInputOpen(port1) chained to native (h=0x%lx)", (unsigned long)h);
	uint32_t r = getstate(h, st);
	int pattern = 1; for (int i = 0; i < 22; i++) pattern &= st[i] == 0x5A;
	CHECK(r == 0 && M.getstate_handle == h && pattern, "native GetState chained, native buffer not overwritten by virtual state");
	ogx_stub_xinputclose(h);
	CHECK(M.n_close == 1 && M.close_handle == h, "native XInputClose chained");
	M.mu_ins = 0x4u; uint32_t mi = 0, mr = 0;
	uint32_t before = ogx_g_module.present.native_connected_mask;
	ogx_stub_xgetdevicechanges(DTYPE_MU, &mi, &mr);
	CHECK(mi == 0x4u && mr == 0 && ogx_g_module.present.native_connected_mask == before, "non-gamepad dtype passthrough, gamepad mask untouched");
	M.native_rem = 0x2u; tick();
	CHECK(g_rem == 0x2u && !(g_ins & 2u), "native removal emitted alone (no same-call virtual ins) rem=0x%x ins=0x%x", g_rem, g_ins);
	tick();
	CHECK(g_ins & 2u, "virtual pad appears one tick after native vacates port1");
}

static void t12_virtual_to_native_takeover(void)
{
	uint8_t st[22]; uintptr_t h; heldA(&h);
	M.native_ins = 0x2u; tick();
	uint32_t ins = g_ins, rem = g_rem;
	uint32_t r = getstate(h, st);
	CHECK(r == OGX_ERR_NOT_CONNECTED, "virtual handle dead when stock pad takes port1");
	if ((ins & 2u) && (rem & 2u))
		INFO("PLAUSIBLE: same call reports ins AND rem for port1 (ins=0x%x rem=0x%x); title handling order unverified", ins, rem);
	else
		INFO("takeover emits separated edges ins=0x%x rem=0x%x", ins, rem);
}

static int g_reent;
static int reenter(void *urb)
{
	uint8_t st[22];
	gdr_urb_transfer *t = (gdr_urb_transfer *)urb;
	if (t->Hdr.Function != 0x41 || t->FlagB0 != 1) return 0;   /* only service-path OUT submits */
	if (g_reent++ > 4) return 0;
	ogx_stub_xinputgetstate(0x7A000111u, (uintptr_t)st);   /* title re-enters the API (SYNTHETIC) */
	uint32_t i, r; ogx_stub_xgetdevicechanges(DTYPE, &i, &r);
	return 1;
}
static void t13_service_reentry_bounded(void)
{
	uintptr_t h; heldA(&h); (void)h;
	M.max_depth = 0; M.reenter_on_submit = reenter; g_reent = 0;
	/* DERIVED from captured status RX 03 20 a8 04 83 01 00 00 with ACK option
	 * (0x10) set: forces an OUT (ACK) submit from the service path */
	static const uint8_t k_status_ack[8] = { 0x03, 0x30, 0xa9, 0x04, 0x83, 0x01, 0x00, 0x00 };
	mock_in_frame(k_status_ack, 8);
	for (int i = 0; i < 300; i++) mock_in_frame(k_a, 48);
	uint32_t pend0 = ogx_g_module.ring.head - ogx_g_module.ring.tail;
	tick(); mock_run(); tick();
	M.reenter_on_submit = 0;
	CHECK(g_reent > 0, "precondition: a service-issued OUT submit re-entered the game API (%d)", g_reent);
	CHECK(M.max_depth <= 1, "API re-entry from inside a service-issued SubmitRequest does not nest service (max submit depth=%d)", M.max_depth);
	CHECK(ogx_g_module.ring.head - ogx_g_module.ring.tail < pend0 || pend0 == 0, "service drains ring (pending %u -> %u), bounded and non-blocking", pend0, ogx_g_module.ring.head - ogx_g_module.ring.tail);
}

static void t14_inline_in_stream(void)
{
	M.inline_in = 1; M.inline_in_budget = 1;   /* native completes an IN submit inline once */
	bring_up(&D1);
	int armed = M.in_urb != 0;
	INFO("EMULATOR/NATIVE-DEPENDENT: after one inline IN completion the IN pipe is %s (in_flight=%d)", armed ? "re-armed" : "NOT re-armed (stream stops)", (int)ogx_g_module.att.in_flight);
}

static void t15_budget(void)
{
	INFO("sizeof(struct ogx_module)=%u ring=%u evt=%u att=%u gip=%u present=%u (64MiB=%u)",
	     (unsigned)sizeof(struct ogx_module), (unsigned)sizeof(struct gdr_ring), (unsigned)sizeof(struct gdr_evt),
	     (unsigned)sizeof(struct gdr_attach_ctx), (unsigned)sizeof(struct gdr_gip), (unsigned)sizeof(struct ogx_host_ctx), 64u << 20);
	CHECK(sizeof(struct ogx_module) < 64u * 1024u, "static module state < 64KiB (no heap)");
}

struct test { const char *id, *what; void (*fn)(void); };
static const struct test T[] = {
	{"T01", "raw captured input -> published XInput", t01_raw_to_xinput},
	{"T02", "held-A removal -> neutral, dead handle", t02_heldA_remove_neutral},
	{"T03", "remove+reattach between game ticks (gen change)", t03_remove_reattach_between_ticks},
	{"T04", "ring overflow drops DETACH, then replug", t04_overflow_drops_detach},
	{"T05", "ring overflow drops release (stuck A)", t05_overflow_release_lost},
	{"T06", "late gen1 IN completion after gen2 attach [PLAUSIBLE ordering]", t06_late_gen1_in_completion},
	{"T07", "three successful closes before RemoveComplete", t07_three_closes_before_ack},
	{"T08", "close failure quarantines, no ack", t08_close_failure_quarantine},
	{"T09", "duplicate remove / inline completions", t09_duplicate_and_inline},
	{"T10", "remove while open-endpoint URB outstanding", t10_remove_during_enum_open_inflight},
	{"T11", "native-owned slot suppression + passthrough", t11_native_slot_passthrough},
	{"T12", "virtual->native takeover", t12_virtual_to_native_takeover},
	{"T13", "service re-entry serialized/bounded", t13_service_reentry_bounded},
	{"T14", "inline IN completion [INFO]", t14_inline_in_stream},
	{"T15", "memory budget", t15_budget},
};

int main(int argc, char **argv)
{
	const char *only = argc > 1 ? argv[1] : 0;
	g_explicit = getenv("OGX_EXPLICIT_PUMP") && atoi(getenv("OGX_EXPLICIT_PUMP"));
	printf("mode=%s pump_symbol=%s transport_init=%s\n", g_explicit ? "explicit-pump" : "stubs-only",
	       ogx_module_pump ? "present" : "absent", ogx_transport_init ? "present" : "absent");
	int failed = 0, n = 0;
	for (unsigned i = 0; i < sizeof T / sizeof T[0]; i++) {
		if (only && strcmp(only, T[i].id)) continue;
		fflush(stdout);
		pid_t p = fork();
		if (p == 0) { printf("%s %s\n", T[i].id, T[i].what); harness_init(); T[i].fn(); fflush(stdout); _exit(g_fail ? 1 : 0); }
		int st = 0; waitpid(p, &st, 0);
		int bad = !WIFEXITED(st) || WEXITSTATUS(st) != 0;
		if (!WIFEXITED(st)) printf("    FAIL crashed (signal %d)\n", WTERMSIG(st));
		printf("  => %s %s\n", T[i].id, bad ? "RED" : "GREEN");
		failed += bad; n++;
	}
	printf("SUMMARY tests=%d red=%d green=%d\n", n, failed, n - failed);
	return failed ? 1 : 0;
}
