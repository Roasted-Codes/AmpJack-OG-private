# OG-AmpJack build and test notes

## Rebuild the package

Requires Python 3, Clang, ld.lld and GNU binutils (`readelf`, `nm`, `objcopy`) on PATH. From a clean checkout:

```sh
/usr/bin/python3 ogxbox/halo2-release/build.py --out ogxbox/halo2-release/dist
/usr/bin/python3 -m unittest discover -s ogxbox/halo2-release -p test_release.py
```

This rebuilds the trainer wrapper around the pinned controller module (`ogxbox/halo2-release/inputs/module.{elf,bin}`) and produces the matched `candidate/OG-AmpJack.{xbtf,bin}` pair, the versioned ZIP, `manifest.json` and `SHA256SUMS`. No SDK, game executable or console is needed. The build is deterministic for the same sources and toolchain.

This is **not** a from-scratch rebuild of the controller module in C; that lives in `ogxbox/work/65-bisect/rumble/` with its own toolchain requirements. The packaging verifies every source file's hash against `inputs/provenance.json` and refuses to substitute a different module.

## CPU-emulated wrapper tests

Install Python Unicorn and point the tests at your own stock u803 executable (it is hashed, never copied):

```sh
AMPJACK_TEST_XBE=/path/to/default.xbe /usr/bin/python3 -m unittest discover -s ogxbox/halo2-release -p test_release.py
```

Without `AMPJACK_TEST_XBE` only the four package tests run. With it, 11 tests execute the real generated wrapper against the real game image at two load addresses: hook installation, default-OFF, title and payload mismatch, missing/corrupt payload, allocation/I-O failure, rollback and fail-stop. Kernel and file effects are host stubs, not a real Xbox.

`verify_export.py --xbe ...` repeats the whole thing from a fresh Git-visible export and checks the rebuilt artifacts are byte-identical to `dist/`.

## Identities

- Module ELF `5850fc63b387eca58f1dcccae3a390341b66f999bd04d75ee12ddb18135d362b`
- Payload `OG-AmpJack.bin` `5e63fb1afb9c26d15af8165471e2a982171db1f1e9a2fc6c4d6114bd148ec39c`
- Source: [`ogxbox/work/65-bisect/rumble/src/`](../ogxbox/work/65-bisect/rumble/src/)

Preserve license and attribution files; no BIOS, SDK or game content is redistributed.
