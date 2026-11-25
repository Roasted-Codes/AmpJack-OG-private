# OG-AmpJack — private source snapshot

Experimental Xbox One/Series controller support on an original Xbox, through a passive USB cable.

## Hardware status (owner reports)
- W43: Halo 2 TU1.5/u803 launched through XBMC; modern-pad buttons/sticks/triggers work after replug. Original pad works alongside it. No rumble.
- W63: combined wake/rumble/logging experiment black-screened with logging enabled and disabled. Cause unproved.
- W65 WAKE-ONLY: launches, but Xbox-button wake still blinks; replug restores input. Wake fix NOT successful.
- W65 RUMBLE-ONLY: built and host-tested; hardware result pending.

## Source map
- `ogxbox/integration`, `gipdriver`, `gip`, `halo2`, `loader`: base implementation.
- `ogxbox/work/32-opus-final-integration`: W43 module build lineage.
- `ogxbox/work/43-trainer-candidate`: known playable trainer packaging.
- `ogxbox/work/63-wake-rumble`: failed combined experiment, preserved for diagnosis.
- `ogxbox/work/65-bisect/{baseline,wake,rumble}`: independent source copies, build tools and tests.
- `tools/trainerfmt.py`: trainer format helper originally in LAN_Stats.

This snapshot retains source/build scripts and selected technical documentation. It excludes game XBEs, BIOS/SDK assets, compiled outputs, USB captures, screenshots, local credentials, worker transcripts, and emulator/vendor checkouts. Some historical scripts reference the original workspace and separately installed toolchains or game files; this is not a portable one-command distribution. No new console test was performed for this upload.

The parent tree is AmpJack upstream commit b83cf6546e7d04c6013571d4641cb3e482b05e94. Existing licenses and notices are retained. The public AmpJack repository is not changed.
