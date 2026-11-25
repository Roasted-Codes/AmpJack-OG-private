# AmpJack OG — wired Xbox One input in Halo 2

Owner: Roasted. Request: research and implement overnight, up to ten DeepSeek workers.
Parent thread: Discord 1574624331043053618; request 1574633267582214215.

## Scope

First milestone ONLY: a wired Xbox One controller directly connected (passive USB-port cable permitted) controls Halo 2 on an original Xbox. No external PC or translating adapter as the main design. Buttons/sticks/triggers first, rumble next. Headset, DSP, wireless and other games are out of scope for this run.
Local private port: `~/Desktop/Xbox/AmpJack-OG`, upstream AmpJack b83cf6546e7d04c6013571d4641cb3e482b05e94. Original code preserved; additions under ogxbox/. No GitHub fork/push/PR or commits yet.

## Honest unknowns

- A modern controller's USB full-speed enumeration and endpoint descriptors must be demonstrated for the actual model. No Xbox One pad appeared in host lsusb at dispatch; never turn a host test into a hardware claim.
- A classic Xbox pad includes a hub for expansion accessories. A modern composite function is not automatically a hub. Neither observation alone decides host compatibility.
- No assumption that kernel/BIOS modification is needed or sufficient: first identify title-linked USB/XInput ownership. Do not flash, install host drivers or alter a real console.
- The initial generic inventory wrongly called current AmpJack EQ/surround stubs. Treat the pinned code as evidence, not that old inventory.

## Six independent workers

1. USB enumeration/speed/hub feasibility and controller model evidence (report).
2. OG Xbox USB stack/driver binding and minimum real implementation route (report).
3. Halo 2 XInput presentation, exact-build hooks and tested input shim if evidence permits.
4. Reusable wired GIP core adapter, host tests, bounded parsing and button mapping (code).
5. PIC/trainer loader and build/toolchain feasibility, non-destructive compile proof (report/code).
6. Independent existing-solutions survey and reproducibility/test strategy (report).

Write ownership is disjoint in the individual briefs. Workers must report real commands/results and hardware gaps. No emulator/runtime ownership granted to first-wave workers. Parent integrates after reviewing results; no fabricated platform backend or dummy function posing as a driver.

## Completion

Preferred: buildable diagnostic/driver payload plus a repeatable real-controller acceptance path. If USB/binding evidence blocks it: deliver verified limitation, tested reusable code and the smallest next physical measurement. Research completion is not playable-controller completion.
