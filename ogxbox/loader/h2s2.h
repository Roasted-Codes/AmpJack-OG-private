/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * Minimal stage-2 module ABI for the OG Xbox loader. Faithful re-statement of the
 * LAN_Stats H2S2 v1 contract (trainer/stage2/h2s2.h) so +05-loader can build a
 * harmless diagnostic container independently, without copying the LAN_Stats module.
 *
 * A controller driver ships as a stage-2 payload because the XBMC trainer (.xbtf)
 * bootstrap is capped at 15193 decoded bytes (XBTF_HEAP_SIZE 15360 - 167-byte loader).
 * The bootstrap loads and relocates this larger freestanding module from
 * \Device\Harddisk0\Partition1\Trainers\<name>.bin at runtime.
 */
#ifndef OGX_LOADER_H2S2_H
#define OGX_LOADER_H2S2_H

#pragma GCC visibility push(hidden)

#include <stddef.h> /* size_t (clang builtin header: available even with -ffreestanding) */

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef int s32;
typedef unsigned long long u64;
typedef s32 NTSTATUS;

#define STDCALL __attribute__((stdcall))

#define H2S2_MAGIC    0x32533248u  /* "H2S2" */
#define H2S2_VERSION  1u

/* Module file header: offset 0 of the .bin AND of the loaded image.
 * mkmodule.py fills every field after linking. The C side only reserves it. */
struct h2s2_header {
    u32 magic;        /* "H2S2" */
    u32 version;      /* 1 */
    u32 file_size;    /* image + relocation table */
    u32 mem_size;     /* bytes the loader allocates (>= file_size; image + bss); < 4 MiB */
    u32 image_size;   /* loaded image [0, image_size); bss = [image_size, mem_size) */
    u32 entry;        /* offset of: int STDCALL entry(struct h2s2_host *) */
    u32 reloc_off;    /* file offset of the u32 relocation table (== image_size) */
    u32 reloc_count;  /* (file_size - reloc_off) / 4 */
    u32 build_id;     /* CRC-32 of the image with header fields 8..47 zero */
    u32 reserved[3];
};

/* Host table: lives in the bootstrap (.xbtf) image, persistent for the boot. */
#define H2S2_HOST_MAGIC 0x48533248u  /* "H2SH" */
struct h2s2_host {
    u32 magic;                   /* "H2SH" */
    u32 version;                 /* 1 */
    u8 *trainer;                 /* XBMC trainer-data header (the bootstrap's EBP) */
    u8 *module_base;             /* = our struct h2s2_header */
    u32 module_size;             /* bytes allocated (header.mem_size) */
    void (STDCALL *tick)(void);  /* set by the module; called every network_update */
    s32 entry_rc;                /* the bootstrap stores entry()'s return value here */
    u32 tsc_load;                /* low 32 bits of RDTSC when the loader started */
};

extern const struct h2s2_header h2s2_header;
int h2s2_main(struct h2s2_host *host);

#pragma GCC visibility pop
#endif
