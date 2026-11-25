/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * ogx_log.h -- W63 opt-in on-console log file (E:\Trainers\AmpJack63.log).
 *
 * Contract: enabled only when the loader passes flags bit0 to the module entry.
 * Flag clear = zero file I/O. Lines are formatted into a 2 KiB module buffer by
 * TITLE-THREAD code only (pump + XInput stubs); DPC/USB callbacks never call
 * anything here (they only bump counters). File calls (NtCreateFile /
 * NtWriteFile / NtFlushBuffersFile / NtClose through the title's own kernel
 * import slots) happen ONLY in ogx_log_service(), called from the pump, and
 * only at PASSIVE_LEVEL. Any negative NTSTATUS turns logging off for the rest
 * of the title run. Hard cap 512 KiB, then one LOGFULL line.
 *
 * Hosted builds route the file calls through `struct ogx_log_io` (5 function
 * pointers) so tests can fake them; the tick comes from ogx_log_fake_tick.
 */
#ifndef OGX_LOG_H
#define OGX_LOG_H
#include <stdint.h>

#define OGX_LOG_BUF   2048u
#define OGX_LOG_CAP   (512u * 1024u)
#define OGX_LOG_PATH  "\\Device\\Harddisk0\\Partition1\\Trainers\\AmpJack63.log"

/* u803 kernel import slots (Pins._thunk_ordinal re-asserted by build.py) */
#define OGX_SLOT_NTCREATEFILE   0x0041B660u   /* ord 190 */
#define OGX_SLOT_NTWRITEFILE    0x0041B658u   /* ord 236 */
#define OGX_SLOT_NTFLUSHBUFFERS 0x0041B6B0u   /* ord 198 */
#define OGX_SLOT_NTCLOSE        0x0041B624u   /* ord 187 */
#define OGX_SLOT_KETICKCOUNT    0x0041B774u   /* ord 156: slot holds &KeTickCount */

#if __STDC_HOSTED__
struct ogx_log_io {
	long     (*create)(uint32_t *handle, const char *path, uint32_t access,
	                   uint32_t attrs, uint32_t share, uint32_t disp, uint32_t opts);
	long     (*write)(uint32_t handle, const void *buf, uint32_t len, uint32_t offset);
	long     (*flush)(uint32_t handle);
	long     (*close)(uint32_t handle);
	uint32_t (*irql)(void);
};
extern const struct ogx_log_io *ogx_log_io_hooks;
extern volatile uint32_t ogx_log_fake_tick;
#endif

enum { OGX_LS_OFF = 0, OGX_LS_PENDING = 1, OGX_LS_OPEN = 2, OGX_LS_DEAD = 3, OGX_LS_FULL = 4 };

struct ogx_log_state {
	uint32_t state;     /* OGX_LS_*                              */
	uint32_t off;       /* explicit file ByteOffset (bytes written) */
	uint32_t len;       /* bytes buffered                         */
	uint32_t dropped;   /* lines dropped (buffer full)            */
	uint32_t writes;    /* successful write+flush pairs           */
	uint32_t last_ms;   /* tick of the last write                 */
	long     last_rc;   /* last failing NTSTATUS (0 = none)       */
};
extern struct ogx_log_state ogx_log_st;

struct ogx_log_line { uint32_t n; char b[200]; };

void     ogx_log_init(uint32_t flags);
int      ogx_log_on(void);
uint32_t ogx_log_ms(void);
void     ogx_ll_begin(struct ogx_log_line *l, const char *tag);
void     ogx_ll_dec(struct ogx_log_line *l, const char *k, uint32_t v);
void     ogx_ll_hex(struct ogx_log_line *l, const char *k, uint32_t v);
void     ogx_ll_str(struct ogx_log_line *l, const char *k, const char *s);
void     ogx_ll_bytes(struct ogx_log_line *l, const char *k, const uint8_t *p, uint32_t n);
void     ogx_ll_end(struct ogx_log_line *l);
void     ogx_log_service(void);          /* pump only */

#endif /* OGX_LOG_H */
