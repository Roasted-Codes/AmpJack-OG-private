#!/usr/bin/env python3
"""Minimal XDVDFS image writer (test transport only: host FTP to the devkit is
unavailable because wlan0 is down). Layout: /AmpJack-OG/default.xbe so XBMC's file
manager can copy the folder D:\\AmpJack-OG -> E:\\ (no on-screen-keyboard MKD).
mkxiso.py IN.xbe OUT.iso"""
import struct, sys

S = 2048
src, out = sys.argv[1], sys.argv[2]
data = open(src, 'rb').read()
MAGIC = b'MICROSOFT*XBOX*MEDIA'
ROOT_SEC, SUB_SEC, FILE_SEC = 33, 34, 35


def table(name, sec, size, attr):
    e = struct.pack('<HHIIBB', 0, 0, sec, size, attr, len(name)) + name
    e += b'\xff' * (-len(e) % 4)
    return e + b'\xff' * (S - len(e))


vd = bytearray(S)
vd[0:20] = MAGIC
struct.pack_into('<IIQ', vd, 20, ROOT_SEC, S, 0)
vd[0x7EC:0x7EC + 20] = MAGIC
img = bytearray(32 * S) + vd
img += table(b'AmpJack-OG', SUB_SEC, S, 0x10)
img += table(b'default.xbe', FILE_SEC, len(data), 0x20)
img += data
img += b'\x00' * (-len(img) % S)
img += b'\x00' * (S * 16)
open(out, 'wb').write(img)
print(out, len(img))
