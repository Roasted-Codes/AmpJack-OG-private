# Compatibility and known limitations

## Supported target

Only stock Halo 2 TU1.5/u803 is targeted. Required XBE: 4919296 bytes, SHA-256 `21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd`. A folder/menu named “Halo 2 HD” does not prove the executable is stock. The test console's folder had a stock replacement with the HD executable backed up separately; this does not establish HD-mod compatibility.

## Evidence and status

- **Selected live build:** W63, `AmpJack63-u803-3ddc05b8`, logging OFF. Read-only XBDM inspection matched all seven hook targets and 19180 code bytes exactly. Owner reports controls and rumble working; original pad works alongside it.
- **Earlier W63 launch failures:** owner saw black screens with log option on and off. A later live session worked. Root cause and the condition that changed are not established; no crash fix claimed.
- **Branded preview:** same selected controller module, rebuilt wrapper names/display and one enable checkbox; logging forced OFF. Reproducible package and actual-wrapper CPU checks passed. A separate console recheck of the renamed wrapper is still required.
- **Wake:** pressing Xbox on a dark attached pad may only blink. Unplug/replug is the known workaround. The experimental W65 wake-only change did not fix the owner's case; no new wake behavior is claimed here.
- **Rumble-only experiment:** W65R exists in history, but probing the preferred running session identified W63 instead. Earlier assumed build-specific hardware attribution is superseded by that readback.
- **IGR:** not yet established. The modern pad's virtual GetState path could bypass a native input observer, but Cerbios' exact interception/hook order is unverified. Original-pad forwarding does not independently prove IGR survives.
- **XBDM:** works in the identified live Halo 2 session. Earlier periods of unreachability do not prove permanent title incompatibility or a frozen game. Probe actual current state rather than assume.

## Not established or implemented

- Every Xbox One/Series model/firmware, wireless support, every USB port/player assignment.
- Compatibility with other games, dashboards, HD-patched Halo executables or disc boots; console-wide automatic loading.
- Headset microphone/chat or the full AmpJack360 MixAmp feature. These are research only.
- Measured relative controller latency, a full long-run/reconnect matrix, or retail 64 MiB memory-headroom acceptance.

## IGR checking

Read the installed Cerbios version and its actual combo/port configuration first. Compare the original pad and modern pad using the same selected trainer. Original succeeds/modern fails suggests port selection or virtual-input visibility; original fails only with trainer suggests broader interaction. These are diagnostic distinctions, not proof of a specific BIOS interception.

Published [Cerbios notes](https://github.com/Cerbios/Cerbios-Xbox/blob/main/Cerbios.nfo) and [3.x notes](https://www.xbins.org/nfo.php?file=xboxnfo2572.nfo) document version-dependent controls. NKPatcher is comparative source, not proof that Cerbios uses its mechanism. Do not flash, reconfigure the BIOS or synthesize reset combinations as an untested workaround.
