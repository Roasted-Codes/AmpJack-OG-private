# OG-AmpJack

Use a wired Xbox One / Series controller on an original Xbox through a passive USB cable. Current support is a title-local XBMC trainer for **stock Halo 2 TU1.5/u803**, not console-wide controller support.

## Current version

The owner likes the running **AmpJack63** build. A read-only XBDM probe of that Halo 2 session matched all seven hook targets and its complete code section to the preserved W63 module. Logging was OFF. The owner reports working controls and vibration, alongside an original controller.

- **Working in the owner's test:** modern-pad input and rumble; original pad alongside it.
- **Still unresolved:** waking a dark, already-connected pad may only blink; unplug/replug is the workaround. IGR compatibility is not established.
- **Historical failure:** this same W63 build previously black-screened at launch with logging on and off. It subsequently ran successfully; the cause and changed condition are unknown. Do not call that failure fixed.
- **Cleanly named preview:** preserves the exact selected controller module with logging forced off. Reproducible packaging and actual-wrapper CPU checks passed; one hardware recheck of the renamed wrapper remains. See [compatibility](docs/OG-COMPATIBILITY.md).

The selected source is [`ogxbox/work/63-wake-rumble/src`](ogxbox/work/63-wake-rumble/src/). Historical experiments remain for provenance, not separate maintained releases.

## Install / download

Private preview package: [`OG-AmpJack-Halo2-v0.1.0-preview.1.zip`](ogxbox/halo2-release/dist/OG-AmpJack-Halo2-v0.1.0-preview.1.zip).

Copy the matching `OG-AmpJack-Halo2.xbtf` and `OG-AmpJack-Halo2.bin` into `E:\Trainers\` over FTP. Refresh XBMC's trainer list, select **OG-AmpJack - Halo 2**, enable **Enable controller support**, and launch the stock game through XBMC. Keep your existing working pair until the renamed package passes a console check. [Full installation and rollback](docs/OG-INSTALL.md).

No game, BIOS, SDK, or console credentials are included. Use your own stock u803 executable; a folder called “Halo 2 HD” is not evidence of a compatible executable.

## Development

- [Build and tests](docs/OG-BUILD.md)
- [Compatibility and known limitations](docs/OG-COMPATIBILITY.md)
- [Source map](OG-AMPJACK.md)
- [Changelog](CHANGELOG.md)

## Separate from AmpJack360

This private repository is the OG Xbox project. The [public AmpJack repository](https://github.com/Roasted-Codes/AmpJack) is the separate Xbox 360 project. Do not install `xw.xex` or follow DashLaunch/360 instructions for OG-AmpJack. Headset/MixAmp and console-wide loading are research, not implemented OG features.

This source snapshot retains inherited 360 code/docs and historical experiments. Only the OG paths above describe the current product. Original licenses and attribution are preserved; this is not a claim of independent authorship. See [LICENSE](LICENSE), [NOTICE](NOTICE), and the package notices.
