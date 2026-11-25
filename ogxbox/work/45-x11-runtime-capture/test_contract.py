#!/usr/bin/env python3
"""W45 no-guest contract tests and freeze actual preflight failure."""
import sys
sys.dont_write_bytecode = True
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from parent_launch import ROOT, DIGEST, GUEST, receipt, environment, command, atomic_claim, authority
sys.path.insert(0,str(ROOT/'tools'))
import enum_watch as e
import live_adapter as a

def main():
    out = ROOT/'evidence'/('contract-'+str(time.time_ns()))
    out.mkdir(parents=True)
    results = []
    lease=receipt();authority(lease)
    for name, changes in (
        ('old-owner',{'owner':'42-enum-observer only'}),
        ('spent',{'boot_launch_commands':1}),
        ('wrong-target',{'fresh_clone':str(ROOT/'wrong-guest')}),
        ('pending',{'status':'PENDING'})):
        data=copy.deepcopy(lease);data.update(changes)
        path=out/(name+'.json');path.write_text(json.dumps(data))
        try:receipt(path)
        except ValueError:results.append({'case':name,'refused':True})
        else:raise AssertionError('altered receipt accepted')
    try:receipt(out/'missing.json')
    except FileNotFoundError:results.append({'case':'missing','refused':True})
    else:raise AssertionError('missing receipt accepted')
    cmd=command(lease,environment(lease))
    assert '--setenv=SDL_VIDEO_DRIVER=x11' in cmd
    assert any(x.startswith('--property=UnsetEnvironment=XAUTHORITY ') for x in cmd)
    assert '--setenv=XAUTHORITY=' not in cmd and '--property=Restart=no' in cmd
    assert cmd[-1]==str(GUEST/'.start-xemu.py')
    results.append({'case':'nonlaunch-command','passed':True,'command':cmd})
    fake=out/'fixture-claim.json'
    atomic_claim(fake,'SYNTHETIC-NOT-PARENT-RECEIPT',{'fixture':True,'launch_commands_used':1})
    try:atomic_claim(fake,'SYNTHETIC-NOT-PARENT-RECEIPT',{'fixture':True})
    except FileExistsError:results.append({'case':'single-use-fixture-claim','refused_second':True})
    else:raise AssertionError('duplicate claim accepted')
    partial=out/'partial-fixture-claim.json';partial.write_bytes(b'')
    try:atomic_claim(partial,'SYNTHETIC',{})
    except FileExistsError:results.append({'case':'interrupted-claim','refused':True})
    else:raise AssertionError('incomplete claim accepted')
    try:a.save('../outside-W45.json',{})
    except e.Refusal:results.append({'case':'output-escape','refused':True})
    else:raise AssertionError('output escape accepted')
    pins=json.loads((ROOT/'evidence/pins.json').read_text())
    assert len(pins['pins'])==46
    tests=json.loads((ROOT/'evidence/test-results.json').read_text())
    assert len(tests['cli_cases'])==13
    pre=json.loads((ROOT/'continuation/preflight.json').read_text())
    expected=e.HASHES['xbe']
    keys=('E:/DEVKIT/Tools/Halo2/default.xbe','E:/TDATA/4d530064/$u/default.xbe')
    mismatches={key:pre['hashes'][key] for key in keys if pre['hashes'][key]['sha256']!=expected}
    assert list(mismatches)==[keys[0]], 'do not silently change measured boundary'
    qualification=dict(runtime_authorized=False,epoch=time.time(),receipt_sha256=DIGEST,first_unsupported_boundary='required guest title artifact identity mismatch',expected_title_sha256=expected,mismatches=mismatches,launch_commands_used=0,source_evidence='continuation/preflight.json',display_fixture_passed=True)
    (ROOT/'qualification.json').write_text(json.dumps(qualification,indent=2)+'\n')
    for args in (['--command'],['--receipt',str(out/'spent.json')],[]):
        p=subprocess.run(['/usr/bin/python3','-B',str(ROOT/'parent_launch.py'),*args],capture_output=True,text=True)
        assert p.returncode==(0 if args==['--command'] else 1),(args,p.stdout,p.stderr)
        results.append({'case':'CLI '+repr(args),'command':p.args,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
    p=subprocess.run(['/usr/bin/python3','-B',str(ROOT/'tools/capture_startup_failure.py')],capture_output=True,text=True)
    assert p.returncode==1 and 'runtime-claim.json' in p.stderr
    results.append({'case':'collector-no-new-invocation','returncode':p.returncode,'stderr':p.stderr})
    assert not (ROOT/'runtime-claim.json').exists()
    assert hashlib.sha256((ROOT/'PARENT-RUNTIME-LEASE.json').read_bytes()).hexdigest()==DIGEST
    result=dict(results=results,cases=len(results),offline_observer_cases=13,pins=46,legacy_red_preserved=True,real_claim_exists=False,real_receipt_unchanged=True,real_commands_used=0,live_evidence=False)
    (ROOT/'contract-tests.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='results'},indent=2))

if __name__=='__main__':
    main()
