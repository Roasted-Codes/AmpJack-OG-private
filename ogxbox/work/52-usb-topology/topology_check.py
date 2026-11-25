"""Standalone offline USB topology checker. No runtime imports or I/O effects in API.

Identity receipts are caller-supplied provenance assertions, not cryptographic proof
of when QMP ran. Hashes prevent accidental mixing, not a dishonest receipt issuer.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def digest(data):
    return hashlib.sha256(data).hexdigest()


def text_hash(text):
    return digest(text.encode())


def listing(text):
    rows = []
    pattern = r'\s*Device (\d+)\.(\d+), Port ([\d.]+), Speed ([\d.?]+) Mb/s, Product (.*?)(?:, ID: (.*))?'
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        match = re.fullmatch(pattern, raw)
        if not match:
            raise ValueError('unparsed listing row ' + str(number))
        bus, address, port, speed, product, node_id = match.groups()
        rows.append(dict(busnr=int(bus), address=int(address), port=port,
                         speed=speed, product=product, node_id=node_id,
                         line=number, raw=raw))
    return rows


def tree_nodes(text):
    stack, nodes = [], []
    for number, raw in enumerate(text.splitlines(), 1):
        indent = len(raw) - len(raw.lstrip())
        value = raw.strip()
        if not value:
            continue
        while stack and stack[-1]['indent'] >= indent:
            stack.pop()
        parent = stack[-1] if stack else None
        match = re.fullmatch(r'dev: (.*?), id "(.*)"', value)
        if match or value.startswith('bus: '):
            node = dict(kind='dev' if match else 'bus',
                        name=match[1] if match else value[5:],
                        node_id=match[2] if match else None,
                        parent=parent, indent=indent, line=number, props={}, summary=None)
            nodes.append(node)
            stack.append(node)
        elif parent:
            prop = re.fullmatch(r'([\w-]+) = (.*)', value)
            if prop:
                key, val = prop.groups()
                if key in parent['props']:
                    raise ValueError('duplicate qtree property ' + key)
                parent['props'][key] = val
            summary = re.fullmatch(r'addr (\d+)\.(\d+), port ([\d.]+), speed ([\d.?]+), name (.*?)(, attached)?', value)
            if summary:
                if parent['summary']:
                    raise ValueError('duplicate qtree summary')
                b, a, p, speed, product, attached = summary.groups()
                parent['summary'] = dict(busnr=int(b), address=int(a), port=p,
                                         speed=speed, product=product, attached=bool(attached),
                                         line=number, raw=raw)
    identifiers = [n['node_id'] for n in nodes if n['kind'] == 'dev' and n['node_id']]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('duplicate qtree device identifier')
    result = []
    for node in nodes:
        parent = node['parent']
        if node['kind'] != 'dev' or not parent or parent['kind'] != 'bus' or not parent['name'].startswith('usb-bus.'):
            continue
        ancestry, ancestor = [], parent
        controller = None
        while ancestor:
            ancestry.append(ancestor['name'])
            if ancestor['kind'] == 'dev' and ancestor['name'] == 'pci-ohci':
                cls = ancestor['props'].get('addr', '')
                controller = '00:' + cls  # this schema supports the saved pci.0 OHCI only
            ancestor = ancestor['parent']
        result.append(dict(node_id=node['node_id'], driver=node['name'],
                           bus=parent['name'], controller=controller,
                           ancestry=list(reversed(ancestry)), line=node['line'],
                           props=node['props'], summary=node['summary']))
    return result


def integer_property(node, key):
    value = node['props'].get(key)
    return int(value.split()[0], 0) if value is not None else None


def check(capture, selector, identity, capture_bytes=None):
    """Return independent verdicts; errors always leave qualification false.

    selector: capture_id, controller (00:02.0), bus, busnr, port, node_id,
    driver and optional hostbus/hostaddr/vendorid/productid.
    identity: capture_id, boot_id, pid, start_ticks, invocation_id,
    capture_sha256, listing_sha256, qtree_sha256. Optional host_open receipt
    must be from the same sample and explicitly target-bound.
    """
    result: dict[str, Any] = dict(join='invalid', target_row=None, target_node=None,
                  speed_label=dict(verdict='unknown', reason='join not established'),
                  host_open=dict(verdict='unknown', reason='no independent handle observation'),
                  logical_port=dict(verdict='unknown', reason='no guest routing observation'),
                  qualifies_full_speed_host_open=False, working_game_pad=False,
                  reasons=[])
    try:
        for key in ('capture_id', 'controller', 'bus', 'busnr', 'port', 'node_id', 'driver'):
            if key not in selector or selector[key] in ('', None):
                raise ValueError('missing selector ' + key)
        for key in ('capture_id', 'boot_id', 'pid', 'start_ticks', 'invocation_id',
                    'capture_sha256', 'listing_sha256', 'qtree_sha256'):
            if not identity.get(key):
                raise ValueError('missing capture identity ' + key)
        if identity['capture_id'] != selector['capture_id']:
            raise ValueError('stale capture identity')
        if capture_bytes is None:
            raise ValueError('original capture bytes required for hash binding')
        if identity['capture_sha256'] != digest(capture_bytes):
            raise ValueError('capture hash mismatch')
        if json.loads(capture_bytes) != capture:
            raise ValueError('capture bytes/content mismatch')
        for key, field in (('listing_sha256', 'after'), ('qtree_sha256', 'qtree')):
            if identity[key] != text_hash(capture[field]):
                raise ValueError(field + ' hash mismatch')
        rows = listing(capture['after'])
        before = listing(capture['before'])
        nodes = tree_nodes(capture['qtree'])
        selected = [n for n in nodes if n['node_id'] == selector['node_id']]
        if len(selected) != 1:
            raise ValueError('missing/ambiguous qtree node identity')
        node = selected[0]
        if 'pci.0' not in node['ancestry']:
            raise ValueError('unsupported controller ancestry')
        summary = node['summary']
        if not summary:
            raise ValueError('missing qtree address/speed summary')
        for key in ('controller', 'bus', 'driver'):
            if node[key] != selector[key]:
                raise ValueError('qtree selector mismatch: ' + key)
        if node['props'].get('port') != json.dumps(selector['port']):
            raise ValueError('qtree full port property mismatch')
        for key in ('busnr', 'port'):
            if summary[key] != selector[key]:
                raise ValueError('qtree summary mismatch: ' + key)
        if len([n for n in nodes if n['bus'] == node['bus'] and n['props'].get('port') == node['props'].get('port')]) != 1:
            raise ValueError('colliding qtree full path')
        by_id = [r for r in rows if r['node_id'] == selector['node_id']]
        by_path = [r for r in rows if (r['busnr'], r['port']) == (selector['busnr'], selector['port'])]
        if len(by_id) != 1 or len(by_path) != 1 or by_id[0] != by_path[0]:
            raise ValueError('missing/ambiguous listing identity or full path')
        row = by_id[0]
        for key in ('busnr', 'address', 'port', 'speed', 'product'):
            if row[key] != summary[key]:
                raise ValueError('listing/qtree mismatch: ' + key)
        if any(r['node_id'] == selector['node_id'] or
               (r['busnr'], r['port']) == (selector['busnr'], selector['port']) for r in before):
            raise ValueError('stale target: already present before device_add interval')
        # Check every intermediary, not an address number or last path component.
        components = selector['port'].split('.')
        for depth in range(1, len(components)):
            port = '.'.join(components[:depth])
            hubs = [n for n in nodes if n['bus'] == node['bus'] and
                    n['props'].get('port') == json.dumps(port)]
            if len(hubs) != 1 or hubs[0]['driver'] != 'usb-hub' or not hubs[0]['summary'] or not hubs[0]['summary']['attached']:
                raise ValueError('missing/ambiguous/unattached intermediary ' + port)
            hubrow = [r for r in rows if r['busnr'] == selector['busnr'] and r['port'] == port]
            if len(hubrow) != 1 or any(hubrow[0][k] != hubs[0]['summary'][k] for k in ('busnr','address','port','speed','product')):
                raise ValueError('intermediary listing/qtree mismatch ' + port)
        for key in ('hostbus', 'hostaddr', 'vendorid', 'productid'):
            actual = integer_property(node, key)
            if key in selector and actual != selector[key]:
                raise ValueError('host selector mismatch: ' + key)
        for field, key in (('bus', 'hostbus'), ('address', 'hostaddr')):
            if field in capture and integer_property(node, key) != capture[field]:
                raise ValueError('saved host metadata mismatch: ' + field)
        result.update(join='unique', target_row=row, target_node=node)
        result['speed_label'] = dict(verdict='confirmed', mbps=row['speed'],
                                     full_speed=row['speed'] == '12',
                                     reason='exact target listing and qtree USBDevice.speed agree; not a wire negotiation measurement')
        opening = identity.get('host_open')
        if opening:
            bound = all(opening.get(k) == selector[k] for k in
                        ('capture_id','controller','bus','busnr','port','node_id'))
            bound = bound and all(opening.get(k) == identity[k] for k in
                                  ('boot_id','pid','start_ticks','invocation_id'))
            bound = bound and opening.get('capture_sha256') == identity['capture_sha256']
            bound = bound and all(opening.get(k) == integer_property(node,k) for k in
                                  ('hostbus','hostaddr','vendorid','productid'))
            if not bound or opening.get('method') != 'same-sample-handle-snapshot' or not opening.get('source'):
                result['host_open']['reason'] = 'stale/unbound/unsupported handle evidence'
            elif opening.get('handle_nonnull') is True and summary['attached']:
                result['host_open'] = dict(verdict='confirmed', reason='caller-provided same-sample independent handle snapshot and attached node', source=opening['source'])
            elif opening.get('handle_nonnull') is False:
                result['host_open'] = dict(verdict='not-open', reason='caller-provided same-sample null handle snapshot', source=opening['source'])
        mapped = {'3': 1, '4': 2, '1': 3, '2': 4}
        if len(components) >= 2 and components[0] == '1':
            result['logical_port'] = dict(verdict='configured-only',
                configured_xbox_connector=mapped.get(components[1]),
                reason='inverse xemu port_map {3,4,1,2}; direct usb-host bypasses XID index binding; observed Xbox/game routing unknown')
        result['qualifies_full_speed_host_open'] = row['speed'] == '12' and result['host_open']['verdict'] == 'confirmed'
        result['reasons'] = ['working_game_pad remains false: no guest input/routing evidence is accepted by this checker']
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        result['reasons'].append(str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--selector', type=Path, required=True)
    parser.add_argument('--identity', type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = args.capture.read_bytes()
        result = check(json.loads(raw), json.loads(args.selector.read_text()),
                       json.loads(args.identity.read_text()), raw)
    except (OSError, ValueError) as error:
        result = dict(join='invalid', qualifies_full_speed_host_open=False, working_game_pad=False, reasons=[str(error)])
    print(json.dumps(result, indent=2))
    return 0 if result['qualifies_full_speed_host_open'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
