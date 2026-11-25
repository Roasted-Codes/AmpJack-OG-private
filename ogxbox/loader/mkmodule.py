#!/usr/bin/env python3
"""Convert the linked static-PIE ELF into a stage-2 module file (H2S2 v1).

    python3 mkmodule.py build/diag.elf out/diag.bin

File = image [0, image_size) (struct h2s2_header at 0) + u32 relocation
offsets. Loader: alloc mem_size, read file to base, *(u32*)(base+off) += base
for each offset, zero [image_size, mem_size), call base+entry(host).
Refuses: anything but R_386_RELATIVE, text relocations, allocated sections
outside the image, a header not at 0.

Faithful re-statement of LAN_Stats trainer/stage2/mkmodule.py (GPL-3.0) so the
loader worker can build an independent diagnostic container.
Python 3 stdlib only.
"""
import struct
import sys
import zlib

R_386_RELATIVE = 8
HDR = struct.Struct('<12I')
DYNAMIC_ONLY = {'.dynamic', '.dynsym', '.dynstr', '.hash', '.gnu.hash', '.rel.dyn', '.rel.plt'}


def fail(msg):
    sys.exit(f'mkmodule: {msg}')


def parse(elf):
    if elf[:4] != b'\x7fELF' or elf[4] != 1 or elf[5] != 1:
        fail('not a 32-bit little-endian ELF')
    e_type, e_machine = struct.unpack_from('<HH', elf, 16)
    if e_machine != 3 or e_type != 3:
        fail(f'need EM_386 ET_DYN (static PIE), got machine {e_machine} type {e_type}')
    shoff, = struct.unpack_from('<I', elf, 32)
    shentsize, shnum, shstrndx = struct.unpack_from('<HHH', elf, 46)
    raw = [struct.unpack_from('<10I', elf, shoff + i * shentsize) for i in range(shnum)]
    strtab = raw[shstrndx]

    def name(off):
        b = elf[strtab[4] + off:]
        return b[:b.index(0)].decode()

    return [dict(name=name(s[0]), type=s[1], flags=s[2], addr=s[3], off=s[4],
                 size=s[5], link=s[6], entsize=s[9]) for s in raw]


def symbols(elf, secs):
    out = {}
    for s in secs:
        if s['type'] != 2:
            continue
        strs = secs[s['link']]
        for i in range(s['size'] // 16):
            st_name, value, size, info, other, shndx = struct.unpack_from(
                '<IIIBBH', elf, s['off'] + i * 16)
            b = elf[strs['off'] + st_name:]
            out[b[:b.index(0)].decode()] = value
    return out


def main():
    src, dst = sys.argv[1], sys.argv[2]
    elf = open(src, 'rb').read()
    secs = parse(elf)
    sym = symbols(elf, secs)
    for need in ('_image_end', '_end', 'h2s2_entry', 'h2s2_header'):
        if need not in sym:
            fail(f'symbol {need} missing (linker script link.ld?)')
    image_size, end = sym['_image_end'], sym['_end']
    if sym['h2s2_header'] != 0:
        fail('h2s2_header is not at offset 0')
    image = bytearray(image_size)
    relocs = []
    for s in secs:
        if s['name'] in ('.rel.dyn', '.rel.plt') and s['size']:
            for i in range(s['size'] // 8):
                off, info = struct.unpack_from('<II', elf, s['off'] + i * 8)
                if info & 0xFF != R_386_RELATIVE:
                    fail(f'relocation type {info & 0xff} at {off:#x}: only R_386_RELATIVE allowed')
                relocs.append(off)
        if s['name'] == '.dynamic':
            for i in range(s['size'] // 8):
                tag, val = struct.unpack_from('<iI', elf, s['off'] + i * 8)
                if tag == 22 or (tag == 30 and val & 4):  # DT_TEXTREL, DF_TEXTREL
                    fail('text relocations present')
        if not s['flags'] & 2 or s['name'] in DYNAMIC_ONLY or not s['size']:
            continue
        if s['type'] == 8:  # SHT_NOBITS
            if not (image_size <= s['addr'] and s['addr'] + s['size'] <= end):
                fail(f'{s["name"]} bss outside [image_end, end)')
            continue
        if s['addr'] + s['size'] > image_size:
            fail(f'{s["name"]} at {s["addr"]:#x}+{s["size"]:#x} lies outside the image')
        image[s['addr']:s['addr'] + s['size']] = elf[s['off']:s['off'] + s['size']]
    relocs.sort()
    for off in relocs:
        if off + 4 > image_size:
            fail(f'relocation {off:#x} outside the image')
    if len(set(relocs)) != len(relocs):
        fail('duplicate relocation offsets')
    file_size = image_size + 4 * len(relocs)
    mem_size = max(end, file_size)
    entry = sym['h2s2_entry']
    if not 0 < entry < image_size:
        fail('entry outside the image')
    magic, version = struct.unpack_from('<II', image, 0)
    if magic != 0x32533248 or version != 1:
        fail('crt0 header magic/version missing')
    fields = [magic, version, file_size, mem_size, image_size, entry, image_size,
              len(relocs), 0, 0, 0, 0]
    HDR.pack_into(image, 0, *fields)
    fields[8] = zlib.crc32(bytes(image)) & 0xFFFFFFFF
    HDR.pack_into(image, 0, *fields)
    out = bytes(image) + b''.join(struct.pack('<I', o) for o in relocs)
    open(dst, 'wb').write(out)
    print(f'{dst}: file {file_size} B, image {image_size} B, bss {end - image_size} B, '
          f'mem {mem_size} B, entry {entry:#x}, relocs {len(relocs)}, build_id {fields[8]:08x}')


if __name__ == '__main__':
    main()
