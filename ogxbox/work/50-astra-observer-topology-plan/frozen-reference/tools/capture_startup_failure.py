#!/usr/bin/env python3
"""Read only NEW W45 unit journal, bound to a recorded invocation; no launch."""
import sys
sys.dont_write_bytecode = True
import json
from pathlib import Path
import subprocess
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parent_launch import ROOT, receipt, DIGEST

def main():
    lease = receipt()
    claim = json.loads((ROOT/'runtime-claim.json').read_text())
    handle = json.loads((ROOT/'launch-handle.json').read_text())
    if claim.get('receipt_sha256') != DIGEST or handle.get('receipt_sha256') != DIGEST:
        raise ValueError('unbound claim or launch handle')
    unit = lease['unit']
    invocation = handle['invocation_id']
    if handle['unit'] != unit or len(invocation) != 32 or any(c not in '0123456789abcdef' for c in invocation):
        raise ValueError('wrong unit or invalid invocation')
    cmd = ['journalctl','--user','_SYSTEMD_INVOCATION_ID='+invocation,'--no-pager','-o','json']
    p = subprocess.run(cmd, capture_output=True, text=True, check=True)
    rows = [json.loads(line) for line in p.stdout.splitlines()]
    for row in rows:
        if row.get('_SYSTEMD_USER_UNIT') != unit:
            raise ValueError('journal target mismatch')
    result = {'command': cmd, 'unit': unit, 'invocation_id': invocation, 'records': rows, 'native_success_inferred': False}
    (ROOT/'continuation/launch-journal.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Captured invocation-bound W45 records:',len(rows))

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print('REFUSED: '+str(error),file=sys.stderr)
        sys.exit(1)
