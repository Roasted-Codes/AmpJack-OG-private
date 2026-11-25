# OGX-Mini-2026 source assessment for AmpJack-OG

Scope: owner's specific read-only request to clone https://github.com/MegaCadeDev/OGX-Mini-2026 and determine whether it helps communicate with the Xbox/kernel and support the modern pad. Implementation remains held for the requested Fable audit; no builds, emulator runs, console accesses, firmware changes, or AmpJack production edits performed in this assessment.

Contract: DONE = identify actual source paths for modern-pad startup/read loop and OG Xbox-facing behavior, distinguish on-adapter firmware from Xbox-resident APIs, preserve reproducible citations and avoid claiming a working fix from a code read. Bounded inspection: README + the specific host/device/descriptor files listed below; no recursive submodule fetch or scripts executed.

## Pinned source

VERIFIED: cloned successfully into `ogxbox/work/ogx-mini-reference/repo` using `git clone --depth 1`. HEAD `8818dc99d62bbb49c3068520f6713984c5fc11a2`.
All source links below use this immutable revision. Prefix:
https://github.com/MegaCadeDev/OGX-Mini-2026/blob/8818dc99d62bbb49c3068520f6713984c5fc11a2/

## Verdict

Useful for both ends of the controller conversation, but NOT a drop-in Xbox kernel driver or a kernel-call reference. The code runs on an RP2040/RP2350 adapter: it reads a modern pad on one USB connection and impersonates an original Xbox pad on the other. This is compatible prior art for wire behavior, not permission to replace the owner's no-active-adapter goal with an adapter design.

VERIFIED in source, NOT independently reproduced firmware behavior:

1. Particularly relevant exact-controller symptom: `Firmware/RP2040/src/USBHost/HostDriver/XInput/XboxOne.cpp:20-43` explicitly names Series X `045E:0B12`. Its comment describes earlier initialization that could change LED/rumble yet left Guide dark and produced no input. The current code schedules `start_xboxone` 50ms after initialization. This is closely related evidence, NOT proof our identical symptom has the same cause.

2. Startup order: `.../tuh_xinput/tuh_xinput.cpp:807-857` for ordinary One/Series pads arms the input read, services host frames, calls `xboxone_init`, services frames again. `:213-245` sends POWER_ON once then waits for output completion, sends S_INIT then waits again. Extra input initialization is conditional on `045e:0b00` (`:247-251`), NOT every Series controller. No blind IDENTIFY is sent first by this normal path.

3. Exact startup commands: `.../tuh_xinput/tuh_xinput_cmd.h:12-58` defines POWER_ON, S_INIT, LED, IDENTIFY, virtual-key ACK and rumble. POWER_ON is `05 20 seq 01 00`; S_INIT is 19 bytes with `55 53` in its payload. These are reference bytes; actual bus delivery from our Xbox-resident driver remains unproved by this source read.

4. Continuous listening: `.../tuh_xinput/tuh_xinput.cpp:663-690` uses a full endpoint-sized read (64 for ordinary One/Series), claims the input endpoint and releases on submission failure. `:530-587` handles input, Guide ACK and announce, rearms for non-input traffic, and separates output completion. `XboxOne.cpp:124-201` rearms after actual input/Guide processing too. These paths are concrete comparison points for our listening-stops failure, not Xbox URB layouts.

5. What the Xbox expects from a pad: `Firmware/RP2040/src/Descriptors/XboxOG.h:93-175` declares OG controller USB and XID descriptors/capabilities. `.../USBDevice/DeviceDriver/XboxOG/tud_xid/tud_xid.cpp:286-367,482-509` responds to Xbox requests for reports, XID descriptor and capabilities. `.../XboxOG_GP.cpp:26-120` translates buttons and sticks toward the OG report and synthesizes BIOS button combinations for IGR/shutdown. These are controller-to-console USB messages, NOT XBDM commands or kernel function calls.

## Practical implications for the paused plan (INFERENCE)

- Compare intended startup bytes/order and continuous input rearming against these explicit ordinary-Series paths rather than deriving them only from generic GIP docs or another adapter family.
- Use this source to validate both modern input decoding and classic report presentation.
- Do NOT copy TinyUSB calls into xapilib; they are different USB stacks. Need original-Xbox SubmitRequest/URB ABI evidence and a real bus/runtime observation to bridge them.
- Do NOT treat the source's issue comments as a reproduced fix in our application. The source identifies a useful hypothesis, not the cause of our missing buttons.
- It does not eliminate the need for the Fable audit, prove the current handshake reached the pad, or establish in-Halo control. No implementation resumed.

## Owner-facing summary

Yes. Downloaded and read the controller code. It shows how to wake One/Series pads, keep receiving buttons, and speak the original Xbox controller language. It even documents a closely related no-input problem with the owner's exact model. It runs on an adapter rather than inside the Xbox, so its useful protocol lessons must be adapted, not installed as a kernel driver.
