"""Bounded same-owner USB add receipt. No device/protocol access on import.

Directory identity bounds the command interval, not future connectivity. The
pinned direct-address realization implies open-at-add; no handle is sampled.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time
import uuid
from typing import Any

CHECKER = Path(__file__).resolve().parents[2] / '52-usb-topology/topology_check.py'
CHECKER_SHA = 'd6cebc1da3cd380bd7da42da720cea5c0780a0a5df4b5e52815c2643b54a494f'

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def need(ok, reason):
    if not ok: raise RuntimeError('USB qualification: ' + reason)

def parser():
    need(hashlib.sha256(CHECKER.read_bytes()).hexdigest() == CHECKER_SHA, 'structural checker drift')
    spec = importlib.util.spec_from_file_location('usb57_structural52', CHECKER)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class PhysicalInstance:
    """Held read-only directory FD; attributes are read relative to that FD."""
    def __init__(self, pre):
        self.pre = pre
        self.path = Path(pre['sysfs'])
        self.resolved = self.path.resolve(strict=True)
        self.fd = os.open(self.resolved, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        self.identity = self.stat(os.fstat(self.fd))
        self.initial = None
    @staticmethod
    def stat(st): return dict(device=st.st_dev, inode=st.st_ino)
    def close(self): os.close(self.fd)
    def sample(self):
        need(self.path.resolve(strict=True) == self.resolved, 'physical symlink/path changed')
        need(self.stat(self.path.stat()) == self.identity == self.stat(os.fstat(self.fd)), 'physical device instance changed')
        raw = {}
        for key in ('idVendor', 'idProduct', 'busnum', 'devnum', 'speed'):
            fd = os.open(key, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.fd)
            with os.fdopen(fd, 'r') as stream: raw[key] = stream.read(128)
        need(self.path.resolve(strict=True) == self.resolved and self.stat(self.path.stat()) == self.identity,
             'physical instance changed during attribute read')
        values = {k:v.strip() for k,v in raw.items()}
        need(values['idVendor'] == '045e' and values['idProduct'] == '0b12', 'physical VID/PID changed')
        bus, address = int(values['busnum']), int(values['devnum'])
        need(0 < bus <= 255 and 0 < address <= 127, 'invalid physical bus/address')
        need(bus == int(self.pre['busnum']) and address == int(self.pre['devnum']), 'preflight bus/address mismatch')
        need(self.pre['node'] == f'/dev/bus/usb/{bus:03d}/{address:03d}', 'preflight device node mismatch')
        need(values['speed'] == self.pre['speed'], 'preflight speed mismatch')
        sample = dict(raw=raw, values=values, resolved=str(self.resolved), directory_identity=self.identity,
                      bus=bus, address=address)
        if self.initial is None: self.initial = sample
        need(sample == self.initial, 'physical attributes/instance changed during interval')
        return sample

def direct_arguments(bus, address):
    return dict(driver='usb-host', id='pt_pad3', bus='usb-bus.1', port='1.4', hostbus=bus, hostaddr=address)

def collision(check, before, tree):
    need(not any(r['node_id'] == 'pt_pad3' or (r['busnr'], r['port']) == (1, '1.4')
                 for r in check.listing(before)), 'preexisting listing target/path')
    need(not any(n['node_id'] == 'pt_pad3' or (n['bus'] == 'usb-bus.1' and
                 (n['props'].get('port') == '"1.4"' or
                  n['summary'] and n['summary']['port'] == '1.4'))
                 for n in check.tree_nodes(tree)), 'preexisting tree target/path')

STAGES = ['native_before', 'entry_before', 'physical_before', 'before', 'pre_qtree',
          'physical_pre_add', 'request', 'physical_post_add', 'after', 'qtree',
          'physical_post_sample', 'native_after', 'entry_after']

def validate(receipt):
    """Recheck complete receipt binding/order and return independent verdicts."""
    result: dict[str, Any] = dict(qualified=False, request='unknown', node='unknown', open_at_add='unknown',
                  attached_at_sample='unknown', host_reported_speed='unknown', emulated_speed='unknown',
                  game_input='untested', future_health='unknown', reasons=[])
    try:
        body = {k:v for k,v in receipt.items() if k not in ('binding_sha256', 'verdict')}
        need(receipt.get('binding_sha256') == digest(body), 'receipt hash mismatch')
        identity = receipt['identity']
        need(all(identity.get(k) for k in ('boot_id','pid','start_ticks','invocation_id')), 'missing invocation/native identity')
        events = receipt['events']
        need([x['stage'] for x in events] == STAGES, 'missing/stale/out-of-order observations')
        end = end_wall = -1
        for seq,event in enumerate(events,1):
            need(event['seq'] == seq and event['capture_id'] == receipt['capture_id'] and event['identity'] == identity,
                 'stale session/event binding')
            need(end <= event['start_monotonic_ns'] <= event['end_monotonic_ns'], 'invalid monotonic order')
            need(end_wall <= event['start_wall_ns'] <= event['end_wall_ns'], 'invalid wall order')
            need(event['sha256'] == digest(event['value']), 'observation hash mismatch')
            end = event['end_monotonic_ns']
            end_wall = event['end_wall_ns']
        values = {x['stage']:x['value'] for x in events}
        for field in ('before', 'pre_qtree', 'after', 'qtree'):
            need(receipt[field] == values[field], 'raw/event mismatch: '+field)
        for stage in ('native_before','native_after'):
            need(all(values[stage].get(k) == identity[k] for k in ('boot_id','pid','start_ticks')), 'native bracket mismatch')
        physical = values['physical_before']
        need(physical['values']['idVendor'] == '045e' and physical['values']['idProduct'] == '0b12',
             'physical VID/PID evidence mismatch')
        need(int(physical['values']['busnum']) == physical['bus'] and
             int(physical['values']['devnum']) == physical['address'], 'physical tuple evidence mismatch')
        for stage in ('physical_pre_add','physical_post_add','physical_post_sample'):
            need(values[stage] == physical, 'physical bracket mismatch')
        bus,address = physical['bus'],physical['address']
        need(receipt['bus'] == bus and receipt['address'] == address, 'saved physical tuple mismatch')
        need(receipt['sysfs'] == receipt['preflight']['sysfs'], 'saved preflight path mismatch')
        need(int(receipt['preflight']['busnum']) == bus and int(receipt['preflight']['devnum']) == address,
             'saved preflight tuple mismatch')
        request = values['request']
        need(request['arguments'] == direct_arguments(bus,address), 'not synchronous direct-address branch')
        result['request'] = 'direct-address'
        need(type(request['result']) is dict and request['result'] == {}, 'missing/malformed direct client result')
        result['open_at_add'] = 'source-implied synchronous open; not sampled handle'
        check = parser()
        collision(check, values['before'], values['pre_qtree'])
        capture = dict(before=values['before'], after=values['after'], qtree=values['qtree'],bus=bus,address=address)
        raw = json.dumps(capture).encode()
        selector = dict(capture_id=receipt['capture_id'],controller='00:02.0',bus='usb-bus.1',busnr=1,
                        port='1.4',node_id='pt_pad3',driver='usb-host',hostbus=bus,hostaddr=address)
        binding = dict(identity,capture_id=receipt['capture_id'],capture_sha256=check.digest(raw),
                       listing_sha256=check.text_hash(capture['after']),qtree_sha256=check.text_hash(capture['qtree']))
        joined = check.check(capture,selector,binding,raw)
        result['structural'] = joined
        need(joined['join'] == 'unique', '; '.join(joined['reasons']))
        node,row = joined['target_node'],joined['target_row']
        result['node'] = 'unique joined target'
        result['attached_at_sample'] = node['summary']['attached']
        result['host_reported_speed'] = physical['values']['speed']
        result['emulated_speed'] = row['speed']
        for key in ('vendorid','productid'):
            need(check.integer_property(node,key) == 0, 'unexpected/missing filter default '+key)
        for key in ('hostport','hostdevice'):
            need(node['props'].get(key) in (None, '""', '"<null>"', '<null>'), 'unexpected filter '+key)
        need(node['summary']['attached'], 'target not attached at sample')
        need(physical['values']['speed'] == '12', 'host-reported speed not full/unknown')
        need(row['speed'] == '12', 'emulated target speed not full/unknown')
        need('failed_stage' not in receipt, 'failed receipt')
        result['qualified'] = True
    except (RuntimeError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        result['reasons'].append(str(error))
    return result

def qualify(q, pads, ident, handle, native, entry, save):
    receipt: dict[str, Any] = dict(capture_id=uuid.uuid4().hex, identity={k:ident.get(k) for k in ('boot_id','pid','start_ticks')},
                   events=[], game_input='untested', future_health='unknown')
    receipt['identity']['invocation_id'] = handle.get('invocation_id') if handle else None
    held = None
    stage = 'identity'
    def observe(name, action):
        nonlocal stage
        stage = name
        start_wall,start_mono = time.time_ns(),time.monotonic_ns()
        try:
            value = action()
        except BaseException as error:
            receipt['failed_observation'] = dict(stage=name,start_wall_ns=start_wall,
                start_monotonic_ns=start_mono,end_wall_ns=time.time_ns(),end_monotonic_ns=time.monotonic_ns(),
                exception=dict(type=type(error).__name__,message=str(error)))
            raise
        event = dict(seq=len(receipt['events'])+1,stage=name,capture_id=receipt['capture_id'],identity=dict(receipt['identity']),
                     start_wall_ns=start_wall,start_monotonic_ns=start_mono,end_wall_ns=time.time_ns(),
                     end_monotonic_ns=time.monotonic_ns(),value=value,sha256=digest(value))
        receipt['events'].append(event)
        return value
    try:
        need(all(receipt['identity'].values()), 'authenticated invocation/native identity unavailable')
        check = parser()
        observe('native_before',native);observe('entry_before',entry)
        stage = 'physical_open'
        need(len(pads) == 1, 'preflight pad missing/ambiguous')
        receipt['preflight'] = dict(pads[0])
        receipt['identity_boundary'] = 'held directory from physical_before through physical_post_sample; preflight supplies path/tuple, not a historical inode or serial guarantee'
        held = PhysicalInstance(pads[0])
        physical = observe('physical_before',held.sample)
        receipt.update(bus=physical['bus'],address=physical['address'],sysfs=pads[0]['sysfs'])
        receipt['before'] = observe('before',lambda:q.hmp('info usb'))
        receipt['pre_qtree'] = observe('pre_qtree',lambda:q.hmp('info qtree'))
        stage = 'collision'
        collision(check,receipt['before'],receipt['pre_qtree'])
        observe('physical_pre_add',held.sample)
        args = direct_arguments(physical['bus'],physical['address'])
        receipt['request_arguments'] = args
        observe('request',lambda:dict(arguments=args,result=q.cmd('device_add',**args)))
        observe('physical_post_add',held.sample)
        receipt['after'] = observe('after',lambda:q.hmp('info usb'))
        receipt['qtree'] = observe('qtree',lambda:q.hmp('info qtree'))
        observe('physical_post_sample',held.sample)
        observe('native_after',native);observe('entry_after',entry)
        stage = 'validation'
        receipt['binding_sha256'] = digest(receipt)
        result = validate(receipt)
        need(result['qualified'], '; '.join(result['reasons']))
        return result
    except BaseException as error:
        receipt.update(failed_stage=stage,exception=dict(type=type(error).__name__,message=str(error)))
        raise
    finally:
        if held is not None: held.close()
        receipt.pop('binding_sha256',None)
        receipt['binding_sha256'] = digest(receipt)
        save(dict(receipt, verdict=validate(receipt)))
