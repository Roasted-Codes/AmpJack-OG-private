#!/usr/bin/env python3
"""Apply the W63 source changes to the self-contained copy in ../src (idempotent guard:
refuses if a marker is already present). Each replacement must match exactly once."""
import re, sys
from pathlib import Path
S = Path(__file__).resolve().parents[1] / 'src/ogxbox'

def rep(path, old, new, count=1):
    p = S / path; t = p.read_text()
    n = t.count(old)
    assert n == count, (path, old[:60], n)
    p.write_text(t.replace(old, new))

if 'W63' in (S / 'gipdriver/src/gipdrive.h').read_text():
    sys.exit('already applied')

# ---- gipdrive.h: W1 announce re-handshake + counters -------------------------
rep('gipdriver/src/gipdrive.h', '    int  turned_off;\n};',
    '    int  turned_off;\n    u32  announces;             /* W63: every ANNOUNCE frame seen (any len)   */\n'
    '    u32  rehandshakes;          /* W63: wired re-handshakes started by ANNOUNCE */\n};')
rep('gipdriver/src/gipdrive.h',
'''static void gdr_rx_announce(struct gdr_gip *m, const u8 *data, u32 len) {
    u8 buf[64]; int n;
    if (len != 28) return;''',
'''static void gdr_rx_announce(struct gdr_gip *m, const u8 *data, u32 len) {
    u8 buf[64]; int n;
    m->announces++;                         /* W63: count BEFORE the len check */
    if (m->fallback && m->identified) {
        /* W63 (W1): a wired pad qualified at attach that later wakes and
         * ANNOUNCES got no reply before (identified already set), so it kept
         * flashing. Re-run the minimal wired startup: a fresh power-on now,
         * S-init on its successful OUT completion (gdr_gip_on_power_done).
         * The snapshot is kept; no timer, no periodic resend. */
        n = gdr_build_power_on(buf, gdr_next_seq(m));
        if (gdr_tx_send(m, buf, n)) m->s_init_pending = 1;
        m->ready = 1;
        m->rehandshakes++;
        m->did_announce = 1;
        return;
    }
    if (len != 28) return;''')

# ---- xinput_model.c: report both motors like a stock pad --------------------
rep('halo2/xinput_model.c',
'''	/* Rumble: NOT supported this milestone (no motors). Deliberately 0. */
	caps->Vibration.wLeftMotorSpeed  = 0;
	caps->Vibration.wRightMotorSpeed = 0;''',
'''	/* W63: rumble is forwarded to the GIP pad; report both motors like a
	 * stock pad. Whether Halo 2 gates rumble on caps is NOT known. */
	caps->Vibration.wLeftMotorSpeed  = 0xFFFF;
	caps->Vibration.wRightMotorSpeed = 0xFFFF;''')

# ---- ogx_present.h: per-port desired rumble (appended; existing offsets kept) -
p = S / 'integration/ogx_present.h'; t = p.read_text()
i = t.index('struct ogx_host_ctx {'); j = t.index('\n};', i)
t = t[:j] + ('\n\n\t/* W63 rumble: desired motor speeds (wLeft | wRight << 16) written by the\n'
             '\t * virtual XInputSetState, consumed by ogx_module_pump. Title thread only. */\n'
             '\tuint32_t rumble_want[OGX_MAX_PORTS];\n'
             '\tuint32_t rumble_calls;        /* virtual SetState calls accepted        */\n'
             '\tuint32_t rumble_hevent;       /* hEvent of the first call (never signalled) */\n'
             '\tuint32_t rumble_hevent_seen;') + t[j:]
p.write_text(t)

# ---- ogx_present.c: SetState stores desired rumble, completes immediately ----
rep('integration/ogx_present.c',
'''		/* Input-only milestone: there are NO motors, so rumble cannot
		 * actuate and we will not pretend otherwise. We never read the
		 * header bytes as motor speeds and never emit a GIP rumble
		 * command. Returning ERROR_NOT_SUPPORTED and writing it into
		 * Header.dwStatus (the XID output-completion gate) tells the title
		 * honestly that the rumble did NOT happen; hEvent is left
		 * untouched because no completion occurs. */
		fb->Header.dwStatus = OGX_ERR_NOT_SUPPORTED;
		return OGX_ERR_NOT_SUPPORTED;''',
'''		/* W63: store the desired motor speeds (Rumble at offset 66, never
		 * the header) for the port; ogx_module_pump sends ONE GIP rumble
		 * frame when the OUT path is idle (latest wins). The request is
		 * complete as far as the title can observe: dwStatus = SUCCESS,
		 * return ERROR_IO_PENDING (stock asynchronous semantics; the model
		 * is silent). hEvent is recorded, NOT signalled in this slice. */
		ctx->rumble_want[v->port] = (uint32_t)fb->Rumble.wLeftMotorSpeed |
		                            ((uint32_t)fb->Rumble.wRightMotorSpeed << 16);
		ctx->rumble_calls++;
		if (!ctx->rumble_hevent_seen) {
			ctx->rumble_hevent_seen = 1;
			ctx->rumble_hevent = fb->Header.hEvent;
		}
		fb->Header.dwStatus = OGX_ERR_SUCCESS;
		return OGX_ERR_IO_PENDING;''')
rep('integration/ogx_present.c', '#include "ogx_present.h"\n',
    '#include "ogx_present.h"\n\n#define OGX_ERR_IO_PENDING 997u   /* ERROR_IO_PENDING (W63 SetState) */\n')

# ---- ogx_module.h: entry takes flags ------------------------------------------
rep('integration/ogx_module.h', 'int  ogx_module_entry(void *unused);                    /* .text.entry           */',
    'int  ogx_module_entry(uint32_t flags);                  /* .text.entry, cdecl; bit0 = log */\n'
    'int  ogx_module_main_flags(uint32_t flags);             /* W63 */\n'
    'void ogx_log_gdc(uintptr_t dtype, uint32_t ins, uint32_t rem);           /* W63 stub logs */\n'
    'void ogx_log_xi(int open, uint32_t port, uintptr_t handle);')
rep('integration/crt0.c', '''extern int ogx_module_main(void);

__attribute__((section(".text.entry"), used))
int ogx_module_entry(void *unused)
{
	(void)unused;
	return ogx_module_main();
}''', '''extern int ogx_module_main_flags(unsigned int flags);

/* W63: the cdecl argument is the loader's option word (bit0 = write log). */
__attribute__((section(".text.entry"), used))
int ogx_module_entry(unsigned int flags)
{
	return ogx_module_main_flags(flags);
}''')
rep('integration/module_main.c', '#include "ogx_module.h"\n\nint ogx_module_main(void)\n{\n\tint rc;\n',
'''#include "ogx_module.h"
#include "ogx_log.h"

#ifndef OGX_BUILD_TAG
#define OGX_BUILD_TAG "W63-dev"
#endif

int ogx_module_main(void);
int ogx_module_main(void) { return ogx_module_main_flags(0); }

int ogx_module_main_flags(uint32_t flags)
{
	int rc;
	struct ogx_log_line l;

	ogx_log_init(flags);        /* memory only; the file opens lazily in the pump */
''')
rep('integration/module_main.c', '''	rc = ogx_install_hooks();
''', '''	rc = ogx_install_hooks();

	ogx_ll_begin(&l, "BOOT");
	ogx_ll_str(&l, "tag", OGX_BUILD_TAG);
	ogx_ll_hex(&l, "flags", flags);
	ogx_ll_hex(&l, "installed_hooks", ogx_g_module.installed_hooks);
	ogx_ll_dec(&l, "install_failed", ogx_g_module.install_failed);
	ogx_ll_dec(&l, "rc", (uint32_t)rc);
	ogx_ll_end(&l);
''')

# ---- ogx_stub.c: GDC / XIOPEN / XICLOSE log lines (title thread) -------------
rep('integration/ogx_stub.c', 'static int g_pump_depth;\n',
    'static int g_pump_depth;\n\nvoid ogx_log_gdc(uintptr_t dtype, uint32_t ins, uint32_t rem);\n'
    'void ogx_log_xi(int open, uint32_t port, uintptr_t handle);\n')
rep('integration/ogx_stub.c', '''	return ogx_XGetDeviceChanges(g_ctx, dtype, ins, rem);''',
'''	{
		uint32_t r = ogx_XGetDeviceChanges(g_ctx, dtype, ins, rem);
		if (ins && rem && (*ins | *rem))
			ogx_log_gdc(dtype, *ins, *rem);
		return r;
	}''')
rep('integration/ogx_stub.c', '''	return ogx_XInputOpen(g_ctx, dtype, port, slot, poll);''',
'''	{
		uintptr_t h = ogx_XInputOpen(g_ctx, dtype, port, slot, poll);
		ogx_log_xi(1, port, h);
		return h;
	}''')
rep('integration/ogx_stub.c', '''	ogx_transport_sync();
	ogx_XInputClose(g_ctx, handle);''', '''	ogx_transport_sync();
	ogx_log_xi(0, 0, handle);
	ogx_XInputClose(g_ctx, handle);''')

# ---- ogx_transport.c ----------------------------------------------------------
T = 'integration/ogx_transport.c'
rep(T, '#include "ogx_module.h"\n', '#include "ogx_module.h"\n#include "ogx_log.h"\n')
rep(T, 'struct ogx_module ogx_g_module;\n', '''struct ogx_module ogx_g_module;

/* ---- W63 diagnostics. The USB callbacks (DPC) ONLY increment these; every
 *      log line is formatted on the title thread. ---------------------------- */
static volatile uint32_t ogx_attach_calls, ogx_remove_calls, ogx_attach_refused;
static uint32_t ogx_rumble_sent;      /* last rumble value enqueued (l | r<<16) */
static uint32_t ogx_rumble_frames;    /* rumble frames enqueued                 */
static uint32_t ogx_rumble_logged, ogx_rumble_hev_logged;
static uint32_t ogx_l_att[5], ogx_l_att_valid;
static uint32_t ogx_l_in_seen, ogx_l_in_reports, ogx_l_in_ms;
static uint32_t ogx_l_cnt[10], ogx_l_cnt_ms, ogx_l_cnt_valid;
''')
rep(T, '''	uint8_t old;
	int span = ogx_span_enter(&old);
	ogx_attach_ran = 1;''', '''	uint8_t old;
	int span = ogx_span_enter(&old);
	ogx_attach_calls++;                              /* W63 counter only */
	ogx_attach_ran = 1;''')
rep(T, '''		 * enumeration instead of clobbering a live context. */
		ogx_g_module.att.add_complete''', '''		 * enumeration instead of clobbering a live context. */
		ogx_attach_refused++;                    /* W63 counter only */
		ogx_g_module.att.add_complete''')
rep(T, '''	int span = ogx_span_enter(&old);
	gdr_remove_device(''', '''	int span = ogx_span_enter(&old);
	ogx_remove_calls++;                              /* W63 counter only */
	gdr_remove_device(''')
rep(T, '''	ogx_seen_generation = g;
	ogx_stale_until''', '''	ogx_seen_generation = g;
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
	ogx_stale_until''')

rep(T, '''void ogx_transport_init(void)
{''', '''/* ---- W63 log helpers (title thread only) ---------------------------------- */
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
{''')

rep(T, '''	/* 1. lifecycle truth from the real generation, not from ring delivery */
	ogx_transport_sync();
''', '''	/* 1. lifecycle truth from the real generation, not from ring delivery */
	ogx_transport_sync();
	ogx_log_att();
''')
rep(T, '''		if (ev.kind == GDR_EVT_RX) {
			gdr_gip_rx(&ogx_g_module.gip, ev.data, (int)ev.len);
		} else if (ev.kind == GDR_EVT_TXDONE && ev.b == GIP_CMD_POWER &&
		           (long)(int)ev.a >= 0) {
			gdr_gip_on_power_done(&ogx_g_module.gip);
		} else if''', '''		if (ev.kind == GDR_EVT_RX) {
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
		} else if''')
rep(T, '''		if (ogx_g_module.att.state >= 6u && ogx_g_module.gip.gamepad == 0)
			gdr_gip_qualify_wired(&ogx_g_module.gip);  /* minimal power-on, S-init on done */
		gdr_gip_poll(&ogx_g_module.gip, now);
''', '''		if (ogx_g_module.att.state >= 6u && ogx_g_module.gip.gamepad == 0) {
			struct ogx_log_line l;
			gdr_gip_qualify_wired(&ogx_g_module.gip);  /* minimal power-on, S-init on done */
			ogx_ll_begin(&l, "QUAL");
			ogx_ll_dec(&l, "ready", (u32)ogx_g_module.gip.ready);
			ogx_ll_dec(&l, "s_init_pending", (u32)ogx_g_module.gip.s_init_pending);
			ogx_ll_end(&l);
		}
		gdr_gip_poll(&ogx_g_module.gip, now);
		ogx_rumble_service();
''')
rep(T, '''		while ((out_n = gdr_tx_drain(&ogx_g_module.gip, out_pkt, 64)) > 0)
			ogx_tx_locked(0, out_pkt, out_n);''', '''		while ((out_n = gdr_tx_drain(&ogx_g_module.gip, out_pkt, 64)) > 0) {
			struct ogx_log_line l;
			ogx_ll_begin(&l, "TX");
			ogx_ll_hex(&l, "cmd", out_pkt[0]);
			ogx_ll_dec(&l, "seq", out_pkt[2]);
			ogx_ll_dec(&l, "len", (u32)out_n);
			ogx_ll_end(&l);
			ogx_tx_locked(0, out_pkt, out_n);
		}''')
rep(T, '''	ogx_bridge_publish();
}''', '''	ogx_bridge_publish();

	/* W63: IN / RUMBLE / CNT lines, then the only file I/O (PASSIVE only) */
	ogx_log_periodic(ogx_log_ms());
	ogx_log_service();
}''')

# ---- build_pic.sh: compile + link ogx_log.c, build tag ------------------------
B = 'integration/build_pic.sh'
rep(B, '$CLANG $CFLAGS $INC -c module_main.c   -o out/module_main.o',
    '$CLANG $CFLAGS $INC -DOGX_BUILD_TAG=\\"${OGX_BUILD_TAG:-W63}\\" -c module_main.c   -o out/module_main.o\n'
    '$CLANG $CFLAGS $INC -c ogx_log.c       -o out/ogx_log.o')
rep(B, '    out/module_main.o out/trampoline.o', '    out/module_main.o out/ogx_log.o out/trampoline.o')
print('applied')
