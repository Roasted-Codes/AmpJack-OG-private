> Historical checkpoint: current selected build/status and scope are in [OG compatibility](../docs/OG-COMPATIBILITY.md) and [the root README](../README.md). Do not treat this older document as the current release contract.

# AmpJack-OG — canonical functionality plan

Author/reviewer: openai-codex / gpt-6.1-sol. Owner instruction: Sol plans/reviews and oversees DeepSeek implementers; no global routing change. This file is the sole execution plan. PROJECT_STATE.md is the compact checkpoint, not another queue. Evidence: work/sol-audit/AUDIT.md, input-hashes.json and evidence-summary.json. Historical MISSION.md and worker briefs/reports are retained; their missing-hardware restriction, Fable-only hold and unsupported root-cause claims are superseded here.

## Outcome and proof boundary

The owner's wired045e:0b12 Series controller directly controls Halo2 on his ORIGINAL Xbox using a passive cable. No external PC, microcontroller, active adapter or network translator in the final operating path. Development PC+xemu with the real USB controller passed through is authorized as a testbed, not a replacement product. Required: buttons, triggers and sticks. Not doing now: audio/headset, wireless, rumble, Guide IGR/shutdown, other games, BIOS flashing, another USB framework or a pipeline/controller service.

Real standalone input is now verified for a positive subset: frozen ae9899098a5dd83312460cc8e004d3bc5fbd2f84fbe0b849aab7fcefb516b6cb, under isolated repaired emulator cb72610807d242f1b13eebace7f7049f8e57b9ee7e84b1799a6d77fc8b5f865c, decoded owner-confirmed A/B/X/Y press/release, all four stick axes in both directions, and both triggers 0/full/release. Evidence: work/20-runtime/{button-run.log,VERIFIED-INPUT.json,button-result.json}. Partial trigger levels and remaining buttons are not physically checked. Halo2 and original-console gameplay remain unproved. The emulator defect and its guard/setup gate are resolved for this testbench; do not reinstate old missing-input or permission blockers.

## Working contract

One Sol parent reviews artifacts and makes stage transitions. Current bounded writer: DeepSeek24, work/briefs/24-halo2-input.md, implementing the first loadable Halo2 input module offline in integration/ + work/24-halo2-input/ only;100 API turns/75active minutes/one batch. No runtime or human-contact authority. Side-task25 only investigates the supported live chat-mode update; it cannot restart services or alter game work. Standalone real control subset and three physical held-A disconnect/reconnect cycles are observed and accepted at that scope. Earlier worker17/21/22 attempts and counters remain historical, not reset; old missing-input/cleanup/monitor blockers are superseded. Source/gameplay correctness, live Halo2 control and original-console deployment remain separate gates. Parent reviews before any game run and reports meaningful current work.

Parent retains physical-owner communication and gives brief15-minute NBA-themed updates only while work is actually active. No quarter/finish claims without evidence or duration promises. No file-poll rendezvous. If the tool cannot return a supported live notification, complete the setup handoff at the launcher before starting the timed title; parent then explicitly owns the live run. No worker edits source while someone else owns that runtime test.

## Common evidence/acceptance rules

- Bind each run to source hashes, compiler/build command/log, pin-verifier result, host XBE SHA256 and installed guest SHA256. Capture run-specific log boundaries; existing logs append. Reject source/artifact mismatch or unknown guest identity. Record exact build identity per platform; console adaptation creates a new candidate needing emulator retest.
- A synthetic positive path is a unit test. A QMP device-add is installation/connection. A callback is a completion event. A real raw0x20 report correlated with a physical action is input evidence. A successful Halo action is integration evidence. These are different gates.
- True URB completion status is header+4; actual accumulated byte length is DWORD+14 before rearm; WORD+20 preserves the mapped request length; DWORD+24 is linkage. Audit independently traced those fields into the linked XBE. Recheck if library/candidate changes. No 'status0 means sent' claim from old +24 logs.
- Always request bounded endpoint-size IN reads and keep IN/OUT storage separate; parse/map/log outside DPC. Handle sync rejection, delayed/synchronous callback and pending distinctly. Preserve request IDs, timestamps, raw bytes and requested/completed lengths. Never mark input-valid just because init was queued.
- Data endpoints come from a freshly fetched descriptor. For this exact pad require IF0 alt0 EP82/02 interrupt64 interval4 cfg1; regression must read research/usb/real-pad/config-descriptor-0b12.bin. No EP1 assumption or audio alt selection.
- Capture is supporting evidence, not an extra research branch. Prefer existing unprivileged QEMU/libusb tracing in the same candidate run. usbmon was not available in this audit's read-only probes; no module load, elevated capture, package/udev/host change without its own authorized scope. A trace of a submission is not bus completion. If accessible, a working Linux/xpad trace gives a positive comparison; do not replace the native-Xbox goal with Linux controls.
- Parent confirmation must name which pad and which press window. Expected physical actions: neutral; A press/release; other buttons individually; each trigger neutral→partial→full→neutral; both sticks along positive/negative X/Y then neutral. Match raw input plus all decoded fields. Missing owner confirmation makes that action trial inconclusive, not a controller diagnosis.
- Prevent SDL/native-pad false positives: record usb-host path1.2.1 and host usbfs ownership; leave native keyboard/stock pad idle during modern-pad action proof. Native coexistence is separately tested. Green/cyan screen alone is never acceptance.
- Preserve evidence on failure. Real-console and destructive host actions are not part of the next task. No git commits/pushes/history changes, firmware, networking, credentials, global routing, or unrelated project edits.

## Slice1 — real standalone controls (NOW, size M)

Description: retain the existing title-local class hook and explicit completion-driven config/open chain. Correct only demonstrated transport-field/direction/rearm errors and the qualified wired no-identify decoder gate; obtain the first trustworthy physical button/trigger/stick sample in xemu. Next brief owns this slice; do not port the full core or install Halo hooks first.

Dependencies: none beyond parent review of this audit, tool capability, actual pad present and parent available for physical action. Hardware and passthrough permission already exist; no owner re-interview/model approval.

Files: next worker writes only ogxbox/gipdriver/ and ogxbox/work/17-sol-execution/. Parent owns PLAN.md, PROJECT_STATE.md and accepted conclusions. Prior work/tests/reference/core/research modules are read-only dependencies; new regressions live in work17.

Acceptance:
- [ ] INSTALL/STARTUP: clean rebuild of the actual candidate, regenerated pins verified against that final build; saved SHA256 matches installed E:\AmpJack-OG\gip\default.xbe; no-pad armed/PINFAIL safety control terminates normally without device submissions through null state. No old bin presented as new source.
- [ ] FUNCTION/PLATFORM: actual real-pad passthrough produces genuine successful0x20 input; same main-loop consumer records confirmed A down/up, both triggers with intermediate/full/release and all four stick axes in both directions/neutral. Log A/B/X/Y/bumper analog bytes too; no synthetic identify prerequisite. First positive subset is reported as partial, not all controls. Completion of all immediate buttons remains a checklist before slice3.
- [ ] RESOURCE/EXIT: no log-ring corruption, silently lost queues or submit storm in the bounded run; errors surface via real header status; driver returns to launcher by its documented watchdog, and xpad ownership/toml are restored after runtime ends. This is bounded liveness, NOT unplug/cancel proof.

Executable verification:
1. From repo root, run existing11/14/15 suites with outputs redirected to work17 (commands in brief); run new17 regressions against the SAME gipdrive.h, including no-announce normal input and the real binary config fixture. Do not use fake_in_complete to test the real callback.
2. In gipdriver: make -B, regenerate pinned_findclass.h after reviewing deterministic layout changes, rebuild, then python3 ../work/11-gipdriver/gen_pinned_findclass.py --verify. Save complete final logs, sha256sum bin/default.xbe src/*.c src/*.h, and executable disassembly where field/ABI assumptions changed.
3. Build an offline transfer DVD with python3 ogxbox/work/15-handshake/xemu-pad-2/mkxiso.py ogxbox/gipdriver/bin/default.xbe ogxbox/work/17-sol-execution/gip.iso. Use the proven virtual-DVD transfer and current xemu skill, not network changes. Verify guest file identity with the already-used offline FATX read tool only when xemu is stopped; never mount/write a live HDD.
4. Use the QMP hot-add commands and launch/press sequence in brief. Save host transfer observations, guest run log, expected/observed physical transitions, screenshot/title exit and restored-state evidence. Parent independently verifies the actual outputs before marking accepted.

Attempt/stop: two code batches and the shared experiment budget above. If corrected transport still produces no input, do not add more init guesses. Return exact OUT/IN actual-versus-intended comparison, status snapshots and the smallest missing capture capability. If real input reaches bus but not decoder, fix that demonstrated consumer boundary within remaining budget, not transport again. Do not physically unplug before slice2.

## Slice2 — sustained reads, unplug and cleanup (NEXT, size M)

Description: make the demonstrated standalone path safe to keep using, disconnect and reattach. Retain the same transport design; derive remove/close/AddComplete lifecycle from actual xapilib consumers, not a guessed extended descriptor. Reuse ogxbox/gip's tested reset/no-stale-state semantics where feasible, with one main-loop owner and bounded allocation if full core is linked.

Dependencies: slice1 real input evidence. No Halo installer yet. Assign one DeepSeek worker to gipdriver and a fresh bounded work directory; parent owns status. It may read reference/research/core, not rewrite them without a separately explicit file assignment.

Acceptance:
- [ ] FUNCTION: five-minute standalone run with periodic confirmed controls; three unplug/replug cycles with held-button unplug, immediate logical neutral/disconnected state, successful reinit and no stale input. Native pad still exits. Run cancellation only after remove notification and endpoint-close ordering are proven in code/host tests.
- [ ] INSTALL/LIFECYCLE: cancel/stop prevents new submissions; close IN, OUT and control with completed/quiescent callbacks; disconnect does not reuse live context; restore hook only after quiescence or keep title-lifetime ownership explicitly. Normal exit, no-pad exit, failed-init exit and relaunch all return to a known launcher state.
- [ ] RESOURCE/PLATFORM: log endpoint/allocation/queue counters before/after each cycle; no increasing live handles/buffers, DPC file I/O, callback-after-retirement or repeated submits after detach. Record measured sampling/consumer intervals; current250ms polling is a diagnostic cadence, not claimed Halo-quality responsiveness. No crashes/pauses during sustained xemu run.

Verification: run existing and new real-callback failure/delayed-completion/queue-preemption tests; install hashed candidate using slice1 recipe; repeat full physical input checklist plus five-minute/three-cycle lifecycle script with timestamps and final readback. Parent checks logs against actual operations. Budget: at most two implementation batches and three runtime sessions; if no new boundary evidence in two batches, stop that approach. Counter growth, hang, cancellation uncertainty or stale-input reproduction blocks slice3 and real-console testing.

## Slice3 — control Halo2 in emulator (L; implement as one narrow vertical path)

Description: connect the already-demonstrated transport to ogxbox/gip's hardened main-loop snapshot and existing integration presentation, then install the already-pinned Halo2 hook plan via the existing loader route. No third parser, new general plugin framework or adapter. Do not copy worker03's superseded scratch hook payload.

Dependencies: slice2 accepted lifecycle candidate; exact Halo u803 build identity/permissions checked from existing project evidence. Each later worker has disjoint ownership: transport owner gipdriver; integration/installer owner integration plus the necessary existing loader files, in sequential non-overlapping runtime sessions. Sol must issue a precise file list before those edits. Audit does not authorize touching LAN_Stats or other projects for a loader.

Acceptance:
- [ ] INSTALL/STARTUP: exact-build SHA gate and all six detour bytes checked before any patch; fail closed on mismatch. Loadable candidate from the existing dashboard/trainer path, disabled candidate chains original input, no unresolved relocations/TEXTREL. Runtime installer is real, not detour_plan.py described as an installer.
- [ ] FUNCTION/PLATFORM: through actual usb-host pad, Halo menus navigate/select/back; a local match demonstrates movement, both look axes, fire and analog trigger release/partial/full, jump/crouch/reload/use, grenade/melee/weapon controls and Start/Back. Record mapping including LB/RB→Black/White; reference adapter's opposite mapping is not authority. Native pad coexists without stolen ports; disconnect/reconnect/level transitions return correct insertion/removal and stale-handle errors. No SDL-native alias used as the proof.
- [ ] RESOURCE: no callback/lifetime failure, title pool growth or unintended native-handle interception; controller state remains responsive in gameplay with measured update intervals. Exercise finite16-handle arena exhaustion and document its fail-closed behavior or fix only if real normal play exhausts it. Do not advertise unlimited hotplug. Audio/rumble caps must not promise support.

Verification: existing gip hardening, integration GCC/Clang/sanitizer suites, six-site verify and PIC relocation checks (commands documented in module READMEs), followed by a hashed installed candidate and the actual local-Halo action/lifecycle test with logs/video or action screenshots. Capture source/installed module identity as well as the unchanged title hash. Budget: two code batches, three runtime sessions; stop at first native-input regression, build mismatch or repeated no-new-evidence batch. Host tests alone cannot close this slice.

Checkpoint after slice2 and slice3: parent reviews evidence, updates PROJECT_STATE and only then assigns the next file/runtime owner. Checkpoints do not trigger another general planning audit.

## Slice4 — original Xbox controls (FINAL PLATFORM GATE)

Description: same emulator-qualified candidate, original controller/passive cable and Xbox. Development PC can transfer/pull evidence, but must not translate input; disconnect that dependency for the functional proof. Owner's console permission exists; current instruction still forbids console activity until the SAME candidate passed full emulator lifecycle. If console environment requires any candidate change, return it through emulator gates first.

Dependencies: slices1-3 accepted, install/recovery files and native-pad/manual exit available, parent owns console session and owner physical contact. Worker may prepare console-readiness artifacts only in its assigned project work directory; console execution remains parent-owned, not implicit worker authority.

Acceptance:
- [ ] INSTALL/RECOVERY: verify exact installed candidate/title identities, passive connection and title-local installation without flashing. Known dashboard recovery and exit proven; no claim that XBMC preserves XBDM in a standalone title. If network disappears use saved logs/observable title/exit state; do not infer crash from connectivity alone.
- [ ] FUNCTION/PLATFORM: real original Xbox Halo2 repeats slice3's complete menu+local-match action checklist with buttons, sticks and triggers; PC/active adapter is not in the controller path. Repeat unplug/replug and normal exit/relaunch only after their emulator gates. Confirm mapping and sustained play with the owner.
- [ ] RESOURCE: no console hang, stale controls, increasing handle/allocation counts or native-pad regression through the tested lifecycle. State measured limitations honestly; emulator acceptance is never console proof.

Verification: parent records console identity, candidate/title SHA readback, physical topology, confirmed actions, runtime logs and recovery outcome. Initial budget: one controlled console session; stop immediately on hang, unsafe teardown or identity mismatch. A new console power-cycle is owner-handled with explicit notice, not an automatic worker recovery loop. Final DONE only after this gate; otherwise report highest verified slice and exact remaining boundary.

## Restart and release rule

Read the CURRENT section of PROJECT_STATE.md and work/sol-audit/COORDINATOR_STATE.json, then the specifically active brief (now work/briefs/24-halo2-input.md). Recheck git/process ownership and matching source hashes before acting. Parent has accepted the original audit and standalone positive input subset and explicitly released slice2; do not resurrect worker17's initial release gate, missing-input claims, exhausted retries or resolved monitor/cleanup blockers. On interruption preserve candidate/source hashes, real tests, last transfer/status, exact runtime owner and one next actionable step. No competing tracker, automatic duplicate worker or routing change.
