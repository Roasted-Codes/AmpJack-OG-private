#!/usr/bin/env python3
"""analyze_run.py <run-dir> [--pins PINS] - offline classifier for an xbdm_observe run directory.

Reads title-gate.json, samples.jsonl, threads.jsonl, notifications.log, fault/, summary.json, manifest.json,
marks.jsonl and writes <run-dir>/result.json.  Pure offline; never connects anywhere.
Classes: R-H R-F R-A R-T B-H B-F X (see README-RUN.md).
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PINS = os.path.normpath(os.path.join(HERE, '..', 'OPUS-F-PINS.json'))
MIN_SAMPLES = 100
QUIESCENT_WINDOW_NS = 10 * 10**9
LONG_DWELL_MS = 3000.0
ORPHAN_HOLD_MS = 100.0
INPUTS = ('title-gate.json', 'samples.jsonl', 'threads.jsonl', 'notifications.log', 'summary.json',
          'manifest.json', 'marks.jsonl', 'fault/fault.json')


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()


def _load_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _load_jsonl(path):
    out = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    try:
                        out.append(json.loads(ln))
                    except ValueError:
                        pass  # a torn last line if the run died mid-write
    except OSError:
        pass
    return out


def mark_has_on(mark):
    return bool(mark) and re.search(r'(?<![A-Za-z])ON(?![A-Za-z])', mark) is not None


def analyze_samples(samples):
    """samples: list of {'mono_ns': int, 'fields': {...}, 'status': {...}?} sorted by mono_ns."""
    recs = {}
    stuck = False
    long_dwell = False
    stint_val = stint_first = stint_last = None
    prev_retry = None
    decs = 0

    def close_stint():
        nonlocal long_dwell, stuck
        if stint_val is None:
            return
        r = recs[stint_val]
        dwell = (stint_last - stint_first) / 1e6
        r['dwell_ms'] += dwell
        r['max_stint_ms'] = max(r['max_stint_ms'], dwell)
        r['retry_decrements'] = max(r['retry_decrements'], decs)
        if dwell >= LONG_DWELL_MS:
            long_dwell = True
        if decs >= 2:
            stuck = True

    for s in samples:
        f = s.get('fields') or {}
        cur, t = f.get('current'), s['mono_ns']
        if cur is None:
            continue                     # unknown sample: neither extends nor ends a stint
        if cur != stint_val:
            close_stint()
            stint_val, stint_first, decs, prev_retry = (cur, t, 0, None) if cur else (None, None, 0, None)
            if cur:
                r = recs.setdefault(cur, {'first_mono_ns': t, 'last_mono_ns': t, 'dwell_ms': 0.0,
                                          'max_stint_ms': 0.0, 'min_retry': None, 'retry_decrements': 0,
                                          'markers': []})
        if cur:
            stint_last = t
            r = recs[cur]
            r['last_mono_ns'] = t
            rt = f.get('retry')
            if rt is not None:
                if r['min_retry'] is None or rt < r['min_retry']:
                    r['min_retry'] = rt
                if prev_retry is not None and rt < prev_retry:
                    decs += 1
                prev_retry = rt
            mk = f.get('marker')
            if mk is not None and mk not in r['markers']:
                r['markers'].append(mk)
    close_stint()
    for r in recs.values():
        r['dwell_ms'] = round(r['dwell_ms'], 3)
        r['max_stint_ms'] = round(r['max_stint_ms'], 3)

    # orphan timer: current nonzero -> 0 with the same armed timer on both sides, held >= 100 ms
    orphan = False
    orphan_events = []
    known = [s for s in samples if (s.get('fields') or {}).get('current') is not None]
    for i in range(1, len(known)):
        a, b = known[i - 1]['fields'], known[i]['fields']
        if not (a['current'] and b['current'] == 0):
            continue
        if not (a.get('timer_inserted') == 1 and b.get('timer_inserted') == 1
                and a.get('duetime') is not None and a.get('duetime') == b.get('duetime')):
            continue
        t0 = known[i]['mono_ns']
        last = t0
        for s in known[i:]:
            f = s['fields']
            if f['current'] == 0 and f.get('timer_inserted') == 1 and f.get('duetime') == a['duetime']:
                last = s['mono_ns']
            else:
                break
        held = (last - t0) / 1e6
        ev = {'record': '0x%x' % a['current'], 'transition_mono_ns': t0, 'duetime': a['duetime'],
              'held_ms': round(held, 3)}
        orphan_events.append(ev)
        if held >= ORPHAN_HOLD_MS:
            orphan = True

    idle_ti_ns = 0
    for i in range(len(samples) - 1):
        f = samples[i].get('fields') or {}
        if f.get('current') == 0 and f.get('timer_inserted') == 1:
            idle_ti_ns += samples[i + 1]['mono_ns'] - samples[i]['mono_ns']

    quiescent_end = False
    if samples:
        tl = samples[-1]['mono_ns']
        win = [s for s in samples if s['mono_ns'] >= tl - QUIESCENT_WINDOW_NS]
        quiescent_end = all((s.get('fields') or {}).get('current') == 0
                            and (s.get('fields') or {}).get('pending') == 0
                            and (s.get('fields') or {}).get('timer_inserted') == 0 for s in win)
    first_quiet = False
    if samples:
        f0 = samples[0].get('fields') or {}
        first_quiet = f0.get('current') == 0 and f0.get('pending') == 0 and f0.get('timer_inserted') == 0

    att = [(s['mono_ns'], (s.get('status') or {}).get('attached')) for s in samples]
    att = [x for x in att if x[1] is not None]
    hooks = [(s.get('status') or {}).get('installed_hooks') for s in samples]
    hooks = [h for h in hooks if h is not None]
    failed = [(s.get('status') or {}).get('install_failed') for s in samples]
    failed = [h for h in failed if h is not None]
    return {
        'records': {'0x%x' % k: v for k, v in recs.items()},
        'stuck_record': stuck, 'long_dwell': long_dwell, 'orphan_timer': orphan, 'orphan_events': orphan_events,
        'idle_timer_inserted_ms': round(idle_ti_ns / 1e6, 3), 'quiescent_end': quiescent_end,
        'enum_activity_after_gate': len(recs),
        'early_phase_missed': bool(first_quiet and len(recs) == 0),
        'attached_end': att[-1][1] if att else None,
        'attached_first_mono_ns': next((t for t, v in att if v == 1), None),
        'installed_hooks_end': hooks[-1] if hooks else None,
        'install_failed_end': failed[-1] if failed else None,
    }


def classify(gate, summary, manifest, stats, n_samples, fault, expected_hooks):
    reasons = []
    gate = gate or {}
    summary = summary or {}
    ts = gate.get('trainer_state')
    code = summary.get('exit_code')
    if gate.get('status') != 'PASS' or gate.get('identity') != 'MATCH':
        reasons.append('gate status %r identity %r' % (gate.get('status'), gate.get('identity')))
    if ts not in ('ON', 'OFF'):
        reasons.append('trainer_state %r' % ts)
    if code in (2, 5, 6) or code is None:
        reasons.append('exit code %r' % code)
    if summary.get('unreachable_episodes'):
        reasons.append('unreachable episodes: %d' % len(summary['unreachable_episodes']))
    if reasons:
        return 'X', reasons
    mark = (manifest or {}).get('mark')
    if mark_has_on(mark) and ts == 'OFF':
        return 'R-T', ['mark %r says ON but trainer_state OFF' % mark]
    bad = [k for k in ('fault', 'stuck_record', 'orphan_timer') if (fault if k == 'fault' else stats[k])]
    if bad:
        return ('R-F' if ts == 'ON' else 'B-F'), bad
    if n_samples < MIN_SAMPLES:
        return 'X', ['too few samples: %d < %d' % (n_samples, MIN_SAMPLES)]
    if not stats['quiescent_end']:
        return 'X', ['not quiescent at end']
    if ts == 'OFF':
        return 'B-H', ['trainer OFF, healthy']
    if stats['installed_hooks_end'] != expected_hooks or stats['install_failed_end'] != 0:
        return 'X', ['hooks %r failed %r' % (stats['installed_hooks_end'], stats['install_failed_end'])]
    if stats['attached_end'] == 1:
        return 'R-H', ['trainer ON, healthy, attached']
    return 'R-A', ['trainer ON, healthy, attached_end=%r' % stats['attached_end']]


def analyze(rd, pins_path=DEFAULT_PINS):
    pins = _load_json(pins_path, {}) or {}
    expected = (pins.get('trainer') or {}).get('expected_installed_hooks', 191)
    gate = _load_json(os.path.join(rd, 'title-gate.json'))
    summary = _load_json(os.path.join(rd, 'summary.json'))
    manifest = _load_json(os.path.join(rd, 'manifest.json'))
    samples = sorted(_load_jsonl(os.path.join(rd, 'samples.jsonl')), key=lambda s: s['mono_ns'])
    marks = _load_jsonl(os.path.join(rd, 'marks.jsonl'))
    threads = _load_jsonl(os.path.join(rd, 'threads.jsonl'))
    gate_status = (gate or {}).get('trainer_status') or {}
    for s in samples:   # samples without a status read inherit nothing; gate status is the fallback below
        s.setdefault('fields', {})
    stats = analyze_samples(samples)
    if stats['installed_hooks_end'] is None:
        stats['installed_hooks_end'] = gate_status.get('installed_hooks')
        stats['install_failed_end'] = gate_status.get('install_failed')
    if stats['attached_end'] is None and gate_status.get('attached') is not None:
        stats['attached_end'] = gate_status.get('attached')
    fault_json = _load_json(os.path.join(rd, 'fault', 'fault.json'))
    fault = bool((summary or {}).get('exit_code') == 3 and fault_json is not None)
    notif_faults = 0
    try:
        with open(os.path.join(rd, 'notifications.log'), 'r', encoding='utf-8', errors='replace') as f:
            for ln in f:
                parts = ln.rstrip('\n').split('\t', 2)
                if len(parts) == 3 and parts[2].strip().lower().startswith(('exception', 'rip', 'execution stopped')):
                    notif_faults += 1
    except OSError:
        pass
    cls, reasons = classify(gate, summary, manifest, stats, len(samples), fault, expected)
    rel_marks = []
    for m in marks:
        t = m.get('mono_ns')
        after = [s for s in samples if s['mono_ns'] >= t]
        rel_marks.append({'text': m.get('text'), 'mono_ns': t,
                          'records_first_seen_after': sorted(k for k, r in stats['records'].items()
                                                             if r['first_mono_ns'] >= t),
                          'attached_first_after_mark': (stats['attached_first_mono_ns'] is not None
                                                        and stats['attached_first_mono_ns'] >= t),
                          'module_changes_after': None, 'samples_after': len(after)})
    mod_idx = _load_jsonl(os.path.join(rd, 'module-index.jsonl'))
    for rm in rel_marks:
        rm['module_changes_after'] = sum(1 for x in mod_idx if x.get('mono_ns', 0) >= rm['mono_ns'])
    inputs = {}
    for name in INPUTS + ('module-index.jsonl',):
        p = os.path.join(rd, name)
        if os.path.isfile(p):
            inputs[name] = _sha(p)
    result = {
        'class': cls, 'reasons': reasons, 'run_dir': os.path.abspath(rd),
        'trainer_state': (gate or {}).get('trainer_state'), 'identity': (gate or {}).get('identity'),
        'exit_code': (summary or {}).get('exit_code'), 'mark': (manifest or {}).get('mark'),
        'samples': len(samples), 'thread_rows': len(threads), 'fault': fault,
        'fault_pc_class': (fault_json or {}).get('fault_pc_class'), 'fault_notifications': notif_faults,
        'freeze_suspected_flag': (summary or {}).get('exit_code') == 4 or bool((summary or {}).get('freeze_suspected')),
        'marks': rel_marks, 'inputs_sha256': inputs,
        'first_sample_mono_ns': samples[0]['mono_ns'] if samples else None,
        'last_sample_mono_ns': samples[-1]['mono_ns'] if samples else None,
    }
    result.update(stats)
    tmp = os.path.join(rd, 'result.json.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=1, sort_keys=True)
    os.replace(tmp, os.path.join(rd, 'result.json'))
    return result


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    pins = DEFAULT_PINS
    if '--pins' in argv:
        i = argv.index('--pins')
        pins = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    r = analyze(argv[0], pins)
    print('CLASS %s reasons=%s' % (r['class'], '; '.join(r['reasons'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
