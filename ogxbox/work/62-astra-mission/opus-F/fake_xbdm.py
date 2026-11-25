#!/usr/bin/env python3
"""fake_xbdm.py - scripted LOOPBACK XBDM server used only by test_xbdm_observe.py.

Binds 127.0.0.1:0.  Scripted memory map (base -> bytearray; unmapped bytes reply '??'), thread table with
stop reasons and contexts, xbeinfo state (None => 402 dashboard), a magicboot "reboot" that drops every
connection and refuses new ones for reboot_s, a notification stream, a down switch, and a log of every
received command line plus a raw received-byte counter.
"""
import socket
import threading
import time


class FakeXbdm:
    def __init__(self, regions=None, xbeinfo=None, threads=None, modules=None, reboot_s=0.5, after_boot=None,
                 shot=b'\x10\x20\x30\x00' * 8):
        self.lock = threading.RLock()
        self.regions = {b: bytearray(v) for b, v in (regions or {}).items()}
        self.xbeinfo = xbeinfo
        self.threads = threads if threads is not None else {
            4: {'info': {'suspend': 0, 'priority': 16, 'tlsbase': 0xd0000f00, 'start': 0x80020000,
                         'base': 0xd0001000, 'limit': 0xd0000000},
                'stopped': None, 'ctx': {'Eip': 0x80021234, 'Esp': 0xd0000f00, 'Ebp': 0xd0000f40,
                                         'EFlags': 0x202, 'Eax': 1}}}
        self.modules = modules or ['name="xboxkrnl.exe" base=0x80010000 size=0x001380e0 check=0x0 timestamp=0x0',
                                   'name="xbdm.dll" base=0xb002d000 size=0x00080000 check=0x0 timestamp=0x0']
        self.reboot_s = reboot_s
        self.after_boot = after_boot
        self.shot = shot
        self.log = []               # (conn_id, line)
        self.bytes_received = 0
        self.connections = 0
        self.refuse_until = 0.0
        self.down = False
        self.conns = set()
        self.notify_conns = set()
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(('127.0.0.1', 0))
        self.srv.listen(16)
        self.port = self.srv.getsockname()[1]
        self.closed = False
        threading.Thread(target=self._accept, daemon=True).start()

    # -------------------------------------------------- control
    def close(self):
        self.closed = True
        try:
            self.srv.close()
        except OSError:
            pass
        self.drop_all()

    def drop_all(self):
        with self.lock:
            cs = list(self.conns)
            self.conns.clear()
            self.notify_conns.clear()
        for c in cs:
            try:
                c.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                c.close()
            except OSError:
                pass

    def set_down(self, down=True):
        self.down = down
        if down:
            self.drop_all()

    def push_notification(self, line):
        with self.lock:
            cs = list(self.notify_conns)
        for c in cs:
            try:
                c.sendall((line + '\r\n').encode('latin1'))
            except OSError:
                pass

    def set_mem(self, addr, data):
        with self.lock:
            for base, buf in self.regions.items():
                if base <= addr and addr + len(data) <= base + len(buf):
                    buf[addr - base:addr - base + len(data)] = data
                    return
            self.regions[addr] = bytearray(data)

    def read(self, addr, n):
        out = [None] * n
        with self.lock:
            for base, buf in self.regions.items():
                lo, hi = max(addr, base), min(addr + n, base + len(buf))
                if lo < hi:
                    out[lo - addr:hi - addr] = list(buf[lo - base:hi - base])
        return out

    def commands(self):
        with self.lock:
            return [l for _, l in self.log]

    def verbs(self):
        return [l.split()[0].lower() for l in self.commands() if l.split()]

    # -------------------------------------------------- server
    def _accept(self):
        while not self.closed:
            try:
                s, _ = self.srv.accept()
            except OSError:
                return
            if self.down or time.time() < self.refuse_until:
                try:
                    s.close()
                except OSError:
                    pass
                continue
            with self.lock:
                self.connections += 1
                cid = self.connections
                self.conns.add(s)
            threading.Thread(target=self._handle, args=(s, cid), daemon=True).start()

    def _handle(self, s, cid):
        try:
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.sendall(b'201- connected\r\n')
            f = s.makefile('rb')
            while True:
                raw = f.readline()
                if not raw:
                    break
                line = raw.decode('latin1').rstrip('\r\n')
                with self.lock:
                    self.bytes_received += len(raw)
                    self.log.append((cid, line))
                resp, after = self._respond(line)
                if resp:
                    s.sendall(resp)
                if after == 'close':
                    break
                if after == 'notify':
                    with self.lock:
                        self.notify_conns.add(s)
                if after == 'reboot':
                    time.sleep(0.05)
                    with self.lock:
                        self.refuse_until = time.time() + self.reboot_s
                        if self.after_boot:
                            self.after_boot(self)
                    self.drop_all()
                    return
        except OSError:
            pass
        finally:
            with self.lock:
                self.conns.discard(s)
                self.notify_conns.discard(s)
            try:
                s.close()
            except OSError:
                pass

    @staticmethod
    def _kv(line):
        out = {}
        for w in line.split()[1:]:
            if '=' in w:
                k, v = w.split('=', 1)
                out[k.lower()] = v.strip('"')
        return out

    def _respond(self, line):
        words = line.split()
        if not words:
            return b'400- empty\r\n', None
        verb = words[0].lower()
        kv = self._kv(line)

        def multi(lines):
            return ('202- multiline response follows\r\n' + ''.join(l + '\r\n' for l in lines) + '.\r\n').encode()
        with self.lock:
            if verb == 'dmversion':
                return b'200- 1.00.5455.1\r\n', None
            if verb == 'xbeinfo':
                if self.xbeinfo is None:
                    return b'402- file not found\r\n', None
                x = self.xbeinfo
                return multi(['timestamp=0x%08x checksum=0x%08x' % (x['timestamp'], x.get('checksum', 0)),
                              'name="%s"' % x.get('name', 'default.xbe')]), None
            if verb == 'modules':
                return multi(self.modules), None
            if verb == 'systime':
                return ('200- high=0x01dc5e1a low=0x%08x\r\n' % (int(time.time() * 1e7) & 0xffffffff)).encode(), None
            if verb == 'threads':
                return multi([str(t) for t in sorted(self.threads)]), None
            if verb in ('threadinfo', 'isstopped', 'getcontext'):
                try:
                    tid = int(kv.get('thread', ''), 0)
                except ValueError:
                    tid = None
                t = self.threads.get(tid)
                if t is None:
                    return b'408- no such thread\r\n', None
                if verb == 'threadinfo':
                    return multi([' '.join('%s=0x%x' % (k, v) for k, v in t['info'].items())]), None
                if verb == 'isstopped':
                    if t['stopped']:
                        return ('200- %s\r\n' % t['stopped']).encode(), None
                    return b'408- not stopped\r\n', None
                c = t['ctx']
                return multi([' '.join('%s=0x%x' % (k, v) for k, v in c.items())]), None
            if verb == 'getmem':
                addr, n = int(kv['addr'], 0), int(kv['length'], 0)
                vals = self.read(addr, n)
                h = ''.join('??' if v is None else '%02x' % v for v in vals)
                return multi([h[i:i + 128] for i in range(0, len(h), 128)]), None
            if verb == 'screenshot':
                d = self.shot
                hdr = ('pitch=0x10 width=0x4 height=0x2 format=0x1e offsetx=0x0 offsety=0x0, '
                       'framebuffersize=0x%x sw=0x4 sh=0x2 colorspace=0x0' % len(d))
                return b'203- binary response follows\r\n' + hdr.encode() + b'\r\n' + d, None
            if verb == 'notify':
                return b'205- now a notification channel\r\n', 'notify'
            if verb == 'dirlist':
                return multi([]), None
            if verb == 'bye':
                return b'200- bye\r\n', 'close'
            if verb == 'magicboot':
                return b'200- OK\r\n', 'reboot'
            if verb in ('stop', 'reboot'):
                return b'200- OK\r\n', None
        return b'407- unknown command\r\n', None
