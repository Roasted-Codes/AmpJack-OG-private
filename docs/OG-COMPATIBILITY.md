# Compatibility and known limitations

## Supported target

- **Halo 2 TU1.5 / u803 only** (title ID 4D530064), stock executable 4,919,296 bytes, SHA-256 `21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd`. The trainer checks the executable before patching and does nothing if it does not match.
- Launched through XBMC's trainer path. A folder called "Halo 2 HD" does not mean the executable inside is stock; the HD 480p patch is a different executable and is not supported.

## Tested

- Owner's console (hard-modded original Xbox, Cerbios, XBMC): modern pad on port 2 gives full input and rumble; the original controller on port 1 keeps working alongside it. Tested pad: Xbox Series controller (`045e:0b12`) over a passive cable.
- The shipped module bytes are identical to that tested build. The renamed `OG-AmpJack` wrapper passed reproducible build and CPU-emulated tests (two load addresses, title/payload guards, rollback, fail-stop); one console launch confirms the renamed files.

## Known limits

- **Wake:** if the pad is attached but dark, pressing the Xbox button may only blink. Unplug/replug fixes it.
- **IGR:** BIOS in-game-reset combos from the modern pad are unverified. The trainer answers the game's controller queries itself for port 2, so a BIOS that watches the native controller path may not see the combo. Use the original pad for IGR.
- **Not supported / not implemented:** other games, dashboards, disc boot, console-wide loading, wireless pads, other ports, headset audio or chat (research in progress), the HD-patched executable.
- Not every Xbox One / Series controller model or firmware has been tested.
- No measured end-to-end latency comparison yet; the driver polls the pad every 4 ms, Halo 2 reads input once per frame.
