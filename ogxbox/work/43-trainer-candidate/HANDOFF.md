# Worker 43 handoff — candidate, not cleared for physical test

## Owner-copy artifact (do not physically install yet)

/home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work/43-trainer-candidate/release-build/AmpJack43-u803-candidate.zip

Archive SHA256:
24bee5b09dbb2f39651c4ac49ac7969de81a0d4d8c376535f889bf298ada530b

Exactly two eventual guest destinations, NO overwrites:
E:\Trainers\AmpJack43-u803-7bbfdafa.xbtf
E:\Trainers\AmpJack43-u803-7bbfdafa.bin

Payload SHA256 d6109c156e832c68443dc75938156379e462e862c7829e2de5ee3e1406714dde
Trainer SHA256 ecbb4a771c7c7ef7dfc401b95c7b452b386a2f33558f5a35c5e4b546c7d4e039
Only copy those two files eventually; retain archive README/checksums/notices on PC.
No XBE, TU, guest images, machine configs or SDK material are in the archive.
NOTICES explicitly distinguishes the local frozen-source requirement from a full
redistributable corresponding-source bundle. Nothing was uploaded.

## Exact host commands

From /home/roasted/Desktop/Xbox/AmpJack-OG:

Existing final candidate verification:
/usr/bin/python3 ogxbox/work/43-trainer-candidate/build.py check --out /home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work/43-trainer-candidate/release-build
/usr/bin/python3 ogxbox/work/43-trainer-candidate/test_candidate.py --out /home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work/43-trainer-candidate/release-build

Complete fresh rebuild, native-code qualification, package, unpack and native-code
requalification (destination must not already exist):
/usr/bin/python3 ogxbox/work/43-trainer-candidate/release.py --out /home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work/43-trainer-candidate/owner-rebuild

Verify the shipped archive independently by unpacking and retesting its bytes
(destination must not already exist):
/usr/bin/python3 ogxbox/work/43-trainer-candidate/release.py --verify-archive /home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work/43-trainer-candidate/release-build/AmpJack43-u803-candidate.zip --out /home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work/43-trainer-candidate/owner-archive-check

Use /usr/bin/python3, not the Hermes venv python (which lacks Unicorn). Requires
local clang, ld.lld, binutils and Unicorn already available on this host. Frozen
read-only W32 ELF/layout, W31/W33 evidence, integration sources, LAN_Stats framing
helper and pinned XBE are required. The scripts never build those projects or
connect to guests. New sources and scripts live only in this work directory.

Real executed release command used release-build, initially absent. Both original
and unpacked CPU suites returned 7 tests OK, no skips. Evidence is in
release-build/{build.log,commands.log,cpu-tests.log,manifest.json,audit.json,
verification.json,ARCHIVE-SHA256SUMS} and release-build/unpacked/cpu-tests.log.
Older build/ is development output, NOT the artifact to install or evaluate.

## Deferred ordinary-launch runbook (after lease release and runtime clearance)

This work has no runtime lease. The following are human/operator steps for the
parent's later authorized runtime work, NOT actions performed by worker 43.
Physical hardware remains separately uncleared; the payload is a packaging vector.

1. Check profile trainerpath = E:\Trainers in XBMC4Gamers. Match both local hashes.
   If either destination already exists, stop; never overwrite an existing trainer
   or use TrinityLive.bin/stats trainer paths. Owner copies only the two files.
2. Original pad in port 1. Modern wired pad in port 2 using passive DATA cable and
   passive Xbox adapter. Keep the original pad for recovery. Wireless and physical
   port inference are not qualified; module advertises fixed virtual index 1.
3. Default XBMC4Gamers skin: Games -> Halo 2 -> White/context -> Trainers (cheats)
   -> Update trainer list. Same menu -> Trainer settings -> choose 'AmpJack43 u803
   CANDIDATE' (this deselects a previous trainer). Leave enable option UNTICKED -> OK.
4. First ordinary disabled launch from Games, not file manager. Allow retail->TU
   relaunch. Verify stock-pad control and no AmpJack hook changes. Missing option,
   retail or different TU must remain inert. No debugger injection/PC input loader.
5. Return normally to dashboard. Tick 'Enable AmpJack43 candidate' -> OK -> launch
   Halo 2 from Games. Install is before decoded 0x2DA9DE/XInitDevices, never main.
   Observe the ordinary launch, not a resumed save state or worker 42's injection.
6. Evidence after return in that exact boot, by separately authorized read-only
   observation: actual trainer base from XBMC [0x8000000C]+167; decoded bytes match
   candidate; resident image from actual allocation, all 20 relocations valid;
   ogx_g_module=resident+0x3978; host bytes match manifest/W33 bindings. At
   module+21124 expect BF; module+21128 expect 0; attached at module+21120 is not
   proof of gameplay and may still be 0 before enumeration.
7. Seven site -> resident-relative target expectations (no eighth hook):
     0x41517D FindClassDriver       -> resident + 1907
     0x4139A5 XGetDeviceChanges     -> resident + 1487
     0x413A12 XInputOpen            -> resident + 1572
     0x413A68 XInputClose           -> resident + 1630
     0x413A74 XInputGetCapabilities -> resident + 1676
     0x413C4C XInputGetState        -> resident + 1728
     0x413CBF XInputSetState        -> resident + 1780
   Each is E9 with exact rel32, untouched displaced tails. Confirm original class
   table/ports unchanged, dtype identity 0x4127D8, required Add/Remove callbacks and
   IRQL SLOT addresses in host, never cached kernel function addresses there.
8. Separately test title survival, original-pad port 1 behavior, native modern-pad
   enum/attach, actual buttons/sticks in menus/game, sustained XGetDeviceChanges
   pump, unplug/replug and retirement. BF/0 or attach alone do not prove control.
9. Later ordinary cold title/console launch from dashboard is a separate gate.
   Record retail/TU gate behavior, startup headroom, actual allocation and file
   handles. Do not substitute host fixture peaks for guest retail-RAM evidence.
10. Recovery: return to dashboard -> untick/deselect -> fresh stock title boot.
    Verify all seven original spans and stock control. Only after this, remove
    ONLY the two named files and Update trainer list. Never free active resident
    memory or hot-unhook a running title. Permanent rollback readback failure
    intentionally halts pre-entry with resident allocation retained; use an
    owner-controlled cold recovery under that runtime authorization.

## What remains open

All ordinary dashboard/guest/native USB/control/cold recovery gates above. This
package has host machine-code proof and a real archive, not physical-install
approval. Independent worker 42's unmodified W32 debugger observation is neither
consumed nor changed by this task. No claims that existing failing legacy suites
11/22 were fixed. No new driver or integration behavior is claimed.
