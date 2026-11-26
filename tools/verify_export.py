#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build and test a fresh export of the Git-visible tree (no game files).
Supply --xbe explicitly for the CPU-emulated tests; the XBE is read-only and
is never copied. All scratch output lives under build/.
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
REPO = ROOT.parent
EXPECTED = {
    'Trainers/OG-AmpJack.bin': '5e63fb1afb9c26d15af8165471e2a982171db1f1e9a2fc6c4d6114bd148ec39c',
    'Trainers/OG-AmpJack.xbtf': '8090175b317cfa28b2a83e16a84ab798e8d62935351db40bfe14d66d0569e817',
}
ZIP_NAME = 'OG-AmpJack-v0.1.0.zip'

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
    scratch = REPO/'build'/'.verification-work'
    scratch.mkdir(parents=True,exist_ok=True)
    env = dict(os.environ, TMPDIR=str(scratch), PYTHONDONTWRITEBYTECODE='1')
    for key in ('AMPJACK_TEST_XBE','AMPJACK_TEST_OUT','PYTHONPATH'):
        env.pop(key,None)
    reference = REPO/'build'
    run([sys.executable,ROOT/'build.py','--out',reference],REPO,env)
    for name, digest in EXPECTED.items():
        assert sha(reference/name) == digest, 'release artifact differs: '+name
    visible = sorted(set(filter(None,subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=REPO).decode().split('\0'))))
    paths = [p for p in visible if (REPO/p).is_file()]
    for name in ('tools/inputs/module.bin','tools/inputs/module.elf','tools/inputs/layout.json','tools/inputs/pins.h','tools/inputs/provenance.json'):
        assert name in paths, 'required input ignored: '+name
    for p in paths:
        assert Path(p).suffix.lower() not in ('.xbe','.rom','.iso','.log','.pcap','.vhd','.qcow2','.env','.zip'), p
        data = (REPO/p).read_bytes()
        for marker in (bytes([47])+b'home/',bytes([47])+b'Users/',b'-----BEGIN '+b'PRIVATE KEY',b'-----BEGIN '+b'OPENSSH PRIVATE KEY',b'gh'+b'p_',b'github'+b'_pat_'):
            assert marker not in data, (p,marker)
    required = [p for p in paths if p.startswith(('src/','tools/','tests/')) or p == 'LICENSE']
    with tempfile.TemporaryDirectory(prefix='fresh-export-',dir=scratch) as td:
        clean = Path(td)
        for name in required:
            dest = clean/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(REPO/name,dest)
        # Build into a new output, never reuse the reference build as proof.
        out = clean/'build'
        run([sys.executable,clean/'tools/build.py','--out',out],clean,env)
        compared = ['manifest.json','SHA256SUMS',ZIP_NAME,*EXPECTED]
        for name in compared:
            assert (out/name).read_bytes() == (reference/name).read_bytes(), name
        package_log = run([sys.executable,'-m','unittest','discover','-s',clean/'tests','-p','test_release.py'],clean,env)
        assert 'CPU-emulated trainer tests NOT RUN' in package_log
        strict_env = dict(env,AMPJACK_TEST_XBE=str(a.xbe.resolve()),AMPJACK_TEST_OUT=str(out))
        strict_log = run([sys.executable,'-m','unittest','discover','-s',clean/'tests','-p','test_release.py'],clean,strict_env)
        package_match = re.search(r'Ran (\d+) tests',package_log)
        strict_match = re.search(r'Ran (\d+) tests',strict_log)
        assert package_match is not None and strict_match is not None
        package_count = int(package_match[1])
        strict_count = int(strict_match[1])
        assert package_count == 4 and strict_count == 11, (package_count, strict_count)
        for name in compared:
            assert (out/name).read_bytes() == (reference/name).read_bytes(), 'tested release differs: '+name
        reloc = run(['readelf','-r',out/'.build/bootstrap.elf'],clean,env)
        assert 'There are no relocations' in reloc
        manifest = json.loads((out/'manifest.json').read_text())
        provenance = manifest['provenance']
        assert manifest['payload_sha256'] == EXPECTED['Trainers/OG-AmpJack.bin']
        tree = ast.parse((clean/'tests/wrapper_harness.py').read_text())
        cases = next(n.iter.elts for n in ast.walk(tree) if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='case' and isinstance(n.iter,ast.List))
        extra = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='EXTRA_IMPORTS' for t in n.targets))
        result = {
            'status':'COMPLETE', 'scope':'fresh-export packaging and CPU-emulated trainer execution',
            'fresh_export_package_tests':package_count, 'fresh_export_strict_total_tests':strict_count,
            'strict_cpu_test_methods':strict_count-package_count, 'negative_cases':len(cases),
            'extra_import_rejection_cases':len(extra)*2,
            'bases':['0x01000000','0x83000000'], 'exact_source_files':len(provenance['controller_sources'])+len(provenance['trainer_sources']),
            'entry_argument':0, 'payload_byte_identical':True,
            'resident_alloc':manifest['resident_alloc'], 'file_buffer_alloc':manifest['file_buffer_alloc'],
            'image_size':manifest['image_size'], 'mem_end':manifest['mem_end'],
            'trainer_decoded_bytes':manifest['trainer_decoded_bytes'], 'trainer_file_bytes':manifest['trainer_file_bytes'],
            'trainer_stub_bytes':manifest['bootstrap_symbols']['boot_end'], 'sha256':{n:sha(out/n) for n in compared},
            'exported_path_count':len(required)}
        (scratch/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))

if __name__ == '__main__':
    main()
