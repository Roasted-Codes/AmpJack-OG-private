/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * module_main.c -- the REAL title-resident module entry (replaces the disabled
 * diagnostic). It wires the proven GIP USB transport (ogx_transport.c +
 * gipdrive.h) into the existing hardened virtual-XInput presentation
 * (ogx_present.c), then installs the six XInput E9 detours plus the
 * FindClassDriver class-match detour (ogx_install.c, build-bound + revertible).
 *
 * It does NOT boot, log, draw, or launch anything: ogx_module_entry() runs once
 * at title entry (before XInitDevices), and ogx_module_pump() is the per-tick
 * transport pump the loader borrows from a title loop hook. attached_mask starts
 * 0 and is raised ONLY when a real USB attach opens the interrupt IN endpoint.
 */
#include "ogx_module.h"
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

	/* wire the presentation ctx + transport seams + GIP class description.
	 * host pointers (ogx_g_module.host) were injected by the loader first. */
	ogx_transport_init();

	/* install the class-match detour + six XInput detours, build-bound.
	 * Refuses (rolls back) on wrong original bytes / missing required surface. */
	rc = ogx_install_hooks();

	ogx_ll_begin(&l, "BOOT");
	ogx_ll_str(&l, "tag", OGX_BUILD_TAG);
	ogx_ll_hex(&l, "flags", flags);
	ogx_ll_hex(&l, "installed_hooks", ogx_g_module.installed_hooks);
	ogx_ll_dec(&l, "install_failed", ogx_g_module.install_failed);
	ogx_ll_dec(&l, "rc", (uint32_t)rc);
	ogx_ll_end(&l);

	/* rc < 0 => fail-closed: no gamepad, stock classes untouched. rc == 0 =>
	 * hooks armed; a hotplug (pad present, or plugged after install) enumerates
	 * through our className driver and the six hooks serve virtual XInput. */
	return rc;
}
