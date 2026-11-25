# OG-AmpJack build and test notes

## Portable package build

Requires Python 3, Clang, ld.lld and GNU binutils on PATH. From a clean private checkout:

```sh
/usr/bin/python3 ogxbox/halo2-release/build.py --out ogxbox/halo2-release/dist
/usr/bin/python3 -m unittest discover -s ogxbox/halo2-release -p test_release.py
```

These commands package a pinned, own-code module and rebuild the trainer wrapper. They need no original development directory, SDK, game executable or console. This is **not** a portable full controller rebuild from C; the historical module build still has separate toolchain/helper/metadata requirements. See the [release source map](../ogxbox/halo2-release/README.md).

Output: `ogxbox/halo2-release/dist/`, including the matched `candidate/OG-AmpJack-Halo2.{xbtf,bin}` pair, versioned ZIP, manifest and SHA256SUMS. `--out` may point to a new directory. Committed module/source identities must match; packaging is not permission to silently substitute a new driver build.

## Actual-wrapper CPU tests

Install Python Unicorn and explicitly provide your own stock u803 executable:

```sh
AMPJACK_TEST_XBE=/path/to/owner/default.xbe /usr/bin/python3 -m unittest discover -s ogxbox/halo2-release -p test_release.py
```

The test validates the external game's SHA-256. Never add the game to Git or the archive. Without that environment variable, strict CPU tests are explicitly not run; the package-only checks do not invent title data.

Qualification executed the actual generated wrapper and selected module: two load addresses, all hook destinations, entry flags forced zero even if bytes after the single option are nonzero, default OFF, title/payload mismatches, missing payload, rollback and permanent-failure fail-stop. Parent verification reproduced 4 package tests and 13 tests with the explicitly supplied owner XBE (4 package plus 9 CPU methods), including 20 rejection scenarios and 12 additional import-rejection cases. Fresh-export and integrated builds reproduced the selected deliverables byte-for-byte. Kernel/file/allocation effects are host stubs, not a physical Xbox.

## Source and identities

The selected source is [`../ogxbox/work/63-wake-rumble/src/`](../ogxbox/work/63-wake-rumble/src/). Packaging preserves payload SHA-256 `8bf54869e1635fbcb8313226da7abd243c0b4fc4729b1b664f2828e030380448` and original ELF `3ddc05b8c0c01a388ad9ab156660c8018a8a3d0fe4cc676af7548a5405ec7fab`. Only the wrapper/display/path changes; logging is forced OFF to match the identified live session. Resident/file-buffer allocation stays 45056/24576 bytes, not the smaller W65 experiment's allocations.

The owner's successful input/rumble report applies to the original pair whose code was read back live. Renamed-wrapper host qualification and physical acceptance are separate. Preserve source attribution and license files; no BIOS flash, SDK redistribution or game upload is needed.
