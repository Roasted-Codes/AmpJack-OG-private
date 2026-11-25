import pathlib,json,hashlib
O=pathlib.Path(__file__).resolve().parent
inputs=json.loads((O/'PARENT-PROTECTED-INPUTS.json').read_text())
r={p:{'expected':h,'actual':hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()} for p,h in inputs.items()}
(O/'initial-authentication.json').write_text(json.dumps(r,indent=2)+'\n')
assert all(v['actual']==v['expected'] for v in r.values()), 'protected preimage drift'
print('all protected preimages match')
