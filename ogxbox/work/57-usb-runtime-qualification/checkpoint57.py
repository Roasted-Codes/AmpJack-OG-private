import pathlib,json,hashlib
W=pathlib.Path(__file__).resolve().parent.parent
D=W/'57-usb-runtime-qualification'; R=W/'45-x11-runtime-capture/tools'
pins=json.loads((D/'PARENT-PROTECTED-INPUTS.json').read_text())
result={p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in pins}
assert result==pins,[(p,result[p],h) for p,h in pins.items() if result[p]!=h]
assert not (R/'usb_target57.py').exists() and not (R/'test_usb_target57.py').exists()
(D/'runtime_effects.preimage.py').write_bytes((R/'runtime_effects.py').read_bytes())
(D/'pre-edit-check.json').write_text(json.dumps({'hashes':result,'new_files_absent':True},indent=2))
(D/'REPORT.md').write_text('W57 OFFLINE implementation checkpoint\n\nINCOMPLETE: protected preimages verified; no production edits/tests yet. No live/native/USB/network activity performed. W55 wrapper EXITED1 remains unknown; parent accepted its plan. W56 correction accepted, not reinvestigated. Four commands spent; zero remaining. Physical/game health untested.\n')
(D/'status.json').write_text(json.dumps({'state':'incomplete','offline_only':True,'preimages_verified':True,'physical_input':'untested','native_commands_remaining':0},indent=2))
print('Protected hashes verified; incomplete report/status saved.')
