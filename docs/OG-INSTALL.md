# Install OG-AmpJack for Halo 2

## Requirements

- An original Xbox running XBMC (XBMC4Xbox / XBMC4Gamers) with trainer support. No BIOS flash or game patch is needed.
- Your own **stock Halo 2 TU1.5 / u803** executable: 4,919,296 bytes, SHA-256 `21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd`. The HD-patched executable is not supported.
- A wired Xbox One or Series controller and a passive Xbox-to-USB adapter cable.
- An original controller in port 1 for navigating XBMC. The modern pad goes in **port 2** and shows up to the game as player 2's controller.

## Install

1. Download [`OG-AmpJack-v0.1.0-preview.1.zip`](../ogxbox/halo2-release/dist/OG-AmpJack-v0.1.0-preview.1.zip) and unzip it.
2. FTP **both** files from `candidate/` into `E:\Trainers\`: `OG-AmpJack.xbtf` and `OG-AmpJack.bin`. They are a matched pair — never mix files from different versions.
3. In XBMC: Programs → Halo 2 → context menu → **Update trainer list**.
4. Trainer settings → select **OG-AmpJack** → tick **Enable controller support** → OK.
5. Plug the modern pad into port 2 and launch Halo 2 from XBMC. The trainer is only applied when the game is launched this way.

If the pad was already plugged in and stays dark, or only blinks when you press the Xbox button, unplug it and plug it back in.

## Uninstall / rollback

Untick the option or deselect the trainer in XBMC and relaunch; Halo 2 runs unmodified and the original controller works as normal. To remove it completely, delete `OG-AmpJack.xbtf` and `OG-AmpJack.bin` from `E:\Trainers\` and update the trainer list again.

## Notes

- XBMC activates one trainer per game. Having other Halo 2 trainers installed is fine, but only the selected one runs.
- The payload path (`E:\Trainers\OG-AmpJack.bin`) is built into the trainer; do not rename the files.
- BIOS in-game-reset combos (e.g. Cerbios IGR) from the modern pad are unverified. Use the original controller for IGR until that is confirmed.
