/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * ogx_install.c -- build-bound, revertible E9 detour installer for the title.
 *
 * Installs the six XInput hooks (og_hook_sites.h) -> the six ogx_stub_x* entry
 * points, plus the FindClassDriver class-match hook @0x41517D -> ogx_findclassdriver.
 * Every site is guarded by the EXACT original 5 bytes it will overwrite
 * (VERIFIED against the frozen XBE by detour_plan.py + pin_u803.py); the site is
 * verified BEFORE the write, the E9 target is computed from the relocated module
 * symbol addresses (actual patch bytes/math, no text search), the write is
 * verified AFTER, and any partial failure restores the already-applied sites from
 * the saved original bytes (rollback). It is NOT presented as a 5-byte-atomic
 * patch: it is safe only because it runs at title entry, before XInitDevices
 * enumerates, on a single CPU/thread (see ogx_module.h).
 */
#include "ogx_module.h"
#include "../halo2/og_hook_sites.h"

/* the six hook entry points (ogx_stub.c) */
extern uint32_t  OGX_STDCALL ogx_stub_xgetdevicechanges(uintptr_t, uint32_t *, uint32_t *);
extern uintptr_t OGX_STDCALL ogx_stub_xinputopen(uintptr_t, uint32_t, uint32_t, uintptr_t);
extern void      OGX_STDCALL ogx_stub_xinputclose(uintptr_t);
extern uint32_t  OGX_STDCALL ogx_stub_xinputgetcaps(uintptr_t, uintptr_t);
extern uint32_t  OGX_STDCALL ogx_stub_xinputgetstate(uintptr_t, uintptr_t);
extern uint32_t  OGX_STDCALL ogx_stub_xinputsetstate(uintptr_t, uintptr_t);

/* the six hook entry point addresses in OGX_HOOK_SITES order */
static const uintptr_t g_xinput_hooks[OGX_HOOK_SITE_COUNT] = {
	(uintptr_t)&ogx_stub_xgetdevicechanges,
	(uintptr_t)&ogx_stub_xinputopen,
	(uintptr_t)&ogx_stub_xinputclose,
	(uintptr_t)&ogx_stub_xinputgetcaps,
	(uintptr_t)&ogx_stub_xinputgetstate,
	(uintptr_t)&ogx_stub_xinputsetstate,
};

/* u803 USBD_FindClassDriver detour site (VERIFIED: pin_u803.py) */
#define OGX_FC_VA 0x0041517Du
static const uint8_t OGX_FC_ORIG5[5] = { 0x56, 0xB8, 0xB4, 0x27, 0x41 };

/* ---- one 5-byte E9 site: verify -> write -> verify; 0 ok, <0 refused -------- */
static int ogx_patch_site(uint32_t va, const uint8_t *orig5, uintptr_t target)
{
	uint8_t patch[5];
	int32_t rel;
	int i;

	for (i = 0; i < 5; i++)
		if (*((volatile uint8_t *)(va + i)) != orig5[i])
			return -1;                       /* wrong build / already patched */

	patch[0] = 0xE9;
	rel = (int32_t)(target - (va + 5));
	patch[1] = (uint8_t)( rel        & 0xFF);
	patch[2] = (uint8_t)((rel >>  8) & 0xFF);
	patch[3] = (uint8_t)((rel >> 16) & 0xFF);
	patch[4] = (uint8_t)((rel >> 24) & 0xFF);

	for (i = 0; i < 5; i++)
		*((volatile uint8_t *)(va + i)) = patch[i];
	for (i = 0; i < 5; i++)
		if (*((volatile uint8_t *)(va + i)) != patch[i])
			return -2;                       /* write did not stick */
	return 0;
}

/* restore a site to its original 5 bytes (rollback) */
static void ogx_restore_site(uint32_t va, const uint8_t *orig5)
{
	int i;
	for (i = 0; i < 5; i++)
		*((volatile uint8_t *)(va + i)) = orig5[i];
}

/* ------------------------------------------------------------------------- */
/* install: returns 0 on success; non-zero fail-closed (partial rollback)    */
/* ------------------------------------------------------------------------- */
int ogx_install_hooks(void)
{
	int rc;
	int i;

	/* required injected surface BEFORE any write: without submit/add/remove/
	 * table/type the GIP device could be claimed but never driven or never
	 * dismissed/removed -> refuse to arm and leave every target byte untouched. */
	if (!ogx_g_module.host.submit_request ||
	    !ogx_g_module.host.add_complete ||
	    !ogx_g_module.host.remove_complete ||
	    !ogx_g_module.host.class_table_begin ||
	    !ogx_g_module.host.class_table_end ||
	    !ogx_g_module.host.xdevice_type_gamepad) {
		ogx_g_module.install_failed = 1;
		return -1;
	}

	/* 1. FindClassDriver class-match detour */
	rc = ogx_patch_site(OGX_FC_VA, OGX_FC_ORIG5, (uintptr_t)&ogx_findclassdriver);
	if (rc != 0) {
		ogx_g_module.install_failed = 1;
		return rc;
	}
	ogx_g_module.installed_hooks |= (1u << 7);

	/* 2. the six XInput hooks */
	for (i = 0; i < (int)OGX_HOOK_SITE_COUNT; i++) {
		uint32_t va = OGX_HOOK_SITES[i].va;
		rc = ogx_patch_site(va, OGX_HOOK_SITES[i].orig5, g_xinput_hooks[i]);
		if (rc != 0) {
			/* rollback the sites we already applied (incl. the FC detour) */
			int j;
			for (j = 0; j < i; j++)
				ogx_restore_site(OGX_HOOK_SITES[j].va, OGX_HOOK_SITES[j].orig5);
			ogx_restore_site(OGX_FC_VA, OGX_FC_ORIG5);
			ogx_g_module.installed_hooks = 0;
			ogx_g_module.install_failed = 1;
			return rc;
		}
		ogx_g_module.installed_hooks |= (1u << i);
	}

	return 0;
}
