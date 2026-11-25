#!/usr/bin/env python3
"""_finalize.py - re-run the suite twice, compute deliverable hashes, write RESULT.json (worker housekeeping)."""
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ['xbdm_observe.py', 'analyze_run.py', 'fake_xbdm.py', 'test_xbdm_observe.py', 'stage_ftp.py',
         'README-RUN.md', 'REPORT.md', 'REFUSALS.md', '_finalize.py']


def run_suite(i):
    p = subprocess.run(['/usr/bin/python3', '-B', '-m', 'unittest', '-v', 'test_xbdm_observe'], cwd=HERE,
                       capture_output=True, text=True, timeout=600)
    log = p.stdout + p.stderr
    with open(os.path.join(HERE, 'test-run-%d.log' % i), 'w') as f:
        f.write(log)
    ran = int(re.search(r'Ran (\d+) tests', log).group(1))
    failed = sorted(set(re.findall(r'^(test_\w+) \(.*\) \.\.\. (?:FAIL|ERROR)', log, re.M)))
    ok = p.returncode == 0
    return {'ran': ran, 'passed': ran - len(failed) if ok or failed else 0, 'failed': failed, 'rc': p.returncode}


runs = [run_suite(1), run_suite(2)]
try:
    os.unlink(os.path.join(HERE, 'test-run.log'))
except FileNotFoundError:
    pass
leftover = [d for d in os.listdir(HERE) if d.startswith('test-run-') and os.path.isdir(os.path.join(HERE, d))]
files = {}
for n in FILES:
    with open(os.path.join(HERE, n), 'rb') as f:
        files[n] = hashlib.sha256(f.read()).hexdigest()
last = runs[-1]
all_green = all(r['rc'] == 0 for r in runs)
result = {
    'status': 'COMPLETE' if all_green else 'PARTIAL',
    'tests': {'ran': last['ran'], 'passed': last['passed'], 'failed': sorted(set(sum((r['failed'] for r in runs), []))),
              'runs': runs, 'command': 'cd opus-F && /usr/bin/python3 -B -m unittest -v test_xbdm_observe',
              'leftover_temp_dirs': leftover},
    'files': files,
    'p3': ['stage_ftp.py (list, fetch-hash, put-verify; mock-FTP tested)', 'PNG conversion for screenshots (--png)'],
    'not_done': ['no live run (by design; parent runs probe first)',
                 'freeze detection implemented but has no dedicated test',
                 'PNG conversion only for 32bpp X8R8G8B8; other formats stay raw',
                 'XBDM reply shapes unverified on the real 1.00.5455.1 monitor until probe'],
    'live_actions': 0,
    'pins_sha256': 'a34d3deac8feb3ee4e4a33c9e63c032268ac727c3b420e39e756ae29b1317079',
}
with open(os.path.join(HERE, 'RESULT.json'), 'w') as f:
    json.dump(result, f, indent=1, sort_keys=True)
print(json.dumps({'status': result['status'], 'runs': runs, 'leftover': leftover}, indent=1))
sys.exit(0 if all_green else 1)
