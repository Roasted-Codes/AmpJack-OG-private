"""ETM / XBTF trainer container helpers (stdlib only).

Format facts come from XBMC4Xbox source (Rocky5/XBMC4Xbox @ 921f9fe9):
  xbmc/utils/Trainer.cpp  CTrainer::Load / GetTitleIds   (header offsets, XBTF unmangle)
  xbmc/Util.cpp           CUtil::InstallTrainer + trainerloaderdata[] (runtime loader)
See references/xbmc-trainer-format.md for the full write-up.

Header of the *trainer data* (ETM file start, or XBTF data after key+scroller):
  0x00 u32  total size (Yelo15: == file size; not read by XBMC)
  0x04 u16  1          (meaning unknown; not read by XBMC)
  0x06 u32  code start (Yelo15: 0x23; not read by XBMC)
  0x0A u32  offset of option-state bytes (one byte per option, 0/1)
  0x0E u32  offset of text-pointer table: [name, info, label0, label1, ..., 0]
  0x12 u32  offset of title-ID list (3 x u32)
  0x16 u32  ETM / converted-ETM: entry offset.  real XBTF: XBTF_Section offset
  0x1A u32  ETM: must be 0.  real XBTF: entry offset
"""
import re
import struct

HDR_SIZE = 0x1E
LOADER_SIZE = 167            # trainerloaderdata[] in Util.cpp
ETM_HEAP_SIZE = 2400         # Util.cpp ETM_HEAP_SIZE
XBTF_HEAP_SIZE = 15360       # Util.cpp XBTF_HEAP_SIZE
# sm_bus, patch_it, hookit, igk_main, then hook_igk_toy (76 B) but Util.cpp:1012 advances
# by sizeof(igk_main_toy)=403, then the larger LCD toy (378 B): 1308 bytes after the data.
XBTF_TOYS_SIZE = 48 + 33 + 43 + 403 + 403 + 378
PAGE = 4096
LABEL_MAX = 84               # Trainer.cpp copies labels with strcpy into char temp[85]


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


# ---------------------------------------------------------------- XBTF mangling
def xbtf_unmangle(raw):
    """Exact port of the __asm block in CTrainer::Load (Trainer.cpp)."""
    b = bytearray(raw)
    s = (b[0x27] + b[0x2F] + b[0x37]) & 0xFF          # add al,[esi+27h/2Fh/37h]
    m = (s * 0xFFFFFF) & 0xFFFFFFFF                   # imul ecx (ecx=0FFFFFFh)
    struct.pack_into('<I', b, 0, u32(b, 0) ^ m)       # xor [esi],eax
    bl = b[0] & 0xFF                                  # mov ebx,[esi]
    eax, ecx = 0, len(b) - 4
    for i in range(4, len(b)):
        b[i] = ((b[i] ^ bl) - (eax & 0xFF)) & 0xFF    # xor [esi],bl ; sub [esi],al
        eax = (eax + 3 + ecx) & 0xFFFFFFFF            # add eax,3 ; add eax,ecx
        ecx -= 1                                      # loop
    return bytes(b)


def xbtf_mangle(plain):
    """Inverse of xbtf_unmangle. plain[0:4] is the key dword (its low byte keys the XOR)."""
    if len(plain) < 0x38:
        raise ValueError('XBTF image must be >= 0x38 bytes')
    b = bytearray(plain)
    bl = b[0]
    eax, ecx = 0, len(b) - 4
    for i in range(4, len(b)):
        b[i] = (((b[i] + (eax & 0xFF)) & 0xFF) ^ bl)
        eax = (eax + 3 + ecx) & 0xFFFFFFFF
        ecx -= 1
    s = (b[0x27] + b[0x2F] + b[0x37]) & 0xFF
    m = (s * 0xFFFFFF) & 0xFFFFFFFF
    struct.pack_into('<I', b, 0, u32(b, 0) ^ m)
    return bytes(b)


def cstr(b, o):
    e = b.index(0, o)
    return b[o:e].decode('latin-1')


# ------------------------------------------------- self-decrypting ETM stub (Yelo15)
# Found at the entry of Yelo15.etm (offset 0x19DE). It decrypts [code, idlist-4) in
# place with byte = ((byte - al) ^ bl), al starting at the low byte of EAX0 and
# decreasing by 3, bl = low byte of the first title ID; then it writes code_off to
# header+0x16 (so a re-run after a reboot skips decryption) and calls code_off.
STUB_RE = re.compile(
    rb'\x8b\xd5\xbf(.{4})\x89\x7a\x16\x03\xd7\x52\xb8(.{4})\x8b\xf5\x8b\x5e\x12'
    rb'\x8b\xcb\x8b\x5c\x1d\x00\x2b\xcf\x83\xe9\x04\x28\x02\x30\x1a\x42\x83\xe8\x03'
    rb'\xe2\xf6\x5a\xff\xd2\xc3', re.S)


def stub_params(data, entry):
    m = STUB_RE.match(data, entry)
    if not m:
        return None
    return {'code_off': u32(m.group(1), 0), 'eax0': u32(m.group(2), 0),
            'stub_len': m.end() - m.start()}


def stub_crypt(data, code_off, eax0, decrypt=True):
    b = bytearray(data)
    idl = u32(b, 0x12)
    bl = u32(b, idl) & 0xFF
    n = idl - code_off - 4
    eax = eax0
    for i in range(n):
        p = code_off + i
        if decrypt:
            b[p] = ((b[p] - (eax & 0xFF)) & 0xFF) ^ bl
        else:
            b[p] = ((b[p] ^ bl) + (eax & 0xFF)) & 0xFF
        eax = (eax - 3) & 0xFFFFFFFF
    return bytes(b), (code_off, code_off + n)


# ---------------------------------------------------------------- parsing
def parse(raw, is_xbtf):
    """Return (trainer_data_bytes, info dict) mirroring CTrainer::Load."""
    info = {'container': 'xbtf' if is_xbtf else 'etm', 'file_size': len(raw)}
    if is_xbtf:
        dec = xbtf_unmangle(raw)
        key = cstr(dec, 4)
        if len(key) < 7 or key[6] != '-':
            raise ValueError('XBTF creation key[6] != "-" (XBMC rejects this file)')
        o = 4 + len(key) + 1
        scroller = cstr(dec, o)
        o += len(scroller) + 1
        info.update(xbtf_key_dword=hex(u32(dec, 0)), creation_key=key,
                    scroller=scroller, trainer_data_offset=o)
        data = dec[o:]
    else:
        data = bytes(raw)
    if len(data) < HDR_SIZE:
        raise ValueError('trainer data shorter than header')
    h = dict(size_field=u32(data, 0), word_04=struct.unpack_from('<H', data, 4)[0],
             code_field=u32(data, 6), options_off=u32(data, 0x0A),
             text_off=u32(data, 0x0E), idlist_off=u32(data, 0x12),
             dw_16=u32(data, 0x16), dw_1A=u32(data, 0x1A))
    info['header'] = {k: hex(v) for k, v in h.items()}
    ids = [u32(data, h['idlist_off'] + 4 * i) for i in range(3)]
    info['title_ids'] = [hex(x) for x in ids]
    # entry resolution exactly as trainerloaderdata does: [0x1A] if nonzero else [0x16]
    if h['dw_1A']:
        info['kind'] = 'xbtf (toys section at +0x16)'
        info['entry_off'] = h['dw_1A']
        info['xbtf_section_off'] = h['dw_16']
    else:
        info['kind'] = 'etm/converted (entry at +0x16)'
        info['entry_off'] = h['dw_16']
    # text table, as CTrainer::Load
    maxn = h['text_off'] - h['options_off']
    texts = []
    for i in range(maxn + 2):
        p = u32(data, h['text_off'] + 4 * i)
        if not p:
            break
        texts.append(cstr(data, p))
    info['name'] = texts[0] if texts else ''
    info['info'] = texts[1] if len(texts) > 1 else ''
    labels = texts[2:]
    info['options'] = [{'index': i, 'label': l, 'default': data[h['options_off'] + i],
                        'offset': hex(h['options_off'] + i)} for i, l in enumerate(labels)]
    info['trainer_data_size'] = len(data)
    info['xbmc_alloc_bytes'] = XBTF_HEAP_SIZE if is_xbtf else ETM_HEAP_SIZE
    need = LOADER_SIZE + len(data)
    info['loader_plus_data_bytes'] = need
    info['fits_xbmc_heap'] = need <= info['xbmc_alloc_bytes']
    info['fits_allocated_pages'] = need <= -(-info['xbmc_alloc_bytes'] // PAGE) * PAGE
    return data, info


# ---------------------------------------------------------------- building
def build_data(code, title_ids, name, info, labels, defaults, entry_rel=0,
               xbtf_toys=False, code_off=0x23):
    """Lay out trainer data: header | [toys] | code | idlist | options | text table | strings."""
    for l in [name, info] + labels:
        if len(l.encode('latin-1')) > LABEL_MAX:
            raise ValueError('string longer than %d bytes: %r' % (LABEL_MAX, l))
    ids = (list(title_ids) + [0, 0, 0])[:3]
    sect_off = 0
    b = bytearray(code_off)
    if xbtf_toys:                      # 6 dwords XBMC fills with toy addresses
        sect_off = code_off
        code_off += 24
        b += bytes(24)
    b += code                          # title-ID list follows the code directly, so
    align = lambda: b.extend(b'\0' * (-len(b) % 4))   # [code_off, idlist) == code exactly
    id_off = len(b)
    b += struct.pack('<3I', *ids)
    opt_off = len(b)
    nopt = max(len(labels), 1)
    opts = bytearray(nopt)
    for i, v in enumerate(defaults[:len(labels)]):
        opts[i] = 1 if v else 0
    b += opts
    align()
    text_off = len(b)
    strings = [name, info] + labels
    b += bytes(4 * (len(strings) + 1))
    for i, s in enumerate(strings):
        struct.pack_into('<I', b, text_off + 4 * i, len(b))
        b += s.encode('latin-1') + b'\0'
    align()
    entry = code_off + entry_rel
    struct.pack_into('<IHIIIIII', b, 0, len(b), 1, code_off, opt_off, text_off, id_off,
                     sect_off if xbtf_toys else entry, entry if xbtf_toys else 0)
    return bytes(b)


def build_xbtf(data, creation_key='H2STAT-TRAINER', scroller='', key_dword=0x54533248):
    if len(creation_key) < 7 or creation_key[6] != '-':
        raise ValueError('creation key must have "-" at index 6 (Trainer.cpp check)')
    plain = (struct.pack('<I', key_dword) + creation_key.encode('latin-1') + b'\0'
             + scroller.encode('latin-1') + b'\0' + data)
    return xbtf_mangle(plain)
