# Build and test

## Package the release

Needs Python 3 (stdlib only), Clang, ld.lld and GNU binutils (`readelf`, `nm`, `objcopy`) on `PATH`. From a clean clone:

```sh
python3 tools/build.py --out build/
```

This writes `build/Trainers/OG-AmpJack.xbtf`, `build/Trainers/OG-AmpJack.bin`, `build/OG-AmpJack-v0.1.0.zip`, `manifest.json` and `SHA256SUMS`. The build is deterministic: with the same toolchain the `.bin` and `.xbtf` match the released files byte for byte. No SDK, game file or console is needed.

## What gets built

- `src/trainer/` is the XBTF trainer stub XBMC runs at launch. `tools/build.py` compiles it and frames it with `tools/trainerfmt.py`. It checks the game, loads `E:\Trainers\OG-AmpJack.bin`, relocates it and installs the hooks.
- `OG-AmpJack.bin` is the controller module. It is pinned in `tools/inputs/` (`module.elf`, the packed `module.bin`, `layout.json`, `pins.h`); the build checks every source and input against `tools/inputs/provenance.json` and refuses anything that differs.
- `src/core/` (GIP protocol, ported from xone) and `src/ogxbox/` (USB driver, Halo 2 hook sites, XInput presentation, installer) are the module's source. To rebuild the module itself:

  ```sh
  bash src/ogxbox/integration/build_pic.sh
  ```

  `src/ogxbox/integration/out/pic.elf` is byte-identical to `tools/inputs/module.elf` with the same Clang/LLD.

## Tests

```sh
python3 -m unittest discover -s tests -p test_release.py
```

Runs 4 package tests (identity, reproducibility, payload rejection, zip contents). With your own stock Halo 2 u803 `default.xbe` and the Python `unicorn` module, 7 more tests run the real trainer stub and module in an emulated CPU at two load addresses: hook install, default off, title and payload mismatch, missing or corrupt payload, allocation and I/O failures, rollback and fail-stop. Kernel and file calls are host stubs.

```sh
AMPJACK_TEST_XBE=/path/to/default.xbe python3 -m unittest discover -s tests -p test_release.py
```

The XBE is only read and hashed, never copied. `python3 tools/verify_export.py --xbe /path/to/default.xbe` repeats the build and both test runs from a fresh copy of the Git-visible tree and checks the outputs match.
