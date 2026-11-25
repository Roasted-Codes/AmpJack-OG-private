"""Source-only lane56 receipts; no runtime/native control or shared suites."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

O = Path(__file__).resolve().parent
ROOT = O.parents[2]
TOOLS = O.parent / '45-x11-runtime-capture/tools'
TEST = TOOLS / 'test_watch_writer51.py'
PINS = json.loads((O / 'PARENT-PROTECTED-INPUTS.json').read_text())

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run(argv, label, env):
    result = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True)
    (O / (label + '.log')).write_text(result.stdout + result.stderr)
    receipt = dict(argv=argv, exit=result.returncode, cwd=str(ROOT),
                   stdout=result.stdout, stderr=result.stderr,
                   environment={k: env[k] for k in ('PYTHONDONTWRITEBYTECODE', 'PYTHONPYCACHEPREFIX', 'TMPDIR')})
    (O / (label + '.json')).write_text(json.dumps(receipt, indent=2) + '\n')
    print(label, 'exit', result.returncode)
    print(result.stdout + result.stderr)
    return result

mode = sys.argv[1]
env = os.environ.copy()
env['PYTHONDONTWRITEBYTECODE'] = '1'
env['PYTHONPYCACHEPREFIX'] = tempfile.mkdtemp(prefix=mode + '-pycache-', dir=O)
env['TMPDIR'] = str(O)
env['PYTHONPATH'] = str(TOOLS)
if mode == 'baseline':
    assert all(digest(p) == h for p, h in PINS.items())
    original = TEST.read_text()
    (O / 'original-test_watch_writer51.py.txt').write_text(original)
    output = Path(tempfile.mkdtemp(prefix='baseline-output-', dir=O))
    needle = "O=e.WORK/'51-watch-writer-decoder'"
    assert original.count(needle) == 1
    isolated = original.replace(needle, 'O=Path(' + repr(str(output)) + ')')
    baseline = O / 'baseline-isolated.py'
    baseline.write_text(isolated)
    result = run([sys.executable, '-B', str(baseline)], 'baseline-equality-red', env)
    assert result.returncode == 1
    assert 'self.assertEqual(row,expected)' in result.stderr
    assert 'FAILED (failures=1)' in result.stderr
    assert 'Ran 3 tests' in result.stderr
    assert 'ImportError' not in result.stderr
    (O / 'baseline-isolation.json').write_text(json.dumps(dict(original_sha=digest(TEST), isolated_sha=digest(baseline), only_change='O output path', output_dir=str(output)), indent=2) + '\n')
    (O / 'status.json').write_text(json.dumps(dict(status='incomplete', red_preserved=True, normal_runs=[]), indent=2) + '\n')
elif mode == 'final':
    before = {p: digest(p) for p in PINS}
    for p, h in PINS.items():
        if Path(p) != TEST:
            assert before[p] == h
    runs = []
    for index in (1, 2):
        env['PYTHONPYCACHEPREFIX'] = tempfile.mkdtemp(prefix=f'normal-{index}-pycache-', dir=O)
        existing = set(O.glob('run-*'))
        result = run([sys.executable, '-B', str(TEST)], f'normal-{index}', env)
        assert result.returncode == 0
        fresh = set(O.glob('run-*')) - existing
        assert len(fresh) == 1
        output = fresh.pop()
        focused = json.loads((output / 'focused-result.json').read_text())
        negatives = json.loads((output / 'negative-results.json').read_text())
        assert focused['passed'] and focused['tests'] == 3 and len(negatives) == 9
        row = json.loads((output / 'final-seq2-decoded.json').read_text())
        assert row['writer'] is None and row['unclassified'] is True
        replay = json.loads((output / 'real-row-replay.json').read_text())
        assert replay['result']['hold'] and not replay['result']['restore_running']
        runs.append(dict(output_dir=str(output), tests=3, negatives=9, exit=0))
    assert runs[0]['output_dir'] != runs[1]['output_dir']
    after = {p: digest(p) for p in PINS}
    assert before == after
    receipt = dict(status='complete', source_only=True, red_preserved=True, normal_runs=runs,
                   before_hashes=before, after_hashes=after,
                   original_test_sha=PINS[str(TEST)], changed_test_sha=digest(TEST))
    (O / 'status.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
else:
    raise SystemExit('baseline or final required')
