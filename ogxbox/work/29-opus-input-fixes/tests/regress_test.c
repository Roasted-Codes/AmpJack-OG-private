/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * regress_test.c -- work/29 focused regressions for the F1/F2/F3 fixes.
 * Same model as work/28 lifecycle_test.c: PRODUCTION ogx_transport.c,
 * ogx_present.c, ogx_stub.c, xinput_model.c + gipdrive.h (frozen) built -m32
 * with ASan/UBSan; only the title side is SYNTHETIC (work/28 native_mock.c,
 * linked unmodified). Each test forks (fresh BSS). Checks the RECOVERY side the
 * work/28 tests do not: removal edge still reported, old handles dead before
 * any XGetDeviceChanges, fresh-generation input works, fail-closed overflow
 * recovers on the next real report, ring index wrap.
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
uint32_t  SC ogx_stub_xinputgetcaps(uintptr_t, uintptr_t);
uint32_t  SC ogx_stub_xinputgetstate(uintptr_t, uintptr_t);
typedef void (SC *class_cb)(void *device);

static int g_fail;
#define CHECK(c, ...) do { if (c) printf("    ok   "); else { printf("    FAIL "); g_fail++; } printf(__VA_ARGS__); printf("\n"); } while (0)

static uint32_t k_gp_obj = 0xDEADBEEFu;
#define DTYPE ((uintptr_t)&k_gp_obj)
static uint8_t  k_stock[24] = { 0x58, 0x00 };
static uint32_t k_tab[6];
/* CAPTURED frame (work/20-runtime/E-gip-probe-button.log:595), released */
static const uint8_t k_rel[48] = {
 0x20,0x00,0xc0,0x2c,0x00,0x00,0x00,0x00,0x00,0x00,0xea,0xff,0xad,0xfd,0x8b,0x03,0xd4,0x03,
 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x20,0x8c,0xcd,0x1d,0xfd,0x8e,0xcd,0x1d };
static uint8_t k_a[48];   /* DERIVED: same frame + A bit */
static struct fake_dev D1 = { .id = 1 }, D2 = { .id = 2 };
static struct gdr_class_desc *g_desc;
static uint32_t g_ins, g_rem;

static void harness_init(void)
{
	memset(&M, 0, sizeof M);
	M.dtype_gamepad = DTYPE;
	k_tab[1] = (uint32_t)(uintptr_t)k_stock;
	ogx_g_module.host.submit_request    = mock_va_submit();
	ogx_g_module.host.add_complete      = mock_va_add();
	ogx_g_module.host.remove_complete   = mock_va_remove();
	ogx_g_module.host.class_table_begin = (uint32_t)(uintptr_t)&k_tab[0];
	ogx_g_module.host.class_table_end   = (uint32_t)(uintptr_t)&k_tab[6];
	ogx_g_module.host.xdevice_type_gamepad = (uint32_t)DTYPE;
	ogx_transport_init();
	g_desc = (struct gdr_class_desc *)ogx_findclassdriver(0xFF81u);
	memcpy(k_a, k_rel, sizeof k_a); k_a[4] |= 0x10;
}
static void tick(void) { g_ins = g_rem = 0; ogx_stub_xgetdevicechanges(DTYPE, &g_ins, &g_rem); }
static uint32_t gs(uintptr_t h, uint8_t *st) { memset(st, 0xEE, 22); return ogx_stub_xinputgetstate(h, (uintptr_t)st); }
static uint32_t pkt(const uint8_t *st) { uint32_t p; memcpy(&p, st, 4); return p; }
#define A(st) ((st)[6])
static void attach(struct fake_dev *d) { ((class_cb)(uintptr_t)g_desc->Attach)(d); }
static void detach(struct fake_dev *d) { ((class_cb)(uintptr_t)g_desc->RemoveDevice)(d); }
static void bring_up(struct fake_dev *d) { attach(d); mock_run(); for (int i = 0; i < 4; i++) { tick(); mock_run(); } }
static uintptr_t open1(void) { return ogx_stub_xinputopen(DTYPE, 1, 0, 0); }
static int power_for(int dev) { int n = 0; for (int i = 0; i < M.nout; i++) if (M.out_dev[i] == dev && M.out_log[i][0] == 0x05 && M.out_log[i][3] == 0x01) n++; return n; }
static void heldA(uintptr_t *h) { bring_up(&D1); mock_in_frame(k_a, 48); tick(); tick(); *h = open1(); tick(); }

/* ticks until the virtual port re-inserts; returns tick index of first rem and ins */
static void edges(int n, int *t_rem, int *t_ins, int *same)
{
	*t_rem = *t_ins = -1; *same = 0;
	for (int i = 0; i < n; i++) {
		tick(); mock_run();
		if ((g_rem & 2u) && *t_rem < 0) *t_rem = i;
		if ((g_ins & 2u) && *t_ins < 0) *t_ins = i;
		if ((g_rem & 2u) && (g_ins & 2u)) *same = 1;
	}
}

static void gen2_input_works(uintptr_t old)
{
	uint8_t st[22];
	uintptr_t h2 = open1();
	CHECK(h2 && h2 != old, "fresh gen2 handle issued (0x%lx)", (unsigned long)h2);
	uint32_t r = gs(h2, st);
	CHECK(r == 0 && A(st) == 0, "gen2 handle before gen2 input: connected, neutral (r=0x%x A=%u)", r, A(st));
	mock_in_frame(k_a, 48); tick(); mock_run();
	r = gs(h2, st); int16_t lx; memcpy(&lx, st + 14, 2);
	CHECK(r == 0 && A(st) == 255 && lx == -22, "real gen2 A press served on gen2 handle (r=0x%x A=%u lx=%d)", r, A(st), lx);
	mock_in_frame(k_rel, 48); tick(); mock_run(); gs(h2, st);
	CHECK(A(st) == 0, "real gen2 release served");
	r = gs(old, st);
	CHECK(r == OGX_ERR_NOT_CONNECTED, "gen1 handle still dead after gen2 input (r=0x%x)", r);
	CHECK(power_for(2) >= 1, "gen2 received its own GIP power-on (%d)", power_for(2));
	CHECK(M.freed_calls == 0, "no native call on freed device");
}

static void r01_fast_replug_recovery(void)
{
	uint8_t st[22], cap[64]; uintptr_t h; heldA(&h);
	detach(&D1); mock_run(); attach(&D2); mock_run();
	/* NO XGetDeviceChanges yet */
	uint32_t r = gs(h, st);
	CHECK(r == OGX_ERR_NOT_CONNECTED, "old handle NOT_CONNECTED before any XGetDeviceChanges (r=0x%x A=%u)", r, A(st));
	CHECK(ogx_stub_xinputgetcaps(h, (uintptr_t)cap) == OGX_ERR_NOT_CONNECTED, "old handle caps NOT_CONNECTED before XGetDeviceChanges");
	int tr, ti, same; edges(6, &tr, &ti, &same);
	CHECK(tr == 0, "game still receives the removal edge on its next XGetDeviceChanges (tick %d)", tr);
	CHECK(ti > tr && !same, "re-insertion reported strictly after removal (rem@%d ins@%d same=%d)", tr, ti, same);
	gen2_input_works(h);
}

static void r02_detach_only_edge_not_consumed(void)
{
	uint8_t st[22]; uintptr_t h; heldA(&h);
	detach(&D1); mock_run();
	CHECK(gs(h, st) == OGX_ERR_NOT_CONNECTED, "old handle dead immediately after RemoveDevice");
	tick();
	CHECK(g_rem & 2u, "removal edge reported by next XGetDeviceChanges (rem=0x%x)", g_rem);
	tick(); tick();
	int n0 = M.n_open; uintptr_t ho = ogx_stub_xinputopen(DTYPE, 1, 0, 0);
	int vh = ho >= (uintptr_t)&ogx_g_module.present.vh[0] && ho < (uintptr_t)&ogx_g_module.present.vh[OGX_HANDLE_ARENA];
	CHECK(!(g_ins & 2u) && !vh && M.n_open == n0 + 1, "no re-insertion; Open is not served virtually, chained to native (h=0x%lx)", (unsigned long)ho);
}

static void r03_overflow_drop_detach_recovery(void)
{
	uint8_t st[22]; uintptr_t h; heldA(&h);
	for (int i = 0; i < 200; i++) mock_in_frame(k_a, 48);
	detach(&D1); mock_run(); attach(&D2); mock_run();
	CHECK(gs(h, st) == OGX_ERR_NOT_CONNECTED, "old handle dead even though DETACH event was dropped (overflow=%u)", ogx_g_module.ring.overflow);
	int tr, ti, same; edges(6, &tr, &ti, &same);
	CHECK(tr == 0 && ti > tr && !same, "rem then ins despite dropped DETACH (rem@%d ins@%d)", tr, ti);
	gen2_input_works(h);
}

static void r04_overflow_release_fail_closed_then_recover(void)
{
	uint8_t st[22]; uintptr_t h; heldA(&h);
	gs(h, st); uint32_t p0 = pkt(st);
	for (int i = 0; i < 140; i++) mock_in_frame(k_a, 48);
	mock_in_frame(k_rel, 48);                      /* dropped */
	tick();
	uint32_t r = gs(h, st);
	CHECK(r == 0 && A(st) == 0 && st[14] == 0 && st[15] == 0, "after overflow: handle still connected, neutral (r=0x%x A=%u)", r, A(st));
	CHECK(pkt(st) != p0, "neutralization carries a new packet number (%u -> %u)", p0, pkt(st));
	CHECK(!(g_rem & 2u), "overflow alone does not fake a removal");
	tick(); gs(h, st);
	CHECK(A(st) == 0, "stays neutral while pad is idle (no resurrection of queued A)");
	mock_in_frame(k_a, 48); tick(); r = gs(h, st);
	CHECK(r == 0 && A(st) == 255, "next real report after overflow is served (A=%u)", A(st));
	mock_in_frame(k_rel, 48); tick(); gs(h, st);
	CHECK(A(st) == 0, "and its release");
}

static void r05_ring_index_wrap(void)
{
	/* empty ring placed just below u32 wrap (both producer/consumer indices
	 * equal, before any producer exists) to exercise the wrap-safe compares */
	ogx_g_module.ring.head = ogx_g_module.ring.tail = 0xFFFFFFF0u;
	uint8_t st[22]; uintptr_t h; heldA(&h);
	for (int i = 0; i < 40; i++) mock_in_frame(k_a, 48);
	detach(&D1); mock_run(); attach(&D2); mock_run();
	CHECK(gs(h, st) == OGX_ERR_NOT_CONNECTED, "old handle dead across index wrap (head=0x%x)", ogx_g_module.ring.head);
	int tr, ti, same; edges(6, &tr, &ti, &same);
	CHECK(tr == 0 && ti > tr, "edges across wrap (rem@%d ins@%d)", tr, ti);
	gen2_input_works(h);
}

static void r06_normal_path_unchanged(void)
{
	uint8_t st[22]; uintptr_t h; heldA(&h);
	uint32_t r = gs(h, st);
	CHECK(r == 0 && A(st) == 255, "normal held A served (no overflow, no replug)");
	uint32_t p1 = pkt(st); tick(); gs(h, st);
	CHECK(pkt(st) == p1 && A(st) == 255, "packet number stable without new report");
	mock_in_frame(k_rel, 48); tick(); gs(h, st);
	CHECK(A(st) == 0 && pkt(st) != p1, "release served with new packet number");
	CHECK(ogx_g_module.ring.overflow == 0, "no overflow on normal path");
}

struct test { const char *id, *what; void (*fn)(void); };
static const struct test T[] = {
	{"R01", "fast replug: old handle dead pre-XGDC, rem then ins, gen2 input", r01_fast_replug_recovery},
	{"R02", "detach only: handle dead at once, removal edge not consumed", r02_detach_only_edge_not_consumed},
	{"R03", "overflow drops DETACH: generation resync + gen2 recovery", r03_overflow_drop_detach_recovery},
	{"R04", "overflow drops release: fail closed, next real report recovers", r04_overflow_release_fail_closed_then_recover},
	{"R05", "ring index u32 wrap", r05_ring_index_wrap},
	{"R06", "normal path unchanged", r06_normal_path_unchanged},
};
int main(int argc, char **argv)
{
	const char *only = argc > 1 ? argv[1] : 0;
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
