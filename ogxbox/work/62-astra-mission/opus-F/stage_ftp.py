#!/usr/bin/env python3
"""stage_ftp.py - stdlib ftplib staging helper for the owner's Xbox FTP server (XBMC FTP).

  stage_ftp.py --host H [--port 21] --cred-file F list <dir>
  stage_ftp.py --host H --cred-file F fetch-hash <remote> [--receipt out.json] [--console-path "F:\\..."]
  stage_ftp.py --host H --cred-file F put-verify <local> <remote-dir> <basename> [--receipt out.json]
                                                [--console-path "F:\\...\\basename"]

The cred file holds two lines (user, password); neither is ever printed or logged.
No delete, no rename, no overwrite: put-verify refuses when the basename already exists in NLST, STORs
the file, RETRs it back and requires an identical sha256.  The receipt json (console_path, size, sha256,
verified_epoch) is the --identity input of xbdm_observe.py launch-observe.
Exit codes: 0 ok, 1 verify mismatch, 2 refused/bad args, 5 connection/ftp error.
"""
import argparse
import ftplib
import hashlib
import json
import os
import re
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))


class Refused(Exception):
    pass


def read_creds(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    if len(lines) < 2 or not lines[0]:
        raise Refused('cred file must hold two lines: user, password')
    return lines[0].strip(), lines[1]


def ftp_to_console_path(remote):
    """'/F/Games/h2/default.xbe' -> 'F:\\Games\\h2\\default.xbe' (XBMC FTP drive layout)."""
    m = re.match(r'^/([A-Za-z])(/.*)?$', remote.replace('\\', '/'))
    if not m:
        return None
    rest = (m.group(2) or '/').replace('/', '\\')
    return '%s:%s' % (m.group(1).upper(), rest)


def connect(host, port, cred_file, timeout=30, factory=ftplib.FTP):
    user, pw = read_creds(cred_file)
    ftp = factory()
    ftp.connect(host, port, timeout=timeout)
    ftp.login(user, pw)
    try:
        ftp.voidcmd('TYPE I')
    except (ftplib.Error, AttributeError):
        pass
    return ftp


def nlst(ftp):
    try:
        return [n.replace('\\', '/').rstrip('/').split('/')[-1] for n in ftp.nlst()]
    except ftplib.error_perm as e:       # many servers answer 550 for an empty directory
        if str(e).startswith('550'):
            return []
        raise


def retr_hash(ftp, name, keep_path=None):
    h = hashlib.sha256()
    n = [0]
    out = open(keep_path, 'wb') if keep_path else None

    def cb(b):
        h.update(b)
        n[0] += len(b)
        if out:
            out.write(b)
    try:
        ftp.retrbinary('RETR ' + name, cb, blocksize=65536)
    finally:
        if out:
            out.close()
    return n[0], h.hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return os.path.getsize(path), h.hexdigest()


def write_receipt(path, rec):
    if not path:
        return
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(rec, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def do_list(ftp, d):
    ftp.cwd(d)
    return nlst(ftp)


def do_fetch_hash(ftp, remote, receipt=None, console_path=None, tmpdir=None):
    fd, tmp = tempfile.mkstemp(prefix='ftp-fetch-', dir=tmpdir or HERE)
    os.close(fd)
    try:
        size, sha = retr_hash(ftp, remote, keep_path=tmp)
        lsize, lsha = file_hash(tmp)
    finally:
        os.unlink(tmp)
    if (lsize, lsha) != (size, sha):
        raise ftplib.Error('temp file differs from stream')
    rec = {'remote': remote, 'console_path': console_path or ftp_to_console_path(remote), 'size': size,
           'sha256': sha, 'verified_epoch': time.time(), 'method': 'ftp RETR'}
    write_receipt(receipt, rec)
    return rec


def do_put_verify(ftp, local, rdir, base, receipt=None, console_path=None):
    if not base or '/' in base or '\\' in base or base in ('.', '..'):
        raise Refused('basename must be a plain file name')
    if not os.path.isfile(local):
        raise Refused('local file missing')
    ftp.cwd(rdir)
    if base.lower() in [n.lower() for n in nlst(ftp)]:      # FATX is case-insensitive
        raise Refused('%s already exists in %s; no overwrite' % (base, rdir))
    size, sha = file_hash(local)
    with open(local, 'rb') as f:
        ftp.storbinary('STOR ' + base, f, blocksize=65536)
    rsize, rsha = retr_hash(ftp, base)
    remote = rdir.rstrip('/') + '/' + base
    rec = {'remote': remote, 'console_path': console_path or ftp_to_console_path(remote), 'size': size,
           'sha256': sha, 'readback_size': rsize, 'readback_sha256': rsha, 'method': 'ftp STOR+RETR'}
    if (rsize, rsha) == (size, sha):
        rec['verified_epoch'] = time.time()
        rec['verified'] = True
    else:
        rec['verified'] = False
    write_receipt(receipt, rec)
    return rec


def main(argv=None, factory=ftplib.FTP, out=None):
    out = out or sys.stdout
    p = argparse.ArgumentParser(prog='stage_ftp.py')
    p.add_argument('--host', required=True)
    p.add_argument('--port', type=int, default=21)
    p.add_argument('--cred-file', required=True)
    p.add_argument('--timeout', type=float, default=30)
    sub = p.add_subparsers(dest='sub', required=True)
    s = sub.add_parser('list')
    s.add_argument('dir')
    s = sub.add_parser('fetch-hash')
    s.add_argument('remote')
    s.add_argument('--receipt')
    s.add_argument('--console-path')
    s = sub.add_parser('put-verify')
    s.add_argument('local')
    s.add_argument('remote_dir')
    s.add_argument('basename')
    s.add_argument('--receipt')
    s.add_argument('--console-path')
    try:
        a = p.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    ftp = None
    try:
        ftp = connect(a.host, a.port, a.cred_file, a.timeout, factory)
        if a.sub == 'list':
            for n in do_list(ftp, a.dir):
                out.write(n + '\n')
            code = 0
        elif a.sub == 'fetch-hash':
            r = do_fetch_hash(ftp, a.remote, a.receipt, a.console_path)
            out.write('size=%d sha256=%s console_path=%s\n' % (r['size'], r['sha256'], r['console_path']))
            code = 0
        else:
            r = do_put_verify(ftp, a.local, a.remote_dir, a.basename, a.receipt, a.console_path)
            out.write('size=%d sha256=%s readback_sha256=%s verified=%s\n'
                      % (r['size'], r['sha256'], r['readback_sha256'], r['verified']))
            code = 0 if r['verified'] else 1
    except Refused as e:
        out.write('REFUSED %s\n' % e)
        code = 2
    except (OSError, EOFError, ftplib.Error) as e:
        out.write('FTP_ERROR %s\n' % type(e).__name__)     # message may echo server text; keep it terse
        code = 5
    finally:
        if ftp is not None:
            try:
                ftp.quit()
            except Exception:
                pass
    out.flush()
    return code


if __name__ == '__main__':
    sys.exit(main())
