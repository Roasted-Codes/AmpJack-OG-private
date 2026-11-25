# ogxbox/halo2/ — promoted title-side sources (worker 03 verified data, fixed)

This folder now holds the SOURCE the presentation runtime depends on, promoted from
worker 03's scratch (`ogxbox/work/03-halo/` — read-only evidence):

- `og_hook_sites.h` — the six verified hook sites (VA / orig5 / displaced span /
  resume / argc), now with a PC-relative flag and pcrel_target for XInputClose.
  Re-asserted byte-for-byte by `ogxbox/integration/detour_plan.py`.
- `xinput_model.h/.c` — the verified classic-Xbox XINPUT structures and error
  codes (gamepad 18 B, state 22 B, caps 25 B). `ogx_fill_gamepad_caps()` now
  zero-fills every field (Rumble = 0: no motors this milestone). The redundant
  `ampjack_input_snapshot_t` mapping is DROPPED — the finalized `og_gip` adapter
  (`ogxbox/gip/og_gamepad.h`) is the single button/mapping authority.
  Also defines the VERIFIED `XINPUT_FEEDBACK` ABI (OXDK xbox.h, packed): header
  (dwStatus + hEvent + 58-byte reserved) + Rumble at offset 66, 70 B total —
  XInputSetState takes this, NOT a bare 4-byte vibration pointer.
- `xinput_model.c` — caps fill only.

NOT promoted (superseded): `input_model.c`'s snapshot mapping (redundant with
og_gamepad.h) and `hook_payload.S` (absolute self-symbol loads, unsafe) — replaced
by `ogxbox/integration/{ogx_stub.c,trampoline.S}` (PIC, only R_386_RELATIVE).

The runtime presentation, trampolines, tests and build live in
`ogxbox/integration/` (see its README). The original worker 03 REPORT.md and
PARENT-REVIEW.md remain here for provenance.
