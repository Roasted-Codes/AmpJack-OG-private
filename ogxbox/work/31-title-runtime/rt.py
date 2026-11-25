#!/usr/bin/env python3
"""rt.py — worker17 runtime helper (devkit xemu on the private desktop :2).
Writes evidence to THIS folder (work/31-title-runtime), never the old runs.
  rt.py status                 -> QMP query-status JSON
  rt.py hmp  '<cmd>'           -> human-monitor-command
  rt.py qmp  '{"execute":...}' -> raw QMP
  rt.py gdb                    -> HMP gdbserver tcp:127.0.0.1:1236
  rt.py win                    -> devkit window id (match by /proc/PID/cmdline)
  rt.py shot NAME              -> screenshots/NAME.png (import -window)
  rt.py key [--hold s] [--gap s] k...  -> XSendEvent keydown/keyup --window
  rt.py quit                   -> QMP quit
"""
import os, subprocess, sys, time, json
from pathlib import Path

HOME = Path.home()
sys.path.insert(0, str(HOME / 'Desktop/Xbox/LAN_Stats/tools/xemu'))
DK = '/home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work/31-title-runtime/guest'
QSOCK = DK + '/runtime/qmp.sock'
PORT = 1239
HERE = Path(__file__).resolve().parent
SHOTS = HERE / 'screenshots'
ENV = dict(os.environ, **json.loads(Path('/home/roasted/Desktop/_Parked/halo2-system-link-bridge/network-lab/isolated-desktop/environment.json').read_text()), LD_LIBRARY_PATH=str(HOME / '.local/lib'))
ENV.pop('XAUTHORITY', None)
ENV.pop('SDL_VIDEO_DRIVER', None)
ENV.pop('LIBGL_ALWAYS_SOFTWARE', None)
XD = str(HOME / '.local/bin/xdotool')


def run(*a):
    return subprocess.run(a, env=ENV, capture_output=True, text=True, check=True).stdout.strip()


def win():
    for w in run(XD, 'search', '--name', 'xemu').split():
        try:
            pid = run(XD, 'getwindowpid', w)
            cmd = open(f'/proc/{pid}/cmdline', 'rb').read().decode(errors='replace')
            if DK + '/' in cmd:
                return w
        except Exception:
            pass
    raise SystemExit('devkit window not found')


def qmp():
    from qmp import QMP
    return QMP(QSOCK)


def main():
    op = sys.argv[1]
    if op == 'status':
        q = qmp(); print(json.dumps(q.cmd('query-status'))); q.close()
    elif op == 'hmp':
        q = qmp(); print(q.hmp(sys.argv[2]), end=''); q.close()
    elif op == 'qmp':
        j = json.loads(sys.argv[2]); q = qmp()
        r = q.cmd(j['execute'], **j.get('arguments', {})); q.close()
        print(json.dumps(r) if not isinstance(r, str) else r)
    elif op == 'gdb':
        q = qmp(); print(q.hmp(f'gdbserver tcp:127.0.0.1:{PORT}'), end=''); q.close()
    elif op == 'win':
        print(win())
    elif op == 'shot':
        SHOTS.mkdir(parents=True, exist_ok=True)
        p = SHOTS / f'{sys.argv[2]}.png'
        subprocess.run(['import', '-display', ENV['DISPLAY'], '-window', win(), str(p)],
                       env=ENV, check=True)
        print(p)
    elif op == 'key':
        a = sys.argv[2:]; hold = 0.08; gap = 0.8
        while a and a[0] in ('--hold', '--gap'):
            if a[0] == '--hold': hold = float(a[1])
            else: gap = float(a[1])
            a = a[2:]
        w = win()
        run(XD, 'windowactivate', '--sync', w); time.sleep(0.3)
        run(XD, 'windowfocus', '--sync', w); time.sleep(0.2)
        assert run(XD, 'getwindowfocus') == w, 'Private emulator focus not established'
        for k in a:
            if k.startswith('sleep:'):
                time.sleep(float(k[6:])); continue
            run(XD, 'keydown', k); time.sleep(hold)
            run(XD, 'keyup', k); time.sleep(gap)
        print('keys', *a, time.strftime('%H:%M:%S'))
    elif op == 'quit':
        q = qmp(); print(q.cmd('quit')); q.close()


if __name__ == '__main__':
    main()
