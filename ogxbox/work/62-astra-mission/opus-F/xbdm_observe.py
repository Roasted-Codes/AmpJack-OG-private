#!/usr/bin/env python3
"""xbdm_observe.py - read-only XBDM observer for Halo 2 u803 runs on a real debug Xbox (OPUS-F).

Subcommands (see README-RUN.md):
  probe            read-only qualification of the debug monitor's reply shapes
  observe          wait for the title, gate it, observe (never launches)
  launch-observe   verify an identity receipt, ONE magicboot, then as observe
  recover          send exactly one parent-granted command (stop | reboot | reboot warm)

stdlib only; run with /usr/bin/python3 -B.  Every command goes through Conn.command(), which calls
Policy.check() before a single byte is written to the socket.  No file transfer verbs exist here.
Exit codes: 0 completed, 2 gate/identity/refusal, 3 fault, 4 freeze suspected, 5 unreachable,
6 instrument error.
"""
import argparse
import hashlib
import json
import os
import queue
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import traceback
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PINS = os.path.normpath(os.path.join(HERE, '..', 'OPUS-F-PINS.json'))
DEFAULT_OUT_ROOT = os.path.normpath(os.path.join(HERE, '..', 'real-xbox'))
XBDM_PORT = 731

EXIT_OK, EXIT_GATE, EXIT_FAULT, EXIT_FREEZE, EXIT_UNREACH, EXIT_INSTR = 0, 2, 3, 4, 5, 6

READ_ONLY_VERBS = frozenset((
    'dmversion', 'xbeinfo', 'modules', 'threads', 'threadinfo', 'isstopped', 'getcontext',
    'getmem', 'systime', 'screenshot', 'notify', 'dirlist', 'bye'))
GRANTABLE_COMMANDS = ('stop', 'reboot', 'reboot warm')
GRANT_MAX_AGE_S = 900.0
RECEIPT_MAX_AGE_S = 6 * 3600.0
KSEG_LO, KSEG_HI = 0x80000000, 0x8fffffff
QUIESCENT_HOLD_NS = 10 * 10**9
FAULT_NOTIFY_PREFIXES = ('exception', 'rip', 'execution stopped')


class Refused(Exception):
    """Raised before any byte is sent when a command is not allowed."""


class XbdmIOError(OSError):
    """Protocol-level transport failure (EOF, bad banner, short binary)."""


NET_ERRORS = (OSError, EOFError)


def mono():
    return time.monotonic_ns()


def wall():
    return time.time_ns()


def pint(v):
    return v if isinstance(v, int) else int(str(v), 0)


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load_pins(path):
    with open(path, 'rb') as f:
        data = f.read()
    return json.loads(data.decode('utf-8')), sha256_bytes(data)


def parse_kv(text):
    out = {}
    for k, v in re.findall(r'(\w+)=("[^"]*"|\S+)', text):
        if v.startswith('"'):
            out[k] = v[1:-1]
            continue
        v = v.rstrip(',')
        try:
            out[k] = int(v, 0)
        except ValueError:
            out[k] = v
    return out


def in_kseg(addr, length=1):
    return addr is not None and KSEG_LO <= addr and addr + length - 1 <= KSEG_HI


# ---------------------------------------------------------------- verb gate
class Policy:
    """Process-wide verb allowlist.  check() is the only gate; Conn.command() calls it first."""

    def __init__(self, mode, grant_command=None):
        self.mode = mode
        self.grant_command = grant_command
        self.magicboot_used = False
        self.grant_used = False
        self.lock = threading.Lock()

    def check(self, line):
        if not isinstance(line, str) or '\r' in line or '\n' in line or '\x00' in line:
            raise Refused('control character in command')
        unquoted = re.sub(r'"[^"]*"', '""', line)
        if '"' in unquoted.replace('""', ''):
            raise Refused('unbalanced quote')
        words = unquoted.strip().split()
        if not words:
            raise Refused('empty command')
        verb = words[0].lower()
        with self.lock:
            if verb in READ_ONLY_VERBS:
                return verb
            if verb == 'magicboot':
                if self.mode != 'launch-observe':
                    raise Refused('magicboot only allowed in launch-observe')
                if self.magicboot_used:
                    raise Refused('magicboot already used once in this process')
                keys = [w.split('=', 1)[0].lower() for w in words[1:]]
                if any(k in ('debug', 'cold') for k in keys):
                    raise Refused('magicboot with debug/cold refused')
                if sorted(keys) != ['directory', 'title']:
                    raise Refused('magicboot needs exactly title= and directory=')
                self.magicboot_used = True
                return verb
            norm = ' '.join(w.lower() for w in words)
            if (self.mode == 'recover' and self.grant_command in GRANTABLE_COMMANDS
                    and not self.grant_used and norm == self.grant_command):
                self.grant_used = True
                return verb
            raise Refused('verb %r not allowed in mode %s' % (verb, self.mode))


class CommandLog:
    def __init__(self, path):
        self.f = open(path, 'a', encoding='utf-8')
        self.seq = 0
        self.lock = threading.Lock()

    def log(self, conn, command, status, lines, data, t0, w0, err):
        with self.lock:
            self.seq += 1
            rec = {'seq': self.seq, 'conn': conn, 'mono_ns': t0, 'wall_ns': w0, 'command': command,
                   'status_line': status, 'reply_lines': lines,
                   'reply_bytes': (len(data) if data else 0) + sum(len(x) for x in lines),
                   'elapsed_ms': round((mono() - t0) / 1e6, 3)}
            if err:
                rec['error'] = err
            self.f.write(json.dumps(rec) + '\n')
            self.f.flush()

    def sync(self):
        with self.lock:
            self.f.flush()
            os.fsync(self.f.fileno())

    def close(self):
        with self.lock:
            self.f.close()


class Reply:
    def __init__(self, verb, command, status, lines, data):
        self.verb, self.command, self.status, self.lines, self.data = verb, command, status, lines, data

    @property
    def ok(self):
        return bool(self.status) and self.status.startswith('2')

    def as_dict(self):
        d = {'command': self.command, 'status': self.status, 'lines': self.lines}
        if self.data is not None:
            d['data_len'] = len(self.data)
        return d


class Conn:
    def __init__(self, ip, port, policy, cmdlog, timeout=2.0, name='cmd'):
        self.policy, self.cmdlog, self.name = policy, cmdlog, name
        self.s = socket.create_connection((ip, port), timeout=timeout)
        try:
            self.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self.f = self.s.makefile('rb')
        try:
            self.banner = self.readline()
        except Exception:
            self.close()
            raise
        if not self.banner.startswith('201'):
            self.close()
            raise XbdmIOError('bad banner %r' % self.banner)

    def readline(self):
        b = self.f.readline(1 << 22)
        if not b:
            raise XbdmIOError('connection closed')
        return b.decode('latin1').rstrip('\r\n')

    def readraw(self, n):
        buf = bytearray()
        while len(buf) < n:
            x = self.f.read(n - len(buf))
            if not x:
                raise XbdmIOError('short binary reply %d/%d' % (len(buf), n))
            buf += x
        return bytes(buf)

    def command(self, line):
        verb = self.policy.check(line)          # raises Refused before any byte is written
        t0, w0 = mono(), wall()
        status, lines, data, err = None, [], None, None
        try:
            self.s.sendall((line + '\r\n').encode('latin1'))
            status = self.readline()
            if status.startswith('202'):
                while True:
                    ln = self.readline()
                    if ln == '.':
                        break
                    lines.append(ln)
            elif status.startswith('203'):
                hdr = self.readline()
                lines.append(hdr)
                n = parse_kv(hdr).get('framebuffersize')
                if not isinstance(n, int):
                    raise XbdmIOError('203 reply without framebuffersize')
                data = self.readraw(n)
        except Exception as e:
            err = repr(e)
            raise
        finally:
            if self.cmdlog:
                self.cmdlog.log(self.name, line, status, lines, data, t0, w0, err)
        return Reply(verb, line, status, lines, data)

    def settimeout(self, t):
        self.s.settimeout(t)

    def close(self):
        for x in (getattr(self, 'f', None), getattr(self, 's', None)):
            try:
                if x:
                    x.close()
            except OSError:
                pass


# ---------------------------------------------------------------- memory decoding
def hex_to_vals(text):
    out = []
    for i in range(0, len(text) // 2 * 2, 2):
        p = text[i:i + 2]
        if '?' in p:
            out.append(None)
            continue
        try:
            out.append(int(p, 16))
        except ValueError:
            out.append(None)
    return out


def vals_hex(vals):
    if vals is None:
        return None
    return ''.join('??' if v is None else '%02x' % v for v in vals)


def getmem(conn, addr, length):
    if addr < 0 or length <= 0 or addr + length > (1 << 32):
        raise ValueError('getmem out of address space')
    r = conn.command('getmem addr=0x%x length=0x%x' % (addr, length))
    if not (r.status or '').startswith('202'):
        return {'addr': addr, 'len': length, 'status': r.status, 'hex': None, 'vals': None, 'unreadable': None}
    text = ''.join(x.strip() for x in r.lines)
    vals = hex_to_vals(text)
    return {'addr': addr, 'len': length, 'status': r.status, 'hex': text, 'vals': vals,
            'unreadable': sum(1 for v in vals if v is None) + max(0, length - len(vals))}


def mem_public(m):
    return {k: m.get(k) for k in ('addr', 'len', 'status', 'hex', 'unreadable')}


def v_u8(vals, off):
    if vals is None or off >= len(vals):
        return None
    return vals[off]


def v_u32(vals, off):
    if vals is None or off + 4 > len(vals) or any(v is None for v in vals[off:off + 4]):
        return None
    return vals[off] | vals[off + 1] << 8 | vals[off + 2] << 16 | vals[off + 3] << 24


def v_hex(vals, off, n):
    if vals is None or off + n > len(vals) or any(v is None for v in vals[off:off + n]):
        return None
    return bytes(vals[off:off + n]).hex()


def decode_enum(vals, pins):
    """Decode the enum poll region (or just the 0x84 block). Any unreadable byte => that field None."""
    e = pins['enum']
    f = e['fields']
    base = pint(e['block'])
    return {
        'b0': v_u8(vals, pint(f['b0_busy'])),
        'retry': v_u8(vals, pint(f['retry_b2'])),
        'marker': v_u8(vals, pint(f['marker_b3'])),
        'timer_hdr': v_hex(vals, pint(f['ktimer']), 4),
        'timer_inserted': v_u8(vals, pint(f['ktimer_inserted_byte'])),
        'duetime': v_hex(vals, pint(f['ktimer_duetime']), 8),
        'dpc_ptr': v_u32(vals, pint(f['ktimer_dpc_ptr'])),
        'pending': v_u32(vals, pint(f['pending_u32'])),
        'current': v_u32(vals, pint(f['current_u32'])),
        'node_pool_ptr': v_u32(vals, pint(e['node_pool_ptr']) - base),
        'state_word': v_u32(vals, pint(e['state_word']) - base),
    }


def eval_site(site, vals):
    va, n = pint(site['va']), int(site['len'])
    stock = bytes.fromhex(site['stock_hex'])
    rec = {'va': '0x%x' % va, 'len': n, 'raw_hex': vals_hex(vals), 'state': 'UNREADABLE',
           'target': None, 'resident': None}
    if vals is None or len(vals) < n or any(v is None for v in vals[:n]):
        return rec
    b = bytes(vals[:n])
    if b == stock:
        rec['state'] = 'STOCK'
    elif b[0] == 0xe9 and b[5:] == stock[5:]:
        rel = int.from_bytes(b[1:5], 'little')
        target = (va + 5 + rel) & 0xffffffff
        rec.update(state='HOOKED', target=target, resident=(target - int(site['resident_offset'])) & 0xffffffff)
    else:
        rec['state'] = 'UNKNOWN'
    return rec


def trainer_state_of(sites, pins):
    states = [s['state'] for s in sites.values()]
    if all(s == 'STOCK' for s in states):
        return 'OFF', None
    if all(s == 'HOOKED' for s in states):
        res = set(s['resident'] for s in sites.values())
        if len(res) == 1:
            r = res.pop()
            if in_kseg(r, int(pins['trainer']['resident_alloc'])):
                return 'ON', r
    return 'INCONSISTENT', None


def classify_pc(pc, pins, resident):
    if pc is None:
        return None
    lo, hi = (pint(x) for x in pins['enum']['title_image_range'])
    if lo <= pc < hi:
        return 'title'
    if resident is not None and resident <= pc < resident + int(pins['trainer']['resident_alloc']):
        return 'resident'
    if pc >= 0x80000000:
        return 'kernel'
    return 'other'


def shot_to_png(raw, hdr, path):
    """Offline conversion of a 32bpp X8R8G8B8 framebuffer (format 0x1e seen on 5849 kits)."""
    w, h, pitch = hdr.get('width'), hdr.get('height'), hdr.get('pitch')
    if not all(isinstance(x, int) and x > 0 for x in (w, h, pitch)) or pitch < w * 4 or len(raw) < pitch * h:
        return False

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    rows = []
    for y in range(h):
        row = raw[y * pitch:y * pitch + w * 4]
        px = bytearray(w * 3)
        px[0::3] = row[2::4]
        px[1::3] = row[1::4]
        px[2::3] = row[0::4]
        rows.append(b'\x00' + bytes(px))
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(b''.join(rows), 6)) + chunk(b'IEND', b''))
    with open(path, 'wb') as f:
        f.write(png)
    return True


# ---------------------------------------------------------------- receipts and grants
def check_receipt(path, xbe, pins, now=None):
    now = time.time() if now is None else now
    if not path or not os.path.isfile(path):
        return False, 'identity receipt missing'
    try:
        with open(path, 'r', encoding='utf-8') as f:
            rc = json.load(f)
    except (OSError, ValueError) as e:
        return False, 'identity receipt unreadable: %r' % e
    if str(rc.get('console_path', '')).lower() != str(xbe).lower():
        return False, 'receipt console_path %r != --xbe %r' % (rc.get('console_path'), xbe)
    if str(rc.get('sha256', '')).lower() != pins['title']['xbe_sha256'].lower():
        return False, 'receipt sha256 does not match PINS title.xbe_sha256'
    if rc.get('size') != pins['title']['xbe_size']:
        return False, 'receipt size %r != PINS %r' % (rc.get('size'), pins['title']['xbe_size'])
    ve = rc.get('verified_epoch')
    if not isinstance(ve, (int, float)) or not (0 <= now - ve < RECEIPT_MAX_AGE_S):
        return False, 'receipt verified_epoch missing or older than 6 h'
    return True, 'ok'


def check_grant(path, run, now=None):
    now = time.time() if now is None else now
    if not path or not os.path.isfile(path):
        return False, 'grant file missing', None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            g = json.load(f)
    except (OSError, ValueError) as e:
        return False, 'grant unreadable: %r' % e, None
    if g.get('verb') not in GRANTABLE_COMMANDS:
        return False, 'grant verb %r not one of %s' % (g.get('verb'), GRANTABLE_COMMANDS), None
    if g.get('run') != run:
        return False, 'grant run %r != --run %r' % (g.get('run'), run), None
    if g.get('issued_by') != 'parent':
        return False, 'grant not issued_by parent', None
    ie = g.get('issued_epoch')
    if not isinstance(ie, (int, float)) or not (0 <= now - ie <= GRANT_MAX_AGE_S):
        return False, 'grant older than 900 s (or in the future)', None
    return True, 'ok', g


def ping_once(ip):
    if not ip:
        return None
    try:
        p = subprocess.run(['ping', '-c', '1', '-W', '1', ip], capture_output=True, text=True, timeout=5)
        return {'ip': ip, 'rc': p.returncode, 'out': (p.stdout + p.stderr)[-500:]}
    except Exception as e:  # ping missing or denied: record, do nothing else
        return {'ip': ip, 'rc': None, 'error': repr(e)}


# ---------------------------------------------------------------- run directory
def make_run_dir(out_root, run):
    os.makedirs(out_root, exist_ok=True)
    rd = os.path.join(out_root, 'run-%d' % run)
    os.mkdir(rd)        # exclusive: FileExistsError if it exists
    return rd


def write_json(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class Jsonl:
    def __init__(self, path):
        self.f = open(path, 'a', encoding='utf-8')
        self.lock = threading.Lock()
        self.count = 0

    def write(self, obj):
        with self.lock:
            self.f.write(json.dumps(obj, sort_keys=True) + '\n')
            self.f.flush()
            self.count += 1

    def sync(self):
        with self.lock:
            self.f.flush()
            os.fsync(self.f.fileno())

    def close(self):
        with self.lock:
            self.f.close()


class Notifier(threading.Thread):
    def __init__(self, conn, path, q):
        super().__init__(daemon=True)
        self.conn, self.q, self.stop_ev = conn, q, threading.Event()
        self.f = open(path, 'a', encoding='utf-8')
        self.lost = None
        self.count = 0

    def run(self):
        # Blocking reads (a timed-out makefile reader cannot be read again); stop() shuts the socket down.
        self.conn.settimeout(None)
        while not self.stop_ev.is_set():
            try:
                ln = self.conn.readline()
            except Exception as e:
                if not self.stop_ev.is_set():
                    self.lost = repr(e)
                break
            t = mono()
            self.f.write('%d\t%d\t%s\n' % (t, wall(), ln))
            self.f.flush()
            self.count += 1
            self.q.put((t, ln))
        try:
            self.f.flush()
            os.fsync(self.f.fileno())
        except (OSError, ValueError):
            pass

    def stop(self):
        self.stop_ev.set()
        try:
            self.conn.s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.conn.close()
        self.join(2)
        try:
            self.f.close()
        except OSError:
            pass


# ---------------------------------------------------------------- observer
class Observer:
    def __init__(self, args, pins, pins_sha, rd, out, mode):
        self.a, self.pins, self.pins_sha, self.rd, self.out, self.mode = args, pins, pins_sha, rd, out, mode
        self.policy = Policy(mode)
        self.cmdlog = CommandLog(os.path.join(rd, 'commands.jsonl'))
        self.conn = None
        self.notifier = None
        self.nq = queue.Queue()
        self.gate = None
        self.trainer_state = None
        self.resident = self.module = None
        self.launch_mono = None
        self.first_sighting_mono = None
        self.samples = self.threads_log = self.mod_index = None
        self.seq = 0
        self.prev_fields = None
        self.change_count = 0
        self.prev_current = None
        self.prev_attached = None
        self.quiet_since = None
        self.quiescent_printed = False
        self.gate_mono = None
        self.last_np_ptr = None
        self.last_np_mono = 0
        self.known_threads = set()
        self.next_threads = 0
        self.next_shot = None
        self.next_module = None
        self.module_k = 0
        self.module_prev_sha = None
        self.shot_hist = []
        self.shots = 0
        self.marks_off = 0
        self.marks_log = None
        self.freeze = False
        self.fault = None
        self.unreachable_episodes = []
        self.first_sample = self.last_sample = None
        self.exit_reason = None

    # -- io helpers
    def say(self, line):
        self.out.write(line + '\n')
        self.out.flush()

    def connect(self, timeout=None):
        return Conn(self.a.ip, self.a.port, self.policy, self.cmdlog,
                    timeout=timeout or self.a.io_timeout, name='cmd')

    def close_conn(self):
        if self.conn:
            self.conn.close()
        self.conn = None

    def ensure_conn(self):
        if self.conn is None:
            self.conn = self.connect()
        return self.conn

    # -- entry
    def run(self):
        self.manifest = {
            'argv': list(self.a.argv), 'subcommand': self.mode, 'tool': os.path.abspath(__file__),
            'tool_sha256': sha256_file(os.path.abspath(__file__)), 'pins_path': os.path.abspath(self.a.pins),
            'pins_sha256': self.pins_sha, 'ip': self.a.ip, 'run': self.a.run, 'mark': getattr(self.a, 'mark', None),
            'start_wall_ns': wall(), 'start_mono_ns': mono(), 'python': sys.version}
        write_json(os.path.join(self.rd, 'manifest.json'), self.manifest)
        code = EXIT_INSTR
        try:
            code = self._run()
        except Refused as e:
            code, self.exit_reason = EXIT_GATE, 'refused: %s' % e
        except Exception:
            code, self.exit_reason = EXIT_INSTR, 'instrument error'
            with open(os.path.join(self.rd, 'instrument-error.txt'), 'w') as f:
                f.write(traceback.format_exc())
        finally:
            self.finish(code)
        return code

    def finish(self, code):
        if self.notifier:
            self.notifier.stop()
        if self.conn:
            try:
                self.conn.settimeout(1.0)
                self.conn.command('bye')
            except Exception:
                pass
            self.close_conn()
        for w in (self.samples, self.threads_log, self.mod_index, self.marks_log):
            if w:
                try:
                    w.sync()
                    w.close()
                except (OSError, ValueError):
                    pass
        try:
            self.cmdlog.sync()
            self.cmdlog.close()
        except (OSError, ValueError):
            pass
        summary = {
            'exit_code': code, 'exit_reason': self.exit_reason, 'mode': self.mode,
            'trainer_state': self.trainer_state, 'samples': self.samples.count if self.samples else 0,
            'threads_rows': self.threads_log.count if self.threads_log else 0,
            'notifications': self.notifier.count if self.notifier else 0,
            'notify_lost': self.notifier.lost if self.notifier else None,
            'shots': self.shots, 'module_dumps': self.module_k, 'first_sample': self.first_sample,
            'last_sample': self.last_sample, 'fault': self.fault, 'freeze_suspected': self.freeze,
            'unreachable_episodes': self.unreachable_episodes, 'gate_mono_ns': self.gate_mono}
        write_json(os.path.join(self.rd, 'summary.json'), summary)
        self.manifest.update(end_wall_ns=wall(), end_mono_ns=mono(), exit_code=code)
        write_json(os.path.join(self.rd, 'manifest.json'), self.manifest)
        self.say('DONE exit=%d' % code)

    def _run(self):
        if self.mode == 'launch-observe':
            self.launch()
        if not self.wait_title():
            self.exit_reason = 'title gate not passed (timestamp)'
            write_json(os.path.join(self.rd, 'title-gate.json'),
                       {'status': 'TIMEOUT', 'identity': None, 'trainer_state': None,
                        'attach_now': bool(self.a.attach_now)})
            return EXIT_GATE
        ok = self.title_gate()
        if not ok:
            self.exit_reason = 'identity %s' % self.gate.get('identity')
            return EXIT_GATE
        self.open_notify()
        return self.observe_loop()

    # -- launch
    def launch(self):
        if '"' in self.a.xbe or '"' in self.a.dir:
            raise Refused('quote in console path')
        self.ensure_conn()
        pre = self.conn.command('xbeinfo running')
        cmd = 'magicboot title="%s" directory="%s"' % (self.a.xbe, self.a.dir)
        self.launch_mono = mono()
        try:
            r = self.conn.command(cmd)
            rec = r.as_dict()
        except NET_ERRORS as e:
            rec = {'command': cmd, 'error': repr(e)}
        write_json(os.path.join(self.rd, 'launch.json'),
                   {'prelaunch_xbeinfo': pre.as_dict(), 'magicboot': rec, 'launch_mono_ns': self.launch_mono,
                    'launch_wall_ns': wall()})
        self.close_conn()   # the monitor drops connections while the console reboots

    # -- wait for the title (timestamp)
    def wait_title(self):
        want = pint(self.pins['title']['timestamp'])
        deadline = mono() + int(self.a.wait_title * 1e9)
        last = None
        while True:
            try:
                self.ensure_conn()
                r = self.conn.command('xbeinfo running')
                kv = parse_kv(' '.join(r.lines)) if (r.status or '').startswith('202') else {}
                last = r.as_dict()
                if self.first_sighting_mono is None and kv.get('timestamp') is not None:
                    self.first_sighting_mono = mono()
                if kv.get('timestamp') == want:
                    self.xbeinfo_at_gate = last
                    return True
            except NET_ERRORS as e:
                last = {'error': repr(e)}
                self.close_conn()
            if self.a.attach_now or mono() >= deadline:
                self.xbeinfo_at_gate = last
                return False
            time.sleep(0.1)

    # -- identity + trainer gate
    def title_gate(self):
        t = self.pins['title']
        lo, hi = t['header_signature_file_range']
        base = pint(t['image_base'])
        deadline = mono() + 5 * 10**9
        while True:
            hdr = getmem(self.conn, base, hi)
            sig = hdr['vals'][lo:hi] if hdr['vals'] else None
            if sig and len(sig) == hi - lo and None not in sig:
                identity = 'MATCH' if sha256_bytes(bytes(sig)) == t['header_signature_sha256'] else 'MISMATCH'
                break
            if mono() >= deadline:
                identity = 'UNREADABLE'
                break
            time.sleep(0.1)
        gate = {'identity': identity, 'header': mem_public(hdr), 'xbeinfo': getattr(self, 'xbeinfo_at_gate', None)}
        if identity != 'MATCH':
            gate.update(status=identity, trainer_state=None, gate_mono_ns=mono())
            self.gate = gate
            write_json(os.path.join(self.rd, 'title-gate.json'), gate)
            self.say('GATE %s identity=%s' % ('MISMATCH' if identity == 'MISMATCH' else 'UNREADABLE', identity))
            return False
        while True:
            sites = {}
            for name, s in self.pins['hook_sites'].items():
                m = getmem(self.conn, pint(s['va']), int(s['len']))
                sites[name] = eval_site(s, m['vals'])
            unreadable = any(v['state'] == 'UNREADABLE' for v in sites.values())
            if not unreadable or mono() >= deadline:
                break
            time.sleep(0.1)
        state, resident = trainer_state_of(sites, self.pins)
        self.gate_mono = mono()
        tr = self.pins['trainer']
        gate.update(status='PASS', sites=sites, trainer_state=state, gate_mono_ns=self.gate_mono,
                    resident=None, module=None, trainer_status=None,
                    ms_since_launch=(round((self.gate_mono - self.launch_mono) / 1e6, 3)
                                     if self.launch_mono else None),
                    ms_since_first_sighting=(round((self.gate_mono - self.first_sighting_mono) / 1e6, 3)
                                             if self.first_sighting_mono else None))
        self.trainer_state = state
        if state == 'ON':
            self.resident = resident
            self.module = resident + int(tr['module_offset_from_resident'])
            if not in_kseg(self.module, int(tr['module_size'])):
                state = self.trainer_state = 'INCONSISTENT'
                gate['trainer_state'] = state
                gate['note'] = 'module range outside 0x80000000..0x8fffffff'
                self.resident = self.module = None
            else:
                gate['resident'] = '0x%x' % self.resident
                gate['module'] = '0x%x' % self.module
                gate['trainer_status'] = self.read_status()
                self.dump_module(force=True)
        self.gate = gate
        write_json(os.path.join(self.rd, 'title-gate.json'), gate)
        hooks = sum(1 for v in sites.values() if v['state'] == 'HOOKED')
        st = gate.get('trainer_status') or {}
        self.say('GATE %s hooks=%s failed=%s' % (state, st.get('installed_hooks', hooks) if state == 'ON' else hooks,
                                                  st.get('install_failed', 0) if state == 'ON' else 0))
        return True

    def read_status(self):
        so = self.pins['trainer']['status_offsets']
        a = self.module + int(so['attached'])
        m = getmem(self.conn, a, 12)
        v = m['vals']
        return {'hex': m['hex'], 'attached': v_u32(v, 0), 'installed_hooks': v_u32(v, 4),
                'install_failed': v_u32(v, 8)}

    def dump_module(self, force=False, into=None):
        size = int(self.pins['trainer']['module_size'])
        m = getmem(self.conn, self.module, size)
        if m['vals'] is not None and m['unreadable'] == 0:
            blob, ext = bytes(m['vals']), 'bin'
        else:
            blob, ext = (m['hex'] or '').encode('ascii'), 'hex'
        h = sha256_bytes(blob)
        if into:
            with open(os.path.join(into, 'module.%s' % ext), 'wb') as f:
                f.write(blob)
            return h
        if not force and h == self.module_prev_sha:
            return None
        k = self.module_k
        path = os.path.join(self.rd, 'module-%03d.%s' % (k, ext))
        with open(path, 'wb') as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        if self.mod_index is None:
            self.mod_index = Jsonl(os.path.join(self.rd, 'module-index.jsonl'))
        self.mod_index.write({'k': k, 'mono_ns': mono(), 'sha256': h, 'file': os.path.basename(path)})
        self.mod_index.sync()
        self.module_k += 1
        self.module_prev_sha = h
        if k > 0:
            self.say('MODULE_CHANGED k=%d' % k)
        return h

    def open_notify(self):
        rec = {'opened_mono_ns': mono()}
        try:
            c = Conn(self.a.ip, self.a.port, self.policy, self.cmdlog, timeout=self.a.io_timeout, name='notify')
            r = c.command('notify')
            rec['reply'] = r.as_dict()
            if (r.status or '').startswith('205'):
                self.notifier = Notifier(c, os.path.join(self.rd, 'notifications.log'), self.nq)
                self.notifier.start()
                rec['active'] = True
            else:
                rec['active'] = False
                c.close()
        except NET_ERRORS as e:
            rec.update(active=False, error=repr(e))
        with open(os.path.join(self.rd, 'notify-channel.jsonl'), 'a') as f:
            f.write(json.dumps(rec) + '\n')

    # -- observation
    def observe_loop(self):
        self.samples = Jsonl(os.path.join(self.rd, 'samples.jsonl'))
        self.threads_log = Jsonl(os.path.join(self.rd, 'threads.jsonl'))
        self.marks_log = Jsonl(os.path.join(self.rd, 'marks.jsonl'))
        start = mono()
        end = start + int(self.a.duration * 1e9)
        cad = int(self.a.cadence_ms * 1e6)
        self.next_threads = start
        self.next_shot = start if self.a.shot_every > 0 else None
        self.next_module = start + int(1e9 / self.a.module_hz) if self.a.module_hz > 0 else None
        due = start
        while True:
            now = mono()
            if now >= end:
                break
            try:
                fault = self.tick(max(0.0, (now - due) / 1e6))
            except NET_ERRORS as e:
                if not self.handle_unreachable(e):
                    self.exit_reason = 'unreachable'
                    return EXIT_UNREACH
                continue
            if fault:
                return self.on_fault(fault)
            due += cad
            now = mono()
            if due < now - cad:
                due = now
            if due > now:
                time.sleep((due - now) / 1e9)
        self.exit_reason = 'freeze suspected' if self.freeze else 'completed'
        return EXIT_FREEZE if self.freeze else EXIT_OK

    def tick(self, late_ms, light=False):
        self.seq += 1
        t0, w0 = mono(), wall()
        s = {'seq': self.seq, 'mono_ns': t0, 'wall_ns': w0, 'late_ms': round(late_ms, 3)}
        pr = self.pins['enum']['poll_region']
        m = getmem(self.conn, pint(pr['addr']), pint(pr['len']))
        s['enum_status'], s['raw_hex'] = m['status'], m['hex']
        f = decode_enum(m['vals'], self.pins)
        s['fields'] = f
        for key in ('current', 'pending'):
            v = f[key]
            if v and in_kseg(v, 0x40):
                s[key + '_read'] = mem_public(getmem(self.conn, v, 0x40))
        npp = f['node_pool_ptr']
        if npp and in_kseg(npp, 0x200) and (npp != self.last_np_ptr or t0 - self.last_np_mono >= 10**9):
            s['node_pool_read'] = mem_public(getmem(self.conn, npp, 0x200))
            self.last_np_ptr, self.last_np_mono = npp, t0
        if self.trainer_state == 'ON':
            s['status'] = self.read_status()
            if self.next_module is not None and t0 >= self.next_module:
                self.next_module = t0 + int(1e9 / self.a.module_hz)
                self.dump_module()
        s['mono_ns_after'] = mono()
        self.samples.write(s)
        self.samples.sync()
        if self.first_sample is None:
            self.first_sample = {'seq': s['seq'], 'mono_ns': t0}
        self.last_sample = {'seq': s['seq'], 'mono_ns': t0}
        self.events(s)
        self.read_marks()
        if light:
            return None
        fault = None
        if t0 >= self.next_threads:
            self.next_threads = t0 + 10**9
            stopped = self.poll_threads()
            if stopped:
                fault = 'thread stopped: %s' % '; '.join('%s %s' % kv for kv in stopped)
        while not self.nq.empty():
            _, ln = self.nq.get_nowait()
            if ln.strip().lower().startswith(FAULT_NOTIFY_PREFIXES) and fault is None:
                fault = 'notification: %s' % ln.strip()
        if self.next_shot is not None and t0 >= self.next_shot and fault is None:
            self.next_shot = t0 + int(self.a.shot_every * 1e9)
            self.take_shot_and_check_freeze()
        return fault

    def events(self, s):
        f = s['fields']
        cmp = {k: v for k, v in f.items()}
        if self.prev_fields is not None and cmp != self.prev_fields:
            self.change_count += 1
        self.prev_fields = cmp
        cur = f['current']
        if cur is not None and cur != self.prev_current:
            if self.prev_current is not None or cur != 0:
                self.say('ENUM current=0x%x' % cur)
            self.prev_current = cur
        quiet = f['current'] == 0 and f['pending'] == 0 and f['timer_inserted'] == 0
        if quiet:
            if self.quiet_since is None:
                self.quiet_since = s['mono_ns']
            if not self.quiescent_printed and s['mono_ns'] - self.quiet_since >= QUIESCENT_HOLD_NS:
                self.quiescent_printed = True
                self.say('QUIESCENT %.1f' % ((s['mono_ns'] - self.gate_mono) / 1e9))
        else:
            self.quiet_since = None
        st = s.get('status')
        if st is not None and st.get('attached') is not None:
            if self.prev_attached is not None and st['attached'] != self.prev_attached:
                self.say('ATTACHED %d->%d' % (self.prev_attached, st['attached']))
            self.prev_attached = st['attached']

    def read_marks(self):
        p = os.path.join(self.rd, 'marks.in')
        try:
            with open(p, 'rb') as f:
                f.seek(self.marks_off)
                data = f.read()
        except FileNotFoundError:
            return
        if b'\n' not in data:
            return
        complete = data[:data.rindex(b'\n') + 1]
        self.marks_off += len(complete)
        t, w = mono(), wall()
        for ln in complete.decode('utf-8', 'replace').splitlines():
            if ln.strip():
                self.marks_log.write({'mono_ns': t, 'wall_ns': w, 'text': ln.strip()})
        self.marks_log.sync()

    def poll_threads(self):
        t0 = mono()
        r = self.conn.command('threads')
        ids = []
        for ln in r.lines:
            mm = re.match(r'\s*(\d+)', ln)
            if mm:
                ids.append(int(mm.group(1)))
        ids = ids[:128]
        rec = {'mono_ns': t0, 'wall_ns': wall(), 'threads_status': r.status, 'ids': ids, 'isstopped': {},
               'threadinfo': {}}
        stopped = []
        for tid in ids:
            q = self.conn.command('isstopped thread=%d' % tid)
            rec['isstopped'][str(tid)] = q.status
            if (q.status or '').startswith('200'):
                stopped.append((tid, q.status))
            if tid not in self.known_threads:
                ti = self.conn.command('threadinfo thread=%d' % tid)
                rec['threadinfo'][str(tid)] = {'status': ti.status, 'lines': ti.lines}
                self.known_threads.add(tid)
        st = self.conn.command('systime')
        rec['systime'] = st.status
        self.threads_log.write(rec)
        self.threads_log.sync()
        return stopped

    def take_shot(self, dirpath):
        r = self.conn.command('screenshot')
        t = mono()
        rec = {'mono_ns': t, 'status': r.status, 'header_line': r.lines[0] if r.lines else None}
        if r.data is not None:
            os.makedirs(dirpath, exist_ok=True)
            hdr = parse_kv(r.lines[0])
            rec.update(header=hdr, sha256=sha256_bytes(r.data), raw=os.path.join(dirpath, '%d.raw' % t))
            with open(rec['raw'], 'wb') as f:
                f.write(r.data)
            if self.a.png:
                rec['png'] = shot_to_png(r.data, hdr, os.path.join(dirpath, '%d.png' % t))
            write_json(os.path.join(dirpath, '%d.json' % t), rec)
            self.shots += 1
        return rec

    def take_shot_and_check_freeze(self):
        rec = self.take_shot(os.path.join(self.rd, 'shots'))
        if rec.get('sha256') is None:
            return
        self.shot_hist.append((rec['sha256'], self.change_count, rec['mono_ns']))
        last = self.shot_hist[-3:]
        if (not self.freeze and len(last) == 3 and len(set(x[0] for x in last)) == 1
                and len(set(x[1] for x in last)) == 1):
            self.freeze = True
            self.say('FREEZE_SUSPECTED')
            write_json(os.path.join(self.rd, 'freeze-suspected.json'),
                       {'shots': [{'sha256': a, 'enum_change_count': b, 'mono_ns': c} for a, b, c in last],
                        'mono_ns': mono()})
            self.dump('freeze-dump', 'freeze suspected')

    # -- evidence dump (no stop/go/continue/reboot ever)
    def dump(self, dirname, reason, notify_line=None):
        d = os.path.join(self.rd, dirname)
        os.makedirs(d, exist_ok=True)
        res = {'reason': reason, 'mono_ns': mono(), 'wall_ns': wall(), 'errors': [], 'threads': {}}

        def step(name, fn):
            try:
                return fn()
            except Refused:
                raise
            except Exception as e:
                res['errors'].append({'step': name, 'error': repr(e)})
                return None
        tr = step('threads', lambda: self.conn.command('threads'))
        ids = []
        if tr is not None:
            res['threads_reply'] = tr.as_dict()
            for ln in tr.lines:
                mm = re.match(r'\s*(\d+)', ln)
                if mm:
                    ids.append(int(mm.group(1)))
        first_stopped_class = None
        for tid in ids[:128]:
            t = {}
            q = step('isstopped %d' % tid, lambda: self.conn.command('isstopped thread=%d' % tid))
            t['isstopped'] = q.as_dict() if q else None
            ti = step('threadinfo %d' % tid, lambda: self.conn.command('threadinfo thread=%d' % tid))
            t['threadinfo'] = ti.as_dict() if ti else None
            info = parse_kv(' '.join(ti.lines)) if ti else {}
            c1 = step('getcontext %d' % tid,
                      lambda: self.conn.command('getcontext thread=%d control int fp' % tid))
            t['getcontext'] = c1.as_dict() if c1 else None
            ctx = c1
            if c1 is None or not c1.ok:
                c2 = step('getcontext-full %d' % tid, lambda: self.conn.command('getcontext thread=%d full' % tid))
                t['getcontext_full'] = c2.as_dict() if c2 else None
                ctx = c2
            regs = {k.lower(): v for k, v in parse_kv(' '.join(ctx.lines)).items()} if (ctx and ctx.ok) else {}
            t['regs'] = regs
            esp, eip = regs.get('esp'), regs.get('eip')
            if isinstance(esp, int):
                base, limit = info.get('base'), info.get('limit')
                n = 0x100
                if isinstance(base, int) and isinstance(limit, int):
                    top = max(base, limit)
                    n = min(0x200, top - esp) if top > esp else 0
                if n > 0 and esp + n <= (1 << 32):
                    m = step('stack %d' % tid, lambda: getmem(self.conn, esp, n))
                    t['stack'] = mem_public(m) if m else None
            if isinstance(eip, int):
                if eip >= 0x20:
                    m = step('code %d' % tid, lambda: getmem(self.conn, eip - 0x20, 0x40))
                    t['code'] = mem_public(m) if m else None
                t['eip_class'] = classify_pc(eip, self.pins, self.resident)
                if first_stopped_class is None and q is not None and (q.status or '').startswith('200'):
                    first_stopped_class = t['eip_class']
            res['threads'][str(tid)] = t
        pr = self.pins['enum']['poll_region']
        m = step('enum', lambda: getmem(self.conn, pint(pr['addr']), pint(pr['len'])))
        if m:
            res['enum'] = mem_public(m)
            f = decode_enum(m['vals'], self.pins)
            res['enum_fields'] = f
            for key, n in (('current', 0x40), ('pending', 0x40), ('node_pool_ptr', 0x200)):
                v = f[key]
                if v and in_kseg(v, n):
                    mm2 = step(key, lambda: getmem(self.conn, v, n))
                    res[key + '_read'] = mem_public(mm2) if mm2 else None
        if self.trainer_state == 'ON':
            res['module_sha256'] = step('module', lambda: self.dump_module(into=d))
            st = step('status', self.read_status)
            res['trainer_status'] = st
        r = step('modules', lambda: self.conn.command('modules'))
        res['modules'] = r.as_dict() if r else None
        r = step('xbeinfo', lambda: self.conn.command('xbeinfo running'))
        res['xbeinfo'] = r.as_dict() if r else None
        res['screenshot'] = step('screenshot', lambda: self.take_shot(d))
        pc_class = first_stopped_class
        if pc_class is None and notify_line:
            mm = re.search(r'address=(0x[0-9a-fA-F]+)', notify_line)
            if mm:
                pc_class = classify_pc(int(mm.group(1), 16), self.pins, self.resident)
        res['fault_pc_class'] = pc_class
        write_json(os.path.join(d, 'fault.json'), res)
        return res

    def on_fault(self, reason):
        self.say('FAULT %s' % reason)
        nl = reason[len('notification: '):] if reason.startswith('notification: ') else None
        try:
            res = self.dump('fault', reason, notify_line=nl)
            self.fault = {'reason': reason, 'fault_pc_class': res.get('fault_pc_class')}
        except NET_ERRORS as e:
            self.fault = {'reason': reason, 'dump_error': repr(e)}
        end = mono() + int(self.a.post_fault_seconds * 1e9)
        while mono() < end:
            try:
                self.tick(0.0, light=True)
                while not self.nq.empty():
                    self.nq.get_nowait()
            except NET_ERRORS as e:
                self.fault['post_fault_error'] = repr(e)
                break
            time.sleep(1.0)
        self.exit_reason = 'fault'
        return EXIT_FAULT

    def handle_unreachable(self, err):
        self.say('UNREACHABLE')
        t0 = mono()
        ep = {'first_failure_mono_ns': t0, 'error': repr(err), 'attempts': 0, 'pings': None}
        self.close_conn()
        budget = int(self.a.unreachable_budget * 1e9)
        fast = min(int(self.a.reconnect_fast_s * 1e9), budget)

        def attempt():
            ep['attempts'] += 1
            try:
                self.conn = self.connect(timeout=0.5)
                return True
            except NET_ERRORS:
                self.conn = None
                return False
        ok = False
        while mono() - t0 < fast:
            if attempt():
                ok = True
                break
            time.sleep(0.1)
        if not ok:
            ep['pings'] = [ping_once(self.a.ip), ping_once(getattr(self.a, 'title_ip', None))]
            while mono() - t0 < budget:
                if attempt():
                    ok = True
                    break
                time.sleep(0.5)
        ep['returned'] = ok
        ep['elapsed_ms'] = round((mono() - t0) / 1e6, 3)
        self.unreachable_episodes.append(ep)
        if not ok:
            write_json(os.path.join(self.rd, 'unreachable.json'), ep)
            return False
        k = len(self.unreachable_episodes)
        self.dump('fault-after-unreachable-%d' % k, 'reconnected after unreachable')
        if self.notifier is None or not self.notifier.is_alive():
            if self.notifier:
                self.notifier.stop()
            self.notifier = None
            self.open_notify()
        return True


# ---------------------------------------------------------------- probe / recover
def cmd_probe(a, out, pins, pins_sha, rd):
    policy = Policy('probe')
    cmdlog = CommandLog(os.path.join(rd, 'commands.jsonl'))
    manifest = {'argv': list(a.argv), 'subcommand': 'probe', 'tool_sha256': sha256_file(os.path.abspath(__file__)),
                'pins_sha256': pins_sha, 'ip': a.ip, 'run': a.run, 'start_wall_ns': wall(), 'start_mono_ns': mono()}
    write_json(os.path.join(rd, 'manifest.json'), manifest)
    res = {'replies': {}, 'shapes_ok': {}, 'errors': []}
    ok_connect = ok_ver = ok_mem = False
    conn = None
    try:
        conn = Conn(a.ip, a.port, policy, cmdlog, timeout=a.io_timeout)
        ok_connect = True
        res['banner'] = conn.banner
        sh = res['shapes_ok']
        sh['banner'] = conn.banner.startswith('201')
        r = conn.command('dmversion')
        res['replies']['dmversion'] = r.as_dict()
        sh['dmversion'] = ok_ver = (r.status or '').startswith('200')
        r = conn.command('xbeinfo running')
        res['replies']['xbeinfo'] = r.as_dict()
        sh['xbeinfo'] = (((r.status or '').startswith('202') and 'timestamp' in parse_kv(' '.join(r.lines)))
                         or (r.status or '').startswith('402'))
        r = conn.command('modules')
        res['replies']['modules'] = r.as_dict()
        sh['modules'] = (r.status or '').startswith('202') and bool(r.lines) and all('name=' in x for x in r.lines)
        r = conn.command('systime')
        res['replies']['systime'] = r.as_dict()
        sh['systime'] = (r.status or '').startswith('200') and 'high=' in r.status and 'low=' in r.status
        r = conn.command('threads')
        res['replies']['threads'] = r.as_dict()
        ids = [int(x.strip()) for x in r.lines if x.strip().isdigit()]
        sh['threads'] = (r.status or '').startswith('202') and bool(ids) and len(ids) == len(r.lines)
        per = {}
        ti_ok, is_ok, ctx_ok = [], [], []
        for tid in ids[:64]:
            p = {}
            q = conn.command('threadinfo thread=%d' % tid)
            p['threadinfo'] = q.as_dict()
            ti_ok.append((q.status or '').startswith('202') and bool(parse_kv(' '.join(q.lines))))
            q = conn.command('isstopped thread=%d' % tid)
            p['isstopped'] = q.as_dict()
            is_ok.append(bool(re.match(r'^(200|4\d\d)', q.status or '')))
            q = conn.command('getcontext thread=%d control int fp' % tid)
            p['getcontext'] = q.as_dict()
            good = q.ok and {'Eip', 'Esp'} <= set(parse_kv(' '.join(q.lines)))
            if not q.ok:
                q2 = conn.command('getcontext thread=%d full' % tid)
                p['getcontext_full'] = q2.as_dict()
                good = q2.ok and {'Eip', 'Esp'} <= set(parse_kv(' '.join(q2.lines)))
            ctx_ok.append(bool(good))
            per[str(tid)] = p
        res['replies']['per_thread'] = per
        sh['threadinfo'] = bool(ti_ok) and all(ti_ok)
        sh['isstopped'] = bool(is_ok) and all(is_ok)
        sh['getcontext'] = bool(ctx_ok) and all(ctx_ok)
        m = getmem(conn, 0x80010000, 0x40)
        res['replies']['getmem'] = mem_public(m)
        sh['getmem'] = ok_mem = bool(m['hex']) and m['hex'].lower().startswith('4d5a')
        try:
            nc = Conn(a.ip, a.port, policy, cmdlog, timeout=a.io_timeout, name='notify')
            r = nc.command('notify')
            res['replies']['notify'] = r.as_dict()
            sh['notify'] = (r.status or '').startswith('205')
            nc.close()
        except NET_ERRORS as e:
            res['errors'].append({'step': 'notify', 'error': repr(e)})
            sh['notify'] = False
        if a.shot:
            r = conn.command('screenshot')
            hdr = parse_kv(r.lines[0]) if r.lines else {}
            res['replies']['screenshot'] = {'status': r.status, 'header': hdr,
                                            'sha256': sha256_bytes(r.data) if r.data else None}
            sh['screenshot'] = (r.status or '').startswith('203') and r.data is not None \
                and len(r.data) == hdr.get('framebuffersize')
            if r.data:
                with open(os.path.join(rd, 'probe-shot.raw'), 'wb') as f:
                    f.write(r.data)
                if a.png:
                    shot_to_png(r.data, hdr, os.path.join(rd, 'probe-shot.png'))
        conn.command('bye')
    except Refused:
        raise
    except Exception as e:
        res['errors'].append({'step': 'probe', 'error': repr(e)})
    finally:
        if conn:
            conn.close()
    code = EXIT_OK if (ok_connect and ok_ver and ok_mem) else (EXIT_UNREACH if not ok_connect else EXIT_INSTR)
    res['exit_code'] = code
    write_json(os.path.join(rd, 'probe.json'), res)
    cmdlog.sync()
    cmdlog.close()
    manifest.update(end_wall_ns=wall(), end_mono_ns=mono(), exit_code=code)
    write_json(os.path.join(rd, 'manifest.json'), manifest)
    write_json(os.path.join(rd, 'summary.json'), {'exit_code': code, 'mode': 'probe',
                                                  'shapes_ok': res['shapes_ok']})
    out.write('PROBE shapes=%s\nDONE exit=%d\n' % (json.dumps(res['shapes_ok'], sort_keys=True), code))
    out.flush()
    return code


def cmd_recover(a, out):
    ok, reason, g = check_grant(a.grant, a.run)
    if not ok:
        out.write('REFUSED %s\nDONE exit=%d\n' % (reason, EXIT_GATE))
        out.flush()
        return EXIT_GATE
    parent = os.path.join(a.out_root, 'run-%d' % a.run)
    os.makedirs(parent, exist_ok=True)
    rd = os.path.join(parent, 'recover-%d' % wall())
    os.mkdir(rd)
    policy = Policy('recover', grant_command=g['verb'])
    cmdlog = CommandLog(os.path.join(rd, 'commands.jsonl'))
    rec = {'grant': g, 'grant_sha256': sha256_file(a.grant), 'mono_ns': mono(), 'wall_ns': wall()}
    code = EXIT_OK
    try:
        conn = Conn(a.ip, a.port, policy, cmdlog, timeout=a.io_timeout)
        try:
            r = conn.command(g['verb'])
            rec['reply'] = r.as_dict()
        except NET_ERRORS as e:
            rec['reply_error'] = repr(e)
        conn.close()
    except NET_ERRORS as e:
        rec['connect_error'] = repr(e)
        code = EXIT_UNREACH
    cmdlog.sync()
    cmdlog.close()
    write_json(os.path.join(rd, 'recover.json'), rec)
    out.write('RECOVER %s -> %s\nDONE exit=%d\n' % (g['verb'], (rec.get('reply') or {}).get('status'), code))
    out.flush()
    return code


# ---------------------------------------------------------------- cli
def build_parser():
    p = argparse.ArgumentParser(prog='xbdm_observe.py', description=__doc__.split('\n')[0])
    sub = p.add_subparsers(dest='sub', required=True)

    def common(sp):
        sp.add_argument('--ip', required=True)
        sp.add_argument('--run', type=int, required=True)
        sp.add_argument('--out-root', default=DEFAULT_OUT_ROOT)
        sp.add_argument('--pins', default=DEFAULT_PINS)
        sp.add_argument('--port', type=int, default=XBDM_PORT)
        sp.add_argument('--io-timeout', type=float, default=3.0)
        sp.add_argument('--png', action='store_true', help='also convert screenshots to PNG')

    def obs(sp, wait_default):
        sp.add_argument('--wait-title', type=float, default=wait_default)
        sp.add_argument('--duration', type=float, default=120.0)
        sp.add_argument('--cadence-ms', type=float, default=50.0)
        sp.add_argument('--module-hz', type=float, default=1.0)
        sp.add_argument('--shot-every', type=float, default=10.0)
        sp.add_argument('--mark', default=None)
        sp.add_argument('--attach-now', action='store_true')
        sp.add_argument('--title-ip', default=None)
        sp.add_argument('--post-fault-seconds', type=float, default=10.0)
        sp.add_argument('--unreachable-budget', type=float, default=60.0)
        sp.add_argument('--reconnect-fast-s', type=float, default=3.0)

    sp = sub.add_parser('probe')
    common(sp)
    sp.add_argument('--shot', action='store_true')
    sp = sub.add_parser('observe')
    common(sp)
    obs(sp, 600.0)
    sp = sub.add_parser('launch-observe')
    common(sp)
    obs(sp, 90.0)
    sp.add_argument('--xbe', required=True)
    sp.add_argument('--dir', required=True)
    sp.add_argument('--identity', required=True)
    sp = sub.add_parser('recover')
    common(sp)
    sp.add_argument('--grant', required=True)
    return p


def main(argv=None, out=None):
    out = out or sys.stdout
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        a = build_parser().parse_args(argv)
    except SystemExit as e:
        return EXIT_GATE if e.code else EXIT_OK
    a.argv = argv
    if a.sub == 'recover':
        return cmd_recover(a, out)
    try:
        pins, pins_sha = load_pins(a.pins)
    except (OSError, ValueError) as e:
        out.write('REFUSED pins unreadable: %r\nDONE exit=%d\n' % (e, EXIT_INSTR))
        return EXIT_INSTR
    if a.sub in ('observe', 'launch-observe'):
        if a.cadence_ms < 20:
            out.write('REFUSED --cadence-ms must be >= 20\nDONE exit=2\n')
            return EXIT_GATE
        if a.module_hz < 0 or a.shot_every < 0 or a.duration <= 0:
            out.write('REFUSED bad numeric option\nDONE exit=2\n')
            return EXIT_GATE
    if a.sub == 'launch-observe':
        ok, reason = check_receipt(a.identity, a.xbe, pins)
        if not ok:
            out.write('REFUSED %s\nDONE exit=%d\n' % (reason, EXIT_GATE))
            out.flush()
            return EXIT_GATE
    try:
        rd = make_run_dir(a.out_root, a.run)
    except FileExistsError:
        out.write('REFUSED run directory exists: run-%d\nDONE exit=%d\n' % (a.run, EXIT_GATE))
        out.flush()
        return EXIT_GATE
    if a.sub == 'probe':
        try:
            return cmd_probe(a, out, pins, pins_sha, rd)
        except Refused as e:
            out.write('REFUSED %s\nDONE exit=2\n' % e)
            return EXIT_GATE
    return Observer(a, pins, pins_sha, rd, out, a.sub).run()


if __name__ == '__main__':
    sys.exit(main())
