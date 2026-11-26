# OG-AmpJack

Use a wired **Xbox One / Series controller** on an **original Xbox** through a passive Xbox-to-USB cable. OG-AmpJack is an XBMC trainer for **Halo 2 (TU1.5 / u803)** that adds full input and rumble for the modern pad while an original controller keeps working alongside it.

**Download:** [`OG-AmpJack-v0.1.0-preview.1.zip`](ogxbox/halo2-release/dist/OG-AmpJack-v0.1.0-preview.1.zip) · [Install guide](docs/OG-INSTALL.md) · [Compatibility](docs/OG-COMPATIBILITY.md)

## What works

- Modern pad on **port 2**: sticks, buttons, triggers and rumble. This exact release was tested on real hardware.
- Original controller on port 1 keeps working normally.
- Nothing is flashed or patched on disk: XBMC loads the trainer when you launch Halo 2 and the game files stay untouched.

## Known limits

- **Halo 2 u803 only.** Other games, dashboards and the HD-patched Halo 2 executable are not supported.
- If the pad is already plugged in but dark, pressing the Xbox button may only make it blink — unplug and replug it.
- Headset audio and chat are not implemented yet (research in progress).
- BIOS in-game-reset (IGR) combos from the modern pad are unverified.

## Quick install

1. Copy `OG-AmpJack.xbtf` and `OG-AmpJack.bin` from the ZIP into `E:\Trainers\` over FTP.
2. In XBMC: Programs → Halo 2 → **Update trainer list** → Trainer settings → select **OG-AmpJack** → tick **Enable controller support** → OK.
3. Plug the modern pad into port 2 and launch Halo 2 from XBMC.

Full steps and rollback: [docs/OG-INSTALL.md](docs/OG-INSTALL.md).

## Development

- [Build and tests](docs/OG-BUILD.md)
- [Source map](OG-AMPJACK.md)
- [Changelog](CHANGELOG.md)

## Relationship to AmpJack360

This is the original-Xbox project. The [public AmpJack repository](https://github.com/Roasted-Codes/AmpJack) is the separate Xbox 360 version; its `xw.xex` and DashLaunch instructions do not apply here. This repository began as a snapshot of that codebase, so inherited 360 code, docs and research remain for provenance. Licenses and attribution are preserved: see [LICENSE](LICENSE), [NOTICE](NOTICE) and the package notices. No game files, BIOS or SDK material are included; bring your own stock Halo 2.
