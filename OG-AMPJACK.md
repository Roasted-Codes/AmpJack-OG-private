# OG-AmpJack source map

## The shipped build

The released trainer is the **AmpJack65 rumble-only module** (internal name W65R), the build the owner runs and has verified on hardware for input and rumble. Packaging only renames the wrapper to `OG-AmpJack.{xbtf,bin}` and sets the display title; the controller module bytes are unchanged.

| Path | Purpose |
|---|---|
| [`ogxbox/work/65-bisect/rumble/src/`](ogxbox/work/65-bisect/rumble/src/) | Exact controller source lineage of the shipped module. |
| [`ogxbox/halo2-release/`](ogxbox/halo2-release/) | Portable packaging: pinned module, wrapper build, tests and the released `dist/` files. |
| [`ogxbox/integration/`](ogxbox/integration/), [`gipdriver/`](ogxbox/gipdriver/), [`gip/`](ogxbox/gip/), [`halo2/`](ogxbox/halo2/) | Base implementation: GIP (modern pad) driver, Halo 2 hook sites and the XInput presentation model. |
| `ogxbox/work/*` | Development history (research, experiments, earlier trainer candidates). Not maintained releases. |
| `core/`, `tools/trainerfmt.py` | Shared protocol/format code and the XBMC trainer file format. |
| `xbox360/` and inherited non-OG docs | Historical AmpJack360 snapshot, not OG install instructions. |

## Shipped module identity

- Module ELF: `5850fc63b387eca58f1dcccae3a390341b66f999bd04d75ee12ddb18135d362b`
- Payload `OG-AmpJack.bin`: `5e63fb1afb9c26d15af8165471e2a982171db1f1e9a2fc6c4d6114bd148ec39c` (byte-identical to the hardware-tested `AmpJack65R-u803-5850fc63.bin`)
- Resident / file-buffer allocations: 36864 / 16384 bytes.

How it works, briefly: the trainer hooks six statically linked XInput functions in Halo 2 (`XGetDeviceChanges`, `XInputOpen/Close/GetCapabilities/GetState/SetState`), presents the modern pad as a virtual original controller on port 2, drives the pad over USB with the GIP protocol (handshake, 4 ms input polling, rumble), and forwards original-controller calls to the game's own code untouched. See [compatibility](docs/OG-COMPATIBILITY.md) and [build notes](docs/OG-BUILD.md).
