> Historical checkpoint: current selected build/status and scope are in [OG compatibility](../docs/OG-COMPATIBILITY.md) and [the root README](../README.md). Do not treat this older document as the current release contract.

# AmpJack-OG — current checkpoint

Current as of 2026-11-25T02:49:06.781908+00:00. Ownerconfirmedphysicaldone1574978955318923306.

## CURRENT result and next work

Last updated: 2026-11-25T04:13:53.271391+00:00
Contract: private AmpJack modern wired controller -> real Xbox Halo2 u803. No PC translator as product, BIOS flash, audio/wireless/rumble, public changes or global routing changes.

VERIFIED: standalone physical input subset (A/B/X/Y, sticks, full/released triggers) and three REAL held-A cable-unplug/replug cycles under repaired xemu. Source/driver candidate6cebc4cd965658566ed973b50d7eb34bb9d1fcc45913f1dcd7f9c4f856c1f6a4. Each held button neutralized, fresh input returned, cumulative successful closes3/6/9, four enumeration completions, no STEPFAIL/CFGFAIL/ATTACH_REFUSED. Evidence work/23-reconnect-runtime/VERIFIED-RECONNECT.json and physical-run.log. Capture~315hostseconds, last heartbeat270guestseconds: don't overstate exact5minute guest-clock acceptance. Dpad/shoulders/partial triggers and Halo2/originalXbox remain unproved.

EXIT CAVEAT: physical-exit.png still GREEN after stock Back+Start; GIPEXIT notlogged. Do NOT claim successful title manualexit in this final session. QMPquit did execute and native/desktop exited, xpad reattached, primaryconfig preserved. Earlier automatictrial manualexit was seen atlauncher after rawpad wasremoved. INFERENCE: known single-async-TD xemu limitation can stall virtualstockpad while modernINpending; not a proven diagnosis of the exit attempt. Source and traces retained; not a reason to rebuildanotheremulator now.

NEXT ACTIVE: DeepSeek24 actualNous worker proc_cd318cee8c14, sessionlocal-e4949767066d11e6713f75d2789f873023158d360e7b0583634cf731f58f835b,13API/35tools verified atintake. Brief work/briefs/24-halo2-input.md. Owns integration/ +work/24-halo2-input/ ONLY; driver/frozen23/20/core/H2targets readonly. One offline implementation batch,100calls/75active minutes; actualloadable title module+capture replay+guardedinstaller readiness. Parent reviews before any game/runtime/human ask. No paused/stopped project gate; no further control presses needed during coding.

PARALLEL chat repair COMPLETE at native-command layer: parent opened its own normal Hermes CLI, ran /busy steer and /busy status through the supported gateway-backed interface, observed live mode steer, then /quit exited0. PARENT-APPLIED.json in work25 preserves proof. No restart, impersonation, credential inspection or globalmodelchange. Owner does NOT need to type the command. The next genuine concurrentDiscord message still needs observation before claiming the notification path itself tested; savedconfigalone was not treated as proof.

RUNTIME NOW: none. Physical capture job proc_3e35f9a7f784 exited0 after QMPquit; native2266537 gone, ownedprivate desktop inactive. Protected primary and frozen20 unchanged,23testcopy preserved. Existingmonitor gate alreadyresolved; don't resurrect it. Parent alone coordinates future live/human tests. Source21 two batches closed;22 expert/fallbackclosed, parentfail-closed correction tested; no duplicate continuations.

Last batch: reconnect cleanup physically verified; useful new evidence supports moving from standalone app to game XInputmodule, NOT more prerequisite-only cleanup. Mission budget continues; old worker caps notreset. No commits/pushes.

## Historical checkpoint and evidence timeline (superseded where contradicted above)

Last updated: 2026-11-24T19:10:16Z (final audit validation; author openai-codex/gpt-6.1-sol).

## Objective and contract

Wired045e:0b12 Series controller → passive cable → ORIGINAL Xbox Halo2 controls, with no PC/active translator in the final input path. Buttons/sticks/triggers now; audio/headset/wireless/rumble and Guide IGR/shutdown excluded. xemu+real USB passthrough is the development testbed, never console proof.

Contract: Sol audit-only, max75 tool turns/2400s; DONE is evidence-backed canonical plan plus one restartable DeepSeek assignment. Audit outputs complete; no implementation or runtime launched. Parent checks audit before releasing DeepSeek17. Canonical plan: PLAN.md; evidence: work/sol-audit/AUDIT.md, status.json, input-hashes.json, evidence-summary.json. No competing tracker/controller.

## Handoff — 2026-11-24

VERIFIED: git main, ?? ogxbox/, no tracked diff. No clean committed ogxbox baseline. No emulator process observed; safety guard is not an emulator. No active writer was launched by this audit. Owner reports worker16 stopped. Its source edits remain; work/16-stream/ absent.

VERIFIED historical artifacts: real console reaches classFF81/no stock match, not input. Emulator v3 attaches, fetches config IF0 EP82/02 int4, opens handles, logs TWO status-like RX/FIVE TXDONE records, returns to launcher; no0x20/button proof. Physical presses not confirmed. Old driver console PINFAIL/hang remains a safety warning; network loss alone proves no crash.

VERIFIED independently from linked XBE bytes: +14 is actual completion length before rearm; +20 preserves mapped request length, NOT true RX count; +24 is linkage, NOT status; header+4 is status. Current source still mislabels/logs those fields. No-identify path leaves gamepad=0 and rejects input even after power. Drain resets ring before consumption, risking DPC overwrite. These defects do not establish every cause of prior silence.

VERIFIED current-source host tests11/14/15:48/31/44 checks pass; real alt0 fixture regression retained. Old binary pin check passes. They do not cover the actual no-identify normal path or establish current-source runtime.

Candidate identity: existing bin/default.xbe SHA2568d7def8ed1fed0af4c5e11491797f9036c9c571c4605a42de5ab73fd989384df,184320B equals saved v3 runtime binary; NOT rebuilt interrupted worker16 source. main.c SHA2568a9eedb3b7530bd700b67b81400a920e4f2fd6307ecde4274c0718c521c59f71; gipdrive.h SHA256ce0eea43ec258951d228f53ba8a954f631e3dc26f5d9582607fa5c73dba72431. Full manifest in sol-audit.

EXTERNAL SOURCE, verified checkout: OGX-Mini HEAD8818dc99d62bbb49c3068520f6713984c5fc11a2 names this pad and arms64B IN then POWER_ON→S_INIT with completion servicing. Adapter/TinyUSB, not Xbox URB proof or a tested fix. Existing hardened gip/integration/halo2/loader components are reusable; no runtime installer or Halo controls demonstrated.

Last batch: audited interrupted source, reran existing synthetic tests, traced decisive URB/PNP instructions and hashed source/binary/reference; useful new field/gate evidence. Usage unknown; no worker/runtime batch run. Continue only with the narrow corrected transport+real input experiment, not another general audit or rewrite.

## Next, gates and protection

ONE next assignment: work/briefs/17-sol-execution.md. DeepSeek implements minimal evidence-backed corrections, rebuilds/identifies actual installed candidate, tests standalone with real pad and confirmed presses, optionally observes existing unprivileged USB trace. Max two code batches, one no-pad/two pad runs,90min cumulative active work; failure/stop/handoff contract in brief. Parent owns human contact and final evidence review; return untimed launcher setup through supported completion if live contact cannot occur while worker runs. No PRESS_NOW polling.

Superseded: MISSION's absent-hardware/no-console-permission assumptions; old Fable-only scheduling/next instructions and claimed latency/echo causes. fable-audit/COORDINATOR_STATE.json remains read-only; parent updates coordination. Do not create the old file's suggested sol coordinator.

Protected: real console until SAME candidate passes full emulator lifecycle; EEPROM/HDD/toml; host settings/network/credentials; routing; git history; all unrelated projects. One runtime owner, max2 xemu. No capture module/elevation/install without authority. usbmon not found by audit probes; exact capture capability remains unproved. Future slice2 owns unplug/cancel/cleanup before intentional disconnect; slice3 Halo emulator; slice4 original-console proof.

Uncommitted: all ogxbox/ is untracked project work. This audit authored only PLAN.md, PROJECT_STATE.md, work/sol-audit/ and work/briefs/17-sol-execution.md. No production cleanup/commits. Restart by reading this checkpoint, status, brief; recheck hashes/process owner. Parent's review/release is pending, not a request for owner/model approval already granted.


## Sol parent release — 2026-11-24

Audit accepted after independent model/provider usage verification, protected-input hash check and baseline host-suite reruns. Evidence: work/sol-audit/PARENT-REVIEW.md and parent-checks/results.json. DeepSeek17 is authorized and launched as proc_754a55f831a0 with briefs/17-sol-execution.md; no additional Fable or owner approval required. Current phase: slice1 implementation under Sol review, NOT working buttons. Source/runtime ownership: DeepSeek17 only for gipdriver/ and work/17-sol-execution/ until explicit completion handoff. Parent owns PLAN/checkpoint/human contact and accepts actual results. Same bounded code/experiment/time allowance in plan; no unbounded automatic retries. No real console work.


## DeepSeek17 candidate review and runtime continuation

Parent independently checked worker17 source/EXE/XBE/ISO hashes and final pin verifier; match saved status. Tests14/15/17 pass; test11 has exactly one reproduced obsolete full-state-format expectation, with corrected complete-field coverage in test17. Not all old tests are green and no real input result is claimed. Frozen candidate SHAe4152ea3969978f27cbc144f002190439058a52872e11c64f722350f52e9b116,188416B. No rebuild allowed during runtime. Parent accepted bounded testing, not slice1 completion.

Same DeepSeek session local-2637018498ef24aea751a85dc260a7768e3775f4d2fbbda958509ca14b028f6e continues via proc_069f72af4aaf / briefs/17-runtime-handoff.md: no-pad control, exact guest hash then untimed launcher handoff. One code batch spent, no runtime experiment yet at dispatch. No budget reset/new implementation worker. Parent started only private desktop; helper XTEST probe failed (recorded); targetedXSendEvent harmless positive control required before navigation. Parent's exact toml backup runtime/xemu.toml.before SHA58ea136f...4841 retained. No emulator had been booted by parent before the handoff assignment. Parent resumes physical-contact ownership only after completion.


## Owner steering — wait for confirmed physical inputs

Message1574891667817767053 requires waiting for owner readiness before any real-button acceptance window. Last batch2 run used exact candidate ae9899098a5dd83312460cc8e004d3bc5fbd2f84fbe0b849aab7fcefb516b6cb (guest offline SHA matched); received14 status/power-like RXs and no input report, but physical presses were deliberately not requested, so NOT a failed button test. Actual CB lines showed kind=in/urb=in/buf=rx and kind=tx/urb=tx/buf=tx with correct handles; crossed callback/buffer hypothesis not observed. Do not repeat the worker's unsupported conclusion that HCD routing is definitely broken. Verbatim evidence runtime/pad-run-2.log and pad-run-2-summary.json.

Code2/2,no-pad1/1,pad2/2 spent; no more patch/run loop under this old contract. Sol must explicitly review/re-scope a human-synchronized acceptance, not reset counters. Current scope is waiting for owner-ready; no new worker. QMPquit done, unitinactive, hostxpad reattached, toml restored58ea136f...4841, private desktopstopped. Next conversation: obtain readiness, prepare test, send GO when actually ready, get owner confirmation of performed presses, then judge evidence. No lack-of-input failure claim without the physical positive-control action.

## Independent Astra diagnosis — 2026-11-24

Owner-requested openai-codex/gpt-6-astra diagnosis DONE; not working-button acceptance and not a reset of worker17's budget. Evidence: work/astra-diagnosis/{REPORT.md,status.json,input-hashes.json,verification.json,NEXT-TEST.md}. Frozen ae989909… XBE / 8bb6e880… main / 5f642af8… header unchanged. Latest actual human-run.log recount:13 RX, all03;2 TXDONE;0 STATE; auto-exit; physical actions remain unknown.

VERIFIED new mechanism: installed xemu0.8.136 copies queued OUT into its shared OHCI buffer BEFORE rejecting it for another outstanding asynchronous TD. A completed IN awaiting retirement can therefore be overwritten upstream of the correct guest callback. The verbatim source-function fixture reproduced BOTH exact pad-run-2 command-prefix RXs; changing visit order or a test-only early busy guard preserved the original03 status. Installed AppImage machine-code ordering was independently pinned. Separate limitation: one pending async transfer per controller can delay startup OUT behind IN. Strong inference for the historical echoes, not a live bus trace and not proof of the cause of latest absent buttons. Guest callback/URB/buffer crossing remains falsified.

Xbox lifecycle review also finds no AddComplete call in the custom chain; stock Attach does not call it automatically. This leaves enumeration completion unfinished, but is not established as an existing-transfer/button gate. No production/emulator fix applied. Next: ONE host-USB/OHCI trace of the unchanged candidate, exact commands/falsifier in NEXT-TEST.md, rather than another uninstrumented status timer. Scheduling observation needs no human input; button acceptance still requires current readiness and confirmed actions. No emulator/desktop launched, runtimeowner none, cleanup complete, hostxpad attached. Parent reviews/release implementation; no global settings changed.

## Astra host-boundary continuation — 2026-11-24

openai-codex/gpt-6-astra completed the ONE instrumented non-human observation; no resets/rebuild/patch. Evidence: work/astra-diagnosis/HOST-TRACE.md and host-trace/{capture.log,analysis.json,guest-latest.log,trace-preflight.json}. Trace backend passed stock-polling qualification before title. Actual physical dev3:4 EP2 OUT5 and OUT19 both reached libusb and completed status0/full length: “OUT never reaches pad” falsified for this run. Queued OUTs were rejected1049/236 times while IN64 remained outstanding, then submitted after IN retirement. BOTH mixed05 prefixes occurred live in the predicted completed-IN / queued-OUT overwrite ordering and matching correct guest IN callbacks. Trace has ordering but no per-event timestamps; no millisecond latency claim. Guest13RX/2TXDONE/0STATE, autoexit60s; no human action requested, buttons/Halo2 remain unproved. Parent makes implementation decision; observation allowance consumed.

Frozen main/header/XBE and installed guest XBE unchanged; final trace6981005 bytes, SHA276944c49c972816592e867a537625936f1268281fcbe83a9090ee883f84dcbf. QMPquit/native exit verified, runtimeowner none, xpad reattached, TOML restored58ea136fbe73a09928363d69d769eac96288b451f96a2f3534d305c25ea44841. CLEANUP BLOCKER: tool approval gate denied `systemctl --user stop hermes-xbox-desktop.service`; owned private desktop remains active. Parent must complete that exact cleanup through approved execution. No bypass attempted. status.json explicitly blocked_cleanup, diagnosis/host_observation done.
