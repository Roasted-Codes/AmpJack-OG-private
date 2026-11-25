/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Module start. */
extern int ogx_module_main_flags(unsigned int flags);

/* W63: the cdecl argument is the loader's option word (bit0 = write log). */
__attribute__((section(".text.entry"), used))
int ogx_module_entry(unsigned int flags)
{
	return ogx_module_main_flags(flags);
}
