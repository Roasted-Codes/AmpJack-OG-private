#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build and test a fresh Git-visible source/package export (no game export).
All writable scratch lives below this package. Supply --xbe explicitly for the
strict production-wrapper tests; the external owner title is read-only.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(args, cwd, env):
    print('RUN', ' '.join(map(str,args)), flush=True)
    p = subprocess.run(list(map(str,args)),cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    print(p.stdout,flush=True)
    assert p.returncode == 0, (args,p.returncode)
    return p.stdout

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--xbe',type=Path,required=True)
    a = ap.parse_args()
    assert a.xbe.is_file()
    scratch = ROOT/'.verification-work'
    scratch.mkdir(exist_ok=True)
    env = dict(os.environ, TMPDIR=str(scratch), PYTHONDONTWRITEBYTECODE='1')
    for key in ('AMPJACK_TEST_XBE','AMPJACK_TEST_OUT','PYTHONPATH'):
        env.pop(key,None)
    run([sys.executable,ROOT/'build.py'],REPO,env)
    visible = sorted(set(filter(None,subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=REPO).decode().split('\0'))))
    prefix = ROOT.relative_to(REPO).as_posix()+'/'
    paths = [p for p in visible if p.startswith(prefix)]
    paths = [p for p in paths if (REPO/p).is_file()]
    for name in ('inputs/module.bin','inputs/module.elf','dist/candidate/OG-AmpJack.bin','dist/candidate/OG-AmpJack.xbtf','dist/OG-AmpJack-v0.1.0-preview.1.zip'):
        assert prefix+name in paths, 'required artifact ignored: '+name
    changed = subprocess.check_output(['git','diff','--name-only'],cwd=REPO,text=True).splitlines()
    assert all(p.startswith(prefix) for p in changed), 'tracked files changed outside package'
    for p in paths:
        assert Path(p).suffix.lower() not in ('.xbe','.rom','.iso','.log','.pcap','.vhd','.qcow2','.env'), p
        data = (REPO/p).read_bytes()
        for marker in (bytes([47])+b'home/',bytes([47])+b'Users/',b'-----BEGIN '+b'PRIVATE KEY',b'-----BEGIN '+b'OPENSSH PRIVATE KEY',b'gh'+b'p_',b'github'+b'_pat_'):
            assert marker not in data, (p,marker)
    required = [p for p in visible if (REPO/p).is_file() and (p.startswith((prefix,'ogxbox/work/65-bisect/rumble/src/')) or p == 'tools/trainerfmt.py')]
    with tempfile.TemporaryDirectory(prefix='fresh-export-',dir=scratch) as td:
        clean = Path(td)
        for name in required:
            dest = clean/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(REPO/name,dest)
        child = clean/prefix
        # Build into a new output, never consume the exported dist as proof.
        out = clean/'fresh-output'
        run([sys.executable,child/'build.py','--out',out],clean,env)
        compared = ['manifest.json','SHA256SUMS','OG-AmpJack-v0.1.0-preview.1.zip','candidate/OG-AmpJack.bin','candidate/OG-AmpJack.xbtf']
        for name in compared:
            assert (out/name).read_bytes() == (ROOT/'dist'/name).read_bytes(), name
        package_log = run([sys.executable,'-m','unittest','discover','-s',child,'-p','test_release.py'],clean,env)
        assert 'Strict actual-wrapper CPU tests NOT RUN' in package_log
        strict_env = dict(env,AMPJACK_TEST_XBE=str(a.xbe.resolve()),AMPJACK_TEST_OUT=str(out))
        strict_log = run([sys.executable,'-m','unittest','discover','-s',child,'-p','test_release.py'],clean,strict_env)
        package_match = re.search(r'Ran (\d+) tests',package_log)
        strict_match = re.search(r'Ran (\d+) tests',strict_log)
        assert package_match is not None and strict_match is not None
        package_count = int(package_match[1])
        strict_count = int(strict_match[1])
        assert package_count == 4 and strict_count == 11
        for name in compared:
            assert (out/name).read_bytes() == (ROOT/'dist'/name).read_bytes(), 'tested release differs: '+name
        reloc = run(['readelf','-r',out/'.build/bootstrap.elf'],clean,env)
        assert 'There are no relocations' in reloc
        manifest = json.loads((out/'manifest.json').read_text())
        provenance = manifest['provenance']
        assert manifest['payload_sha256'] == '5e63fb1afb9c26d15af8165471e2a982171db1f1e9a2fc6c4d6114bd148ec39c'
        tree = ast.parse((child/'wrapper_harness.py').read_text())
        cases = next(n.iter.elts for n in ast.walk(tree) if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='case' and isinstance(n.iter,ast.List))
        extra = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='EXTRA_IMPORTS' for t in n.targets))
        result = {
            'status':'COMPLETE', 'scope':'portable selected-W65R packaging and host execution only',
            'hardware':'Renamed wrapper UNTESTED until one console launch; original owner-reported working input and rumble',
            'fresh_export_package_tests':package_count, 'fresh_export_strict_total_tests':strict_count,
            'strict_cpu_test_methods':strict_count-package_count, 'preserved_negative_cases':len(cases),
            'extra_import_rejection_cases':len(extra)*2, 'logging':'not present in W65R',
            'bases':['0x01000000','0x83000000'], 'exact_source_files':len(provenance['controller_sources']),
            'entry_argument':0, 'payload_byte_identical_to_selected':True,
            'resident_alloc':manifest['resident_alloc'], 'file_buffer_alloc':manifest['file_buffer_alloc'],
            'image_size':manifest['image_size'], 'mem_end':manifest['mem_end'],
            'native_peak':manifest['resident_alloc']+manifest['file_buffer_alloc'],
            'trainer_decoded_bytes':manifest['trainer_decoded_bytes'], 'trainer_file_bytes':manifest['trainer_file_bytes'],
            'wrapper_bytes':manifest['bootstrap_symbols']['boot_end'], 'sha256':{n:sha(out/n) for n in compared},
            'elf_sha256':manifest['elf_sha256'], 'selected_live_evidence':provenance['selected_live_evidence'],
            'checks':['fresh export needs no original workspace or bundled game/SDK',
                      'fresh-output pair/ZIP/manifest/sums byte-identical before and after strict tests',
                      'actual production XBTF wrapper executed, not a synthetic wrapper',
                      'exact selected module and full source coverage; no embedded own payload path',
                      'original W65R loader/bootstrap/SHA unchanged; generated pins path renamed only',
                      'compiled renamed native path observed during open; real cdecl null entry at two bases',
                      'default-OFF/title/payload/allocation/I-O guards preserved',
                      'current-site rollback and permanent-failure fail-stop preserved',
                      'no dynamic wrapper relocations; fits XBMC heap; exact ZIP allowlist',
                      'Git-visible package inventory and absolute-path/credential-marker scan'],
            'package_path_count':len(paths), 'package_paths':paths}
        (ROOT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))

if __name__ == '__main__':
    main()
