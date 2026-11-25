/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Module start. */
extern int ogx_module_main(void);

__attribute__((section(".text.entry"), used))
int ogx_module_entry(void *unused)
{
	(void)unused;
	return ogx_module_main();
}
