/* SPDX-License-Identifier: GPL-3.0-or-later */
/* ogx_log.c -- see ogx_log.h. */
#include "ogx_log.h"
#include "../gipdriver/src/gipdrive.h"   /* gdr_str / gdr_dec / gdr_hex_u */

struct ogx_log_state ogx_log_st;
static uint32_t ogx_log_handle;
static char     ogx_log_buf[OGX_LOG_BUF];

#if __STDC_HOSTED__
const struct ogx_log_io *ogx_log_io_hooks;
volatile uint32_t ogx_log_fake_tick;

uint32_t ogx_log_ms(void) { return ogx_log_fake_tick; }
static uint32_t k_irql(void)
{
	return (ogx_log_io_hooks && ogx_log_io_hooks->irql) ? ogx_log_io_hooks->irql() : 0u;
}
static long k_create(uint32_t *h)
{
	if (!ogx_log_io_hooks || !ogx_log_io_hooks->create)
		return (long)(int)0xC0000001u;
	return ogx_log_io_hooks->create(h, OGX_LOG_PATH, 0x40100000u, 0x80u, 1u, 5u, 0x60u);
}
static long k_write(uint32_t h, const void *b, uint32_t n, uint32_t off)
{
	return ogx_log_io_hooks->write(h, b, n, off);
}
static long k_flush(uint32_t h) { return ogx_log_io_hooks->flush(h); }
static long k_close(uint32_t h) { return ogx_log_io_hooks->close(h); }
#else
#define OGX_ST __attribute__((stdcall))
typedef long (OGX_ST *nt_create_t)(uint32_t *, uint32_t, void *, void *, void *,
                                   uint32_t, uint32_t, uint32_t, uint32_t);
typedef long (OGX_ST *nt_write_t)(uint32_t, uint32_t, uint32_t, uint32_t, void *,
                                  const void *, uint32_t, void *);
typedef long (OGX_ST *nt_flush_t)(uint32_t, void *);
typedef long (OGX_ST *nt_close_t)(uint32_t);

/* resolved kernel thunk: a kernel VA, never the unresolved 0x8000xxxx ordinal */
static int slot_ok(uint32_t s) { return *(volatile uint32_t *)s >= 0x80010000u; }
#define SLOT(t, s) (*(t volatile *)(uintptr_t)(s))

uint32_t ogx_log_ms(void)
{
	uint32_t p;
	if (!slot_ok(OGX_SLOT_KETICKCOUNT))
		return 0;
	p = *(volatile uint32_t *)OGX_SLOT_KETICKCOUNT;
	return *(volatile uint32_t *)(uintptr_t)p;
}
static uint32_t k_irql(void)
{
	uint8_t v;
	__asm__ volatile("movb %%fs:0x24, %0" : "=q"(v));   /* KPCR.Irql */
	return v;
}
static long k_create(uint32_t *h)
{
	static const char path[] = OGX_LOG_PATH;
	volatile struct { uint16_t len, max; const char *s; } name;
	volatile struct { uint32_t root; volatile void *name; uint32_t attrs; } oa;
	volatile uint32_t io[2];
	if (!slot_ok(OGX_SLOT_NTCREATEFILE) || !slot_ok(OGX_SLOT_NTWRITEFILE) ||
	    !slot_ok(OGX_SLOT_NTFLUSHBUFFERS) || !slot_ok(OGX_SLOT_NTCLOSE))
		return (long)(int)0xC0000001u;
	name.len = sizeof(path) - 1; name.max = sizeof(path); name.s = path;
	oa.root = 0; oa.name = &name; oa.attrs = 0x40;          /* OBJ_CASE_INSENSITIVE */
	io[0] = io[1] = 0;
	/* GENERIC_WRITE|SYNCHRONIZE, AllocationSize 0, FILE_ATTRIBUTE_NORMAL,
	 * FILE_SHARE_READ, FILE_OVERWRITE_IF, NON_DIRECTORY|SYNCHRONOUS_IO_NONALERT */
	return SLOT(nt_create_t, OGX_SLOT_NTCREATEFILE)(h, 0x40100000u, (void *)&oa,
	                                                (void *)io, 0, 0x80u, 1u, 5u, 0x60u);
}
static long k_write(uint32_t h, const void *b, uint32_t n, uint32_t off)
{
	volatile uint32_t io[2] = { 0, 0 };
	volatile uint32_t pos[2] = { off, 0 };                  /* LARGE_INTEGER */
	return SLOT(nt_write_t, OGX_SLOT_NTWRITEFILE)(h, 0, 0, 0, (void *)io, b, n, (void *)pos);
}
static long k_flush(uint32_t h)
{
	volatile uint32_t io[2] = { 0, 0 };
	return SLOT(nt_flush_t, OGX_SLOT_NTFLUSHBUFFERS)(h, (void *)io);
}
static long k_close(uint32_t h) { return SLOT(nt_close_t, OGX_SLOT_NTCLOSE)(h); }
#endif

void ogx_log_init(uint32_t flags)
{
	memset(&ogx_log_st, 0, sizeof ogx_log_st);
	ogx_log_handle = 0;
	ogx_log_st.state = (flags & 1u) ? OGX_LS_PENDING : OGX_LS_OFF;
}

int ogx_log_on(void)
{
	return ogx_log_st.state == OGX_LS_PENDING || ogx_log_st.state == OGX_LS_OPEN;
}

void ogx_ll_begin(struct ogx_log_line *l, const char *tag)
{
	l->n = 0;
	if (!ogx_log_on())
		return;
	l->n = (uint32_t)gdr_dec(l->b, sizeof l->b, 0, ogx_log_ms());
	l->n = (uint32_t)gdr_str(l->b, sizeof l->b, l->n, " ");
	l->n = (uint32_t)gdr_str(l->b, sizeof l->b, l->n, tag);
}
static void ll_key(struct ogx_log_line *l, const char *k)
{
	l->n = (uint32_t)gdr_str(l->b, sizeof l->b, l->n, " ");
	l->n = (uint32_t)gdr_str(l->b, sizeof l->b, l->n, k);
	l->n = (uint32_t)gdr_str(l->b, sizeof l->b, l->n, "=");
}
void ogx_ll_dec(struct ogx_log_line *l, const char *k, uint32_t v)
{
	if (!l->n) return;
	ll_key(l, k);
	l->n = (uint32_t)gdr_dec(l->b, sizeof l->b, l->n, v);
}
void ogx_ll_hex(struct ogx_log_line *l, const char *k, uint32_t v)
{
	int nib = 1;
	if (!l->n) return;
	while (nib < 8 && (v >> (4 * nib))) nib++;
	if (nib & 1) nib++;
	ll_key(l, k);
	l->n = (uint32_t)gdr_str(l->b, sizeof l->b, l->n, "0x");
	l->n = (uint32_t)gdr_hex_u(l->b, sizeof l->b, l->n, v, nib);
}
void ogx_ll_str(struct ogx_log_line *l, const char *k, const char *s)
{
	if (!l->n) return;
	ll_key(l, k);
	l->n = (uint32_t)gdr_str(l->b, sizeof l->b, l->n, s);
}
void ogx_ll_bytes(struct ogx_log_line *l, const char *k, const uint8_t *p, uint32_t n)
{
	uint32_t i;
	if (!l->n) return;
	ll_key(l, k);
	for (i = 0; i < n; i++)
		l->n = (uint32_t)gdr_hex_u(l->b, sizeof l->b, l->n, p[i], 2);
}
void ogx_ll_end(struct ogx_log_line *l)
{
	if (!l->n || !ogx_log_on())
		return;
	if (l->n > sizeof l->b - 1)
		l->n = sizeof l->b - 1;
	l->b[l->n++] = '\n';
	if (ogx_log_st.len + l->n > OGX_LOG_BUF) {
		ogx_log_st.dropped++;
		return;
	}
	memcpy(ogx_log_buf + ogx_log_st.len, l->b, l->n);
	ogx_log_st.len += l->n;
}

static void log_dead(long rc)
{
	ogx_log_st.last_rc = rc;
	ogx_log_st.state = OGX_LS_DEAD;
	ogx_log_st.len = 0;
	if (ogx_log_handle) { k_close(ogx_log_handle); ogx_log_handle = 0; }
}

void ogx_log_service(void)
{
	struct ogx_log_state *s = &ogx_log_st;
	uint32_t now;
	int force = 0;
	long rc;

	if (!ogx_log_on())
		return;                                  /* flag clear: zero I/O */
	if (k_irql() != 0)
		return;                                  /* PASSIVE_LEVEL only   */
	if (s->state == OGX_LS_PENDING) {
		uint32_t h = 0;
		rc = k_create(&h);
		if (rc < 0) { log_dead(rc); return; }
		ogx_log_handle = h;
		s->state = OGX_LS_OPEN;
		force = 1;
	}
	if (!s->len)
		return;
	now = ogx_log_ms();
	if (!force && (uint32_t)(now - s->last_ms) < 1000u && s->len <= (OGX_LOG_BUF * 3u) / 4u)
		return;
	if (s->off + s->len > OGX_LOG_CAP - 64u) {
		struct ogx_log_line l;
		ogx_ll_begin(&l, "LOGFULL");
		ogx_ll_dec(&l, "bytes", s->off);
		ogx_ll_dec(&l, "dropped", s->dropped);
		l.b[l.n++] = '\n';
		rc = k_write(ogx_log_handle, l.b, l.n, s->off);
		if (rc >= 0) { s->off += l.n; k_flush(ogx_log_handle); }
		k_close(ogx_log_handle);
		ogx_log_handle = 0;
		s->len = 0;
		s->state = OGX_LS_FULL;
		return;
	}
	rc = k_write(ogx_log_handle, ogx_log_buf, s->len, s->off);
	if (rc < 0) { log_dead(rc); return; }
	rc = k_flush(ogx_log_handle);
	if (rc < 0) { log_dead(rc); return; }
	s->off += s->len;
	s->len = 0;
	s->last_ms = now;
	s->writes++;
}
