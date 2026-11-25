/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Module start: the header at image offset 0 and the stdcall entry the bootstrap
 * calls once per load with EDI/ESI/EBX/EBP preserved (C ABI). The bootstrap has
 * already allocated mem_size bytes, read the file to offset 0, added the base to
 * every relocation-table offset, zeroed bss and filled the host table. */
#include "h2s2.h"

/* mkmodule.py locates this section at offset 0 and fills every field. */
__attribute__((section(".h2s2hdr"), used))
const struct h2s2_header h2s2_header = { .magic = H2S2_MAGIC, .version = H2S2_VERSION };

__attribute__((section(".text.entry"), used))
int STDCALL h2s2_entry(struct h2s2_host *host)
{
    if (!host || host->magic != H2S2_HOST_MAGIC || host->module_base != (u8 *)&h2s2_header)
        return -1;
    return h2s2_main(host);
}
