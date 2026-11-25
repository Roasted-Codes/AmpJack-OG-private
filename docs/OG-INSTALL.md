# Install OG-AmpJack for Halo 2

## Requirements

- An original Xbox able to run XBMC trainers; no BIOS flash is required for this trainer.
- Your own stock Halo 2 TU1.5/u803 executable: 4919296 bytes, SHA-256 `21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd`.
- Wired Xbox One/Series controller and passive Xbox-to-USB cable. Hardware reports here describe the owner's tested pad, not every firmware/model.
- Keep an original pad in port 1 for navigation; the modern pad is presented as player/port 2.

The current preferred legacy pair is `AmpJack63-u803-3ddc05b8.{xbtf,bin}`, with Enable on and Write log off. The cleanly named preview preserves that module but still needs a hardware recheck of the rebuilt wrapper. Earlier W63 black-screen reports remain unresolved even though the selected live session ran successfully.

## Install

1. Back up your working trainer pair and record its settings. Do not delete it yet.
2. Download the [private preview archive](../ogxbox/halo2-release/dist/OG-AmpJack-Halo2-v0.1.0-preview.1.zip).
3. FTP BOTH files from `candidate/` into `E:\Trainers\`: `OG-AmpJack-Halo2.xbtf` and `OG-AmpJack-Halo2.bin`.
4. In XBMC, refresh/update the trainer list for Halo 2. Select **OG-AmpJack - Halo 2**, tick **Enable controller support**, and confirm.
5. Launch Halo 2 through XBMC's game/trainer path. A direct debugger launch does not demonstrate XBMC trainer activation.
6. Test modern input, vibration and the original pad. If the modern pad only blinks, unplug/replug it. Do not claim wake is fixed.

The payload path is built into the trainer. Do not rename only one file or mix files from different packages. The wrapper has a single option and always leaves file logging OFF. XBMC's observed trainer database selects one active trainer for the game; several installed files do not imply they all run together. Do not edit a live cached trainer database.

## Rollback and uninstall

Select the original `AmpJack63-u803-3ddc05b8` trainer, with Enable on and Write log off, and relaunch using the same route. To disable support, deselect/disable the trainer and relaunch; the original pad should remain usable. Do not expect the modern pad to work in an unmodified game.

After the new pair is verified, archive superseded **AmpJack** pairs outside the configured trainer-scan directory, retaining checksums and original paths. Do not remove unrelated Yelo, stats, Halo2FTP, or Trinity trainers merely because they are installed. Never delete saves, game assets or BIOS files. The console cleanup is a separate verified move/restore operation, not an automatic action performed by downloading this package.

## IGR

IGR compatibility is unverified. Cerbios combinations and allowed controller ports vary by version/configuration. Save progress before any owner-operated reset test. An IGR failure on the modern pad does not by itself prove the BIOS was changed or the console froze. No firmware editing or automatic reset is part of installation.
