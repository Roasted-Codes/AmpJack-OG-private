# OG-AmpJack - Halo 2

Private preview 0.1.0-preview.1. Owner-selected live W63 combined module,
byte-for-byte unchanged. Target: Halo 2 TU1.5 u803, title ID 4D530064.
The wrapper always passes flags=0, preserving the selected logging-OFF mode.
Existing wake, rumble, caps, ticks/IRQL, hooks and optional logger remain intact.
No module/driver changes or allocation increase relative to selected W63.

## Build from a clean private checkout

Requires /usr/bin/python3 (stdlib only), clang, ld.lld and GNU binutils
(readelf, nm, objcopy) on PATH. No SDK, original development directory,
network, console, firmware, game binary or emulator is needed to package.

    /usr/bin/python3 ogxbox/halo2-release/build.py --out ogxbox/halo2-release/dist

--out accepts a new output directory anywhere; omit it to use the above default.
A populated directory is accepted only if it already has a release manifest.
Outputs: candidate/OG-AmpJack-Halo2.xbtf, candidate/OG-AmpJack-Halo2.bin,
OG-AmpJack-Halo2-v0.1.0-preview.1.zip, manifest.json and SHA256SUMS.
The .build directory contains generated wrapper objects, ELF and binary;
it is not in the ZIP. ZIP metadata and hashes are deterministic for the
same sources and toolchain. Different compiler versions may change wrapper bytes.

## Use and limitations

Keep the matched pair together. The native loader requires the payload at
E:\Trainers\OG-AmpJack-Halo2.bin (native path
\Device\Harddisk0\Partition1\Trainers\OG-AmpJack-Halo2.bin).
The XBTF display is OG-AmpJack - Halo 2 with exactly one default-OFF option:
Enable controller support. Select it explicitly when testing.

The owner selected the trainer currently running and reports input and rumble
working after replug. Parent's read-only evidence in work/68-owner-selected-baseline
(SELECTION.json and LIVE-TRAINER-IDENTITY.json) identifies it as W63 combined,
not W65R: all seven hook targets derive base 0x83fcf000 and all 19,180 code
bytes match SHA-256 3538c20e7fe0382bb450e1c6af113a193c8a2cb08118a7e44a2991c80a0f52a9.
Its 28-byte ogx_log_st at base+0xa368 is entirely zero: logging OFF, no writes.
Evidence file hashes and identity summary are retained in inputs/provenance.json;
these observations were supplied by parent, not reproduced by host CPU tests.

Earlier W63 black-screen observations with logging ON and OFF remain valid
historical reports; cause and changed condition are UNRESOLVED. This is neither
a universal failure claim nor a new hardware fix. The previous assumed W65R
hardware identity is superseded, not a verified build identity.
This branded/recompiled wrapper is hardware UNTESTED. Host CPU checks do not
validate real USB, timing, motors, replug behavior or a complete console launch.

## Verification

Package-only tests (no proprietary input and no Unicorn required):

    /usr/bin/python3 -m unittest discover -s ogxbox/halo2-release -p test_release.py

Strict actual production-wrapper tests require Python unicorn and an explicit
owner-supplied stock u803 XBE. The helper validates the entire XBE SHA-256:
21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd.
Never copy that XBE into this repository or archive. Invoke:

    AMPJACK_TEST_XBE=/path/to/owner/default.xbe /usr/bin/python3 -m unittest discover -s ogxbox/halo2-release -p test_release.py

Without AMPJACK_TEST_XBE, strict CPU tests are explicitly NOT RUN, not replaced
with invented title bytes. The strict suite executes the decoded release XBTF,
real loader and unchanged module with actual owner-supplied title guards;
kernel/file/allocation effects are host synthetic stubs, not an Xbox emulator.
It covers two load addresses, all hook targets, relocation/BSS/host image,
register/flags/stack preservation, rollback/current-site partial write, permanent
restoration fail-stop, title mismatches, missing/corrupt payload, allocation/I/O
failures, default OFF and relaunch. It also proves actual W63 entry flags=0
when the byte after the single option is 1 or 255, all six extra import checks,
and logger OFF/no file calls after repeated execution of the unchanged logger
service. AMPJACK_TEST_OUT optionally selects its output.

To repeat the fresh Git-visible export, new-output build, byte-for-byte artifact
comparison, package-only tests and strict production-wrapper tests together:

    /usr/bin/python3 ogxbox/halo2-release/verify_export.py --xbe /path/to/owner/default.xbe

This writes verification.json and uses only ignored .verification-work/ below
the package for scratch. It exports package/source dependencies, never the XBE;
strict tests read that explicitly supplied owner file in place.

## Portable source map and provenance

- ../work/63-wake-rumble/src/: complete selected W63 controller source lineage.
  inputs/provenance.json records each source hash, checked on every package build.
- inputs/module.bin: committed own-code AJ43 envelope, exact tested payload SHA
  8bf54869e1635fbcb8313226da7abd243c0b4fc4729b1b664f2828e030380448.
- inputs/module.elf: own-code original module ELF SHA
  3ddc05b8c0c01a388ad9ab156660c8018a8a3d0fe4cc676af7548a5405ec7fab.
  Packaging reconstructs its AJ43 envelope independently and requires equality.
- inputs/layout.json and inputs/pins.h: original generated W63 layout/constants.
  build.py changes only the payload filename in the generated pins copy.
- loader.c: original flags-aware W63 cdecl wrapper with all six extra import
  checks; its ONLY source change forces flags=0 rather than reading option [1].
  bootstrap.S, bootstrap.ld, sha256.inc are exact unchanged original W63 files.
  The wrapper is recompiled/relinked on every build; generated pins rename only
  the payload path. rebind_selected.py can audit/import explicitly supplied
  originals and frozen selection evidence; normal portable builds do not need it.
- ../../tools/trainerfmt.py: existing repository XBTF format implementation.
- host_helpers.py: pure ELF/XBE validation portion of work/32 helper; live-console
  adapter removed and hard-coded external XBE default removed.
- wrapper_harness.py: strict production-wrapper CPU harness adapted to W63.
- test_release.py: package checks plus optional strict wrapper suite.

This is a reproducible package build from a pinned own-code module, NOT a claim
of portable full controller rebuild from C. Historical driver build scripts
remain untouched. Manifest connects version, source hashes, original ELF,
payload, generated wrapper and trainer. Resident allocation stays 45056 bytes,
file buffer 24576 bytes, image 20492 bytes, mem_end 43912; XBMC allocation
16384 bytes. These are larger than W65R but unchanged from selected live W63.
No dynamic wrapper
relocations are allowed and decoded trainer must fit the XBMC heap.

ZIP inventory is explicitly allowlisted: matched pair, this README, license,
notices and manifest. No game, BIOS, SDK, credentials, device logs or worker
transcripts are included. Preserve COPYING.GPL-3 and NOTICES.txt; source lineage
and upstream notices remain in the private checkout. Destination is the private
AmpJack-OG repository only; the public AmpJack repository is unchanged.
