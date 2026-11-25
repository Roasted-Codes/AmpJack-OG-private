# OG-AmpJack source map

## One selected baseline

The user's live Halo 2 session was identified by read-only hook and code-section comparison as **AmpJack63-u803-3ddc05b8** (W63 combined module), with logging OFF. Input and vibration are owner-reported working. The earlier assumption that the preferred session was W65 RUMBLE-ONLY was incorrect.

| Path | Purpose |
|---|---|
| [`ogxbox/work/63-wake-rumble/src/`](ogxbox/work/63-wake-rumble/src/) | Exact controller source lineage selected by live readback. |
| [`ogxbox/halo2-release/`](ogxbox/halo2-release/) | Portable packaging of that pinned module; normal installation names, tests and matched preview files. |
| [`ogxbox/integration/`](ogxbox/integration/), [`gipdriver/`](ogxbox/gipdriver/), [`gip/`](ogxbox/gip/), [`halo2/`](ogxbox/halo2/) | Earlier base implementation and protocol/model work. |
| `ogxbox/work/32-*`, `43-*`, `65-bisect/` | Historical lineage and experiments; not parallel maintained releases. |
| `core/`, `tools/trainerfmt.py` | Shared protocol/format code; keep dependencies and notices. |
| `xbox360/` and inherited non-OG docs | Historical AmpJack360 snapshot, not OG install instructions. |

The historical root `SOURCE-MANIFEST.json` describes the initial source upload; new release manifests describe the promoted artifacts. No old Git history is rewritten.

## Selected module identity

- ELF: `3ddc05b8c0c01a388ad9ab156660c8018a8a3d0fe4cc676af7548a5405ec7fab`
- Payload: `8bf54869e1635fbcb8313226da7abd243c0b4fc4729b1b664f2828e030380448`
- Original trainer: `3685f5680425fb72ec48acfd6c347e0f5d76c320352ee1d02d1ff76e5b6ed23d`
- Live code-section SHA-256: `3538c20e7fe0382bb450e1c6af113a193c8a2cb08118a7e44a2991c80a0f52a9`
- Selected resident/file-buffer allocations: 45056 / 24576 bytes. Keeping them unchanged does not establish retail 64 MiB memory headroom.

The release wrapper changes filenames/display and forces the same logging-OFF mode. It must not change controller code, rumble, wake logic, kernel code or BIOS. Its source/module/wrapper hashes are linked in the release manifest. A renamed wrapper is not automatically hardware-tested.

See [compatibility](docs/OG-COMPATIBILITY.md) for the unresolved wake/IGR/launch questions and [build notes](docs/OG-BUILD.md) for the distinction between portable packaging and a full source rebuild.
