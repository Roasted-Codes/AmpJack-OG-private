# OG-AmpJack

Wired Xbox One / Series controllers in Halo 2 on an original Xbox, as an XBMC trainer.

## Install

1. Download the zip from the [latest release](https://github.com/Roasted-Codes/OG-AmpJack/releases/latest).
2. FTP `OG-AmpJack.xbtf` and `OG-AmpJack.bin` (in `Trainers/`) to `E:\Trainers\`.
3. In XBMC: Halo 2 → **Update trainer list** → select **OG-AmpJack** → tick **Enable controller support**.
4. Plug the pad into port 2 and launch Halo 2 from XBMC.

Needs stock Halo 2 TU1.5 (u803) and a passive Xbox-to-USB cable.

## Build

```sh
python3 tools/build.py --out build/
```

Needs Python 3, Clang, ld.lld and binutils. Tests and details in [`docs/BUILD.md`](docs/BUILD.md).

## Status

Works: input, wake, rumble, all buttons. To do: Share button mapping, MixAmp audio features.

## Thanks

- [AmpJack](https://github.com/Roasted-Codes/AmpJack): the Xbox 360 project this is ported from.
- [Jacckii](https://github.com/Jacckii/Xbox360-Series-Controllers-Native): the plugin AmpJack is forked from.
- [xone](https://github.com/dlundqvist/xone) (medusalix and contributors): controller protocol.
- [mt76](https://github.com/openwrt/mt76) (Felix Fietkau, Lorenzo Bianconi, Stanislaw Gruszka): adapter definitions in the shared headers.
- [XBMC4Xbox](https://github.com/Rocky5/XBMC4Xbox): trainer file format and loader.

[GPL-3.0](LICENSE).
