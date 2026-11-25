#!/usr/bin/env python3
"""Extract frozen physical GIP input frames from button-run.log into a replay
fixture, and independently decode them so the C replay test can assert against
real (not synthetic) bytes. Owned work 24; read-only on the frozen logs."""
import json, struct, sys

LOG = "/home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work/20-runtime/button-run.log"

def parse_rx(line):
    # "RX seq=N status=0x.. req=64 id=N n=L <L hex bytes> "
    toks = line.split()
    # find 'n=' token to get length, then the hex bytes follow
    i = toks.index('req=64')  # sentinel: req=64 for this pad
    # idx of 'n=': search after id
    n_idx = next(k for k, t in enumerate(toks) if t.startswith('n='))
    n = int(toks[n_idx][2:])
    hexbytes = toks[n_idx+1:n_idx+1+n]
    return bytes(int(x, 16) for x in hexbytes)

def decode_frame(buf):
    """Re-implement gdr_gip_rx for a single buffer (may hold multiple frames)."""
    out = []
    while len(buf) > 3:
        cmd, opt, seq = buf[0], buf[1], buf[2]
        # LEB128 length
        pktlen = 0; clen = 0
        for b in buf[3:3+4]:
            clen += 1
            pktlen |= (b & 0x7f) << (7*(clen-1))
            if not (b & 0x80):
                break
        hdr = 3 + clen
        if len(buf) < hdr + pktlen:
            break
        payload = buf[hdr:hdr+pktlen]
        if cmd == 0x20:  # input
            b = payload[0] | (payload[1] << 8)
            lt = payload[2] | (payload[3] << 8)
            rt = payload[4] | (payload[5] << 8)
            lx = struct.unpack('<h', payload[6:8])[0]
            ly = struct.unpack('<h', payload[8:10])[0]
            rx = struct.unpack('<h', payload[10:12])[0]
            ry = struct.unpack('<h', payload[12:14])[0]
            out.append(dict(b=b, lt=lt, rt=rt, lx=lx, ly=ly, rx=rx, ry=ry, seq=seq))
        buf = buf[hdr+pktlen:]
    return out

frames = []
with open(LOG) as f:
    for line in f:
        line = line.strip()
        if not line.startswith('RX '):
            continue
        buf = parse_rx(line)
        frames.extend(decode_frame(buf))

print("total input frames decoded:", len(frames))

# button events (A=XG_AB_A bit4, etc.) — GIP button bit mapping from gdr_snap_from_input
seen = set()
events = []
for fr in frames:
    b = fr['b']
    tags = []
    if b & (1<<4):  tags.append('A')
    if b & (1<<5):  tags.append('B')
    if b & (1<<6):  tags.append('X')
    if b & (1<<7):  tags.append('Y')
    if fr['lt'] > 1000: tags.append('LT')
    if fr['rt'] > 1000: tags.append('RT')
    if fr['lx'] or fr['ly'] or fr['rx'] or fr['ry']: tags.append('STICK')
    k = tuple(sorted(tags))
    if k and k not in seen:
        seen.add(k)
        events.append((fr['seq'], k, fr))

print("\nfirst occurrence of each event:")
for seq, k, fr in events:
    print("  seq=%d %s  b=0x%04x lt=%d rt=%d lx=%d ly=%d rx=%d ry=%d" %
          (seq, '+'.join(k) or 'neutral', fr['b'], fr['lt'], fr['rt'],
           fr['lx'], fr['ly'], fr['rx'], fr['ry']))

# save a compact fixture: representative frames (first A, first B, first X, first Y,
# first LT/RT, first STICK, first neutral)
fixture = []
want = {'A','B','X','Y','LT','RT','STICK'}
chosen = {}
for seq, k, fr in events:
    for t in k:
        if t in want and t not in chosen:
            chosen[t] = fr
# ensure order
for t in ['A','B','X','Y','LT','RT','STICK']:
    if t in chosen:
        fixture.append(dict(tag=t, **chosen[t]))
out = {"source": LOG, "frames": fixture}
with open("frozen_input_fixture.json", "w") as f:
    json.dump(out, f, indent=2)
print("\nwrote frozen_input_fixture.json with", len(fixture), "representative frames")
