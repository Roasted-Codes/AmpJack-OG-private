from pathlib import Path
import hashlib,json
O=Path(__file__).resolve().parent
R=O.parent/'45-x11-runtime-capture'
pins=json.loads((O/'PARENT-PROTECTED-INPUTS.json').read_text())
drift={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p,h in pins.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h}
print(json.dumps(drift,indent=2))
assert not drift, 'unexplained pre-edit drift'
(O/'baseline-parent_launch.py').open('xb').write((R/'parent_launch.py').read_bytes())
(O/'REPORT.md').write_text('INCOMPLETE: offline slot59 preparation. Protected preimages verified. No native commands, live grant, device proof or parent confirmation.\n')
(O/'status.json').write_text(json.dumps(dict(state='incomplete',native_commands=0,protected_preimages_match=True)))
(O/'shortsummary.txt').write_text('INCOMPLETE offline preparation; no live authority.\n')
