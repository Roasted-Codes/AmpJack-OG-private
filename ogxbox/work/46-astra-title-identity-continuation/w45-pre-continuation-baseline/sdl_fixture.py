#!/usr/bin/env python3
import sys
sys.dont_write_bytecode = True
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from parent_launch import ROOT, GUEST, receipt, environment, command

def child():
    s = C.CDLL('/usr/lib/libSDL3.so.0')
    libc = C.CDLL(None)
    libc.getauxval.argtypes = [C.c_ulong]
    libc.getauxval.restype = C.c_ulong
    s.SDL_Init.argtypes = [C.c_uint32]
    s.SDL_Init.restype = C.c_bool
    s.SDL_GetError.restype = C.c_char_p
    s.SDL_GetCurrentVideoDriver.restype = C.c_char_p
    s.SDL_CreateWindow.argtypes = [C.c_char_p, C.c_int, C.c_int, C.c_uint64]
    s.SDL_CreateWindow.restype = C.c_void_p
    s.SDL_ShowWindow.argtypes = [C.c_void_p]
    s.SDL_ShowWindow.restype = C.c_bool
    s.SDL_GetWindowProperties.argtypes = [C.c_void_p]
    s.SDL_GetWindowProperties.restype = C.c_uint32
    s.SDL_GetNumberProperty.argtypes = [C.c_uint32, C.c_char_p, C.c_int64]
    s.SDL_GetNumberProperty.restype = C.c_int64
    s.SDL_DestroyWindow.argtypes = [C.c_void_p]
    result = {'pid': os.getpid(), 'uid': os.getuid(), 'euid': os.geteuid(), 'at_secure': libc.getauxval(23), 'cwd': os.getcwd(), 'env': {k:v for k,v in os.environ.items() if k.startswith(('SDL','VK_','MESA','LIBGL','GALLIUM','DRI_','XDG_')) or k in ('DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','TMPDIR','PYTHONDONTWRITEBYTECODE')}, 'xauthority_present': 'XAUTHORITY' in os.environ, 'sdl_path': str(Path('/usr/lib/libSDL3.so.0').resolve()), 'sdl_sha256': hashlib.sha256(Path('/usr/lib/libSDL3.so.0').read_bytes()).hexdigest(), 'sdl_version': s.SDL_GetVersion()}
    w = None
    try:
        if not s.SDL_Init(0x20):
            raise RuntimeError('SDL_Init: ' + s.SDL_GetError().decode())
        result['driver'] = s.SDL_GetCurrentVideoDriver().decode()
        w = s.SDL_CreateWindow(b'W45 SDL3 private X11 qualification', 400, 240, 0)
        if not w:
            raise RuntimeError('SDL_CreateWindow: ' + s.SDL_GetError().decode())
        if not s.SDL_ShowWindow(w):
            raise RuntimeError('SDL_ShowWindow: ' + s.SDL_GetError().decode())
        props = s.SDL_GetWindowProperties(w)
        result['x11_window_id'] = s.SDL_GetNumberProperty(props, b'SDL.window.x11.window', 0)
        for _ in range(30):
            s.SDL_PumpEvents()
            time.sleep(0.05)
        if result['driver'] != 'x11' or not result['x11_window_id']:
            raise RuntimeError('backend/window identity rejected')
        # Query the same X server independently through Xlib, no focus/input changes.
        x = C.CDLL('libX11.so.6')
        x.XOpenDisplay.argtypes = [C.c_char_p]
        x.XOpenDisplay.restype = C.c_void_p
        x.XFetchName.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_void_p)]
        x.XCloseDisplay.argtypes = [C.c_void_p]
        x.XFree.argtypes = [C.c_void_p]
        d = x.XOpenDisplay(b':2')
        if not d:
            raise RuntimeError('independent XOpenDisplay :2 failed')
        name = C.c_void_p()
        try:
            # SDL3 uses EWMH UTF8 _NET_WM_NAME; legacy WM_NAME need not exist.
            result['legacy_name_available'] = bool(x.XFetchName(d, result['x11_window_id'], C.byref(name)))
            if name.value:
                result['x11_name'] = C.string_at(name).decode()
                x.XFree(name)
            x.XGetGeometry.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_int), C.POINTER(C.c_int), C.POINTER(C.c_uint), C.POINTER(C.c_uint), C.POINTER(C.c_uint), C.POINTER(C.c_uint)]
            root = C.c_ulong()
            px, py = C.c_int(), C.c_int()
            width, height, border, depth = C.c_uint(), C.c_uint(), C.c_uint(), C.c_uint()
            if not x.XGetGeometry(d, result['x11_window_id'], C.byref(root), C.byref(px), C.byref(py), C.byref(width), C.byref(height), C.byref(border), C.byref(depth)):
                raise RuntimeError('independent XGetGeometry failed')
            result['independent_x11_geometry'] = {'root': root.value, 'width': width.value, 'height': height.value, 'depth': depth.value}
            if (width.value, height.value) != (400, 240):
                raise RuntimeError('independent X11 window geometry mismatch')
        finally:
            x.XCloseDisplay(d)
        result['passed'] = True
    except Exception as error:
        result.update(passed=False, error=str(error))
    finally:
        if w:
            s.SDL_DestroyWindow(w)
        s.SDL_Quit()
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result['passed'] else 1

def main():
    if sys.argv[1:] == ['--child']:
        return child()
    lease = receipt()
    env = environment(lease)
    cmd = ['/usr/bin/python3', '-B', str(ROOT / 'sdl_fixture.py'), '--child']
    start = time.time()
    run = subprocess.run(cmd, env=env, cwd=GUEST, capture_output=True, text=True, timeout=20)
    evidence = {'command': cmd, 'cwd': str(GUEST), 'start_epoch': start, 'end_epoch': time.time(), 'returncode': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr, 'guarded_command_not_executed': command(lease, env)}
    path = ROOT / 'fixture-result.json'
    if path.exists():
        prior = path.read_text()
        (ROOT / ('fixture-prior-' + str(time.time_ns()) + '.json')).write_text(prior)
    path.write_text(json.dumps(evidence, indent=2)+'\n')
    print(json.dumps(evidence, indent=2))
    return run.returncode

if __name__ == '__main__':
    sys.exit(main())
