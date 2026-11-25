# Parent review — USB transfer ABI round

Worker09 corrected a real earlier error: Xbox interrupt DATA submission uses function 0x41. The Windows-like 0x09 label in worker07 is wrong; 0x09 creates an endpoint/TD pool. Source byte verifiers independently re-run by parent.

Parent integration RED (saved work/09-urb/parent-abi-red.log):
- Including both report headers redeclared XB_URB_BULK_OR_INTERRUPT with different values.
- Completion typedef lost i386 __stdcall in the newer header.
- Close-endpoint C struct allocated 20 bytes but declared a 28-byte URB length; default-close code accesses +0x18 beyond that short struct.

Parent GREEN:
- One canonical data code 0x41 shared by both headers.
- Shared real i386 stdcall completion typedef.
- Close struct includes reserved tail storage for the full 0x1C request extent; no semantic claim made about unknown bytes.
- parent_abi_consistency.cxx includes BOTH headers and asserts i386 type/calling convention, complete struct spans and offsets. Parent executed native + -m32 syntax checks and old individual check suites, all GREEN; verify_urb.py byte verifier re-run PASS.

Remaining unknowns aren't erased by these fixes: per-transfer flag semantics, actual GIP class-ID construction / non-hub composite dispatch on physical Xbox, attach-vtable call requirements, unplug/cancellation ordering. Completion context evidence says DPC; parser allocation and file I/O must not happen inside it.

A bounded follow-up is building the physical-measurement diagnostic (proc_77888da2628f). It must be a normal launchable title or an explicitly disabled diagnostic payload, NOT BIOS flashing. No claim that this makes the actual USB driver ready.
