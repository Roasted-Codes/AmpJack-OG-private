# OG-AmpJack

Private preview 0.1.0-preview.1. Selected build: W65 rumble-only (W65R),
AmpJack65 RUMBLE-ONLY. Target: Halo 2 TU1.5 u803, title ID 4D530064.
Module/driver bytes are unchanged. W63, W43 and W65W are historical experiments,
not maintained builds and not the selected release.

## Hardware status

Owner decision: Discord 1575345691214086249. The owner reports input and rumble
working with AmpJack65R-u803-5850fc63.xbtf. Supplied live XBMC DB readback shows
E:\Trainers\AmpJack65R-u803-5850fc63.xbtf Active=1, settings "1"; all other
AmpJack rows Active=0. This evidence was supplied to the packaging task, not
independently queried here. It overrides the earlier W63 selection.
The renamed wrapper is hardware UNTESTED until one console launch. Host tests
are not validation of physical USB, motors, timing or a complete console launch.

## Install

Keep the matched pair OG-AmpJack.xbtf and OG-AmpJack.bin together. The payload
must be E:\Trainers\OG-AmpJack.bin, native path
\Device\Harddisk0\Partition1\Trainers\OG-AmpJack.bin.
XBTF display name is exactly OG-AmpJack. There is ONE default-OFF option:
Enable controller support. Select it explicitly when testing. No logging option
or W63 logging-flags logic is present in the W65R loader.

## Portable build

Requires Python 3 (stdlib), clang, ld.lld and GNU binutils (readelf, nm, objcopy)
on PATH. No SDK, network, console, firmware, game or original workspace is
needed to package from this checkout:

    /usr/bin/python3 ogxbox/halo2-release/build.py

Optional --out accepts a new output directory, or an existing release output
with manifest.json. Default outputs are in dist/:
candidate/OG-AmpJack.xbtf, candidate/OG-AmpJack.bin,
OG-AmpJack-v0.1.0-preview.1.zip, manifest.json and SHA256SUMS.
The generated .build/ objects are not archived. ZIP metadata and artifacts are
deterministic with the same sources/toolchain; compiler changes may alter XBTF.

## Tests

    /usr/bin/python3 -m unittest discover -s ogxbox/halo2-release -p test_release.py
    AMPJACK_TEST_XBE=/path/to/owner/default.xbe /usr/bin/python3 -m unittest discover -s ogxbox/halo2-release -p test_release.py
    /usr/bin/python3 ogxbox/halo2-release/verify_export.py --xbe /path/to/owner/default.xbe

Package-only: 4 tests. Strict: 11 total (4 package + 7 actual-wrapper CPU methods),
requires Python unicorn. The owner-supplied XBE is read-only, never copied or
archived; expected SHA-256:
21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd.
Without AMPJACK_TEST_XBE strict tests explicitly do not run; no fabricated title
input is substituted. Kernel/file/allocation effects are synthetic host stubs.
Strict tests execute the real decoded release wrapper and original module at
0x01000000 and 0x83000000, checking cdecl(null), relocated image/BSS/host,
seven hooks, registers/flags/stack, 20 rejection cases, title mismatch, default
OFF, missing/corrupt payload, allocation/I-O failures, relaunch, current-site
rollback and permanent-failure fail-stop. W65R has seven baseline import checks,
not W63's extra logging imports. W63-only logging assertions were removed.
verify_export.py builds a fresh Git-visible source export and compares artifacts
before and after tests; writes verification.json. Scratch stays in the package.

## Provenance and memory

../work/65-bisect/rumble/src/ is the complete retained W65R source lineage:
27 source files, each byte-compared with the original and hashed in
inputs/provenance.json, with exact Git-tracked coverage. Normal builds check
all hashes and source inventory. This is a portable wrapper rebuild around a
pinned own-code module, not a claim of a portable full C driver rebuild.

inputs/module.elf SHA-256:
5850fc63b387eca58f1dcccae3a390341b66f999bd04d75ee12ddb18135d362b
inputs/module.bin and released OG-AmpJack.bin SHA-256:
5e63fb1afb9c26d15af8165471e2a982171db1f1e9a2fc6c4d6114bd148ec39c
The AJ43 module envelope contains no own filename/path; reconstruction from
ELF must equal the original selected payload byte-for-byte. No payload rename
patch is needed. inputs/layout.json and pins.h are exact W65R originals.
loader.c, bootstrap.S, bootstrap.ld and sha256.inc are byte-identical to W65R.
Only the generated pins copy renames the payload path; XBTF metadata is branded.
rebind_selected.py imports/audits an explicitly supplied original W65R tree;
normal portable builds need no access to that tree.

W65R sizes from its own layout/ELF/pins: resident allocation 36864 bytes,
file buffer 16384, initialized image 14992, mem_end 36220, module structure
21160. Native peak 53248; XBMC allocation 16384; combined peak 69632.
Wrapper dynamic relocations are forbidden; decoded trainer must fit XBMC heap.
../../tools/trainerfmt.py provides XBTF framing. host_helpers.py provides pure
ELF/XBE validation; no live-console adapter. ZIP allowlist: matched pair, README,
license, notices and manifest. No game, BIOS, SDK, credentials or device logs.
Preserve COPYING.GPL-3 and NOTICES.txt and complete corresponding source/notices
when distributing. No commit, push or publication is performed by this task.
