# AmpJack OG - Halo 2 u803 XInput hook trampolines (i386, gas AT&T).
#
# Runtime detour stubs for the six sites in hook_sites.h. The loader writes
# `E9 rel32` over each site's first 5 bytes; that jumps here with the ORIGINAL
# entry state (stdcall args on the stack, frame not yet built).
#
# Two paths per stub:
#   disabled (ampjack_enable_flag != 0 is FALSE): re-run the displaced bytes
#     verbatim, then `jmp *resume` (absolute VA held in a fixup slot) so the
#     original function body continues and returns normally.
#   enabled: serve the virtual Xbox-One port and `ret $N` directly.
#
# Disabled-by-default: flag starts 0, so the game sees the unmodified XID
# driver ("no controller") until the loader + adapter are actually wired up.
#
# Build proof (host only):  gcc -m32 -c hook_payload.S -o hook_payload.o
# Addresses in the fixup slots are patched to final VAs by the loader.

    .code32
    .text

    .extern ampjack_enable_flag        # uint8
    .extern ampjack_port_states        # og_xinput_state_t[4] (adapter pre-mapped)
    .extern ampjack_port_connected     # uint8[4]
    .extern ampjack_virtual_handles    # 4 x 4-byte descriptors

AMPJACK_MAGIC_RET_INVALID = 0x57      # ERROR_INVALID_PARAMETER
AMPJACK_MAGIC_RET_NOCONN  = 0x48F     # ERROR_DEVICE_NOT_CONNECTED

# Displaced-bytes helpers: each .macroless inline sequence mirrors hook_sites.h.

# --------------------------------------------------------------------------
# XGetDeviceChanges(DeviceType,&insertions,&removals) -> BOOL, ret 12
# displaced: 55 8B EC 56 8B 75 08  (push ebp; mov ebp,esp; push esi; mov esi,[ebp+8])
# --------------------------------------------------------------------------
    .globl ampjack_stub_getdevicechanges
    .type  ampjack_stub_getdevicechanges,@function
ampjack_stub_getdevicechanges:
    cmpb    $0, ampjack_enable_flag
    jne     .Lgdc_virtual
    pushl   %ebp
    movl    %esp, %ebp
    pushl   %esi
    movl    8(%ebp), %esi
    jmp     *ampjack_resume_getdevicechanges
.Lgdc_virtual:
    movl    8(%esp), %edx          # &insertions
    movl    12(%esp), %eax         # &removals
    movl    $0x00000001, (%edx)    # insertions = bit0 (virtual port 0)
    movl    $0, (%eax)
    movl    $1, %eax               # TRUE
    ret     $12
    .size ampjack_stub_getdevicechanges, .-ampjack_stub_getdevicechanges

# --------------------------------------------------------------------------
# XInputOpen(DeviceType,port,slot,&poll) -> HANDLE, ret 16
# displaced: 55 8B EC 51 8B 4D 08
# --------------------------------------------------------------------------
    .globl ampjack_stub_inputopen
    .type  ampjack_stub_inputopen,@function
ampjack_stub_inputopen:
    cmpb    $0, ampjack_enable_flag
    jne     .Lopen_virtual
    pushl   %ebp
    movl    %esp, %ebp
    pushl   %ecx
    movl    8(%ebp), %ecx
    jmp     *ampjack_resume_inputopen
.Lopen_virtual:
    movl    8(%esp), %ecx          # port
    cmpl    $3, %ecx
    ja      .Lopen_none
    leal    ampjack_virtual_handles, %eax
    leal    (%eax,%ecx,4), %eax    # &ampjack_virtual_handles[port]
    ret     $16
.Lopen_none:
    xorl    %eax, %eax             # NULL handle (honest no-device)
    ret     $16
    .size ampjack_stub_inputopen, .-ampjack_stub_inputopen

# --------------------------------------------------------------------------
# XInputClose(handle), ret 4
# displaced: 8B 4C 24 04 E8 CD 0E 00 00 (mov ecx,[esp+4]; call XID_fCloseDevice)
# --------------------------------------------------------------------------
    .globl ampjack_stub_inputclose
    .type  ampjack_stub_inputclose,@function
ampjack_stub_inputclose:
    cmpb    $0, ampjack_enable_flag
    jne     .Lclose_virtual
    movl    4(%esp), %ecx
    call    *ampjack_close_fclose_dev   # XID_fCloseDevice(ecx)
    ret     $4
.Lclose_virtual:
    ret     $4                          # synthetic handle: nothing to free
    .size ampjack_stub_inputclose, .-ampjack_stub_inputclose

# --------------------------------------------------------------------------
# XInputGetCapabilities(handle,&caps) -> DWORD, ret 8
# displaced: 55 8B EC 83 EC 48 (push ebp; mov ebp,esp; sub esp,0x48)
# --------------------------------------------------------------------------
    .globl ampjack_stub_getcaps
    .type  ampjack_stub_getcaps,@function
ampjack_stub_getcaps:
    cmpb    $0, ampjack_enable_flag
    jne     .Lcaps_virtual
    pushl   %ebp
    movl    %esp, %ebp
    subl    $0x48, %esp
    jmp     *ampjack_resume_getcaps
.Lcaps_virtual:
    movl    8(%esp), %edx          # &caps
    xorl    %eax, %eax
    movb    $1, (%edx)             # SubType = XINPUT_DEVSUBTYPE_GC_GAMEPAD
    movw    %ax, 1(%edx)           # Reserved = 0
    movw    $0xFFFF, 22(%edx)      # Rumble.wLeftMotorSpeed  (offsets 21..22)
    movw    $0xFFFF, 24(%edx)      # Rumble.wRightMotorSpeed (offsets 23..24)
    xorl    %eax, %eax
    ret     $8
    .size ampjack_stub_getcaps, .-ampjack_stub_getcaps

# --------------------------------------------------------------------------
# XInputGetState(handle,&state) -> DWORD, ret 8
# displaced: 53 56 33 DB FF 15 00 B7 41 00
#   (push ebx; push esi; xor ebx,ebx; call dword ptr [0x41b700])
# --------------------------------------------------------------------------
    .globl ampjack_stub_getstate
    .type  ampjack_stub_getstate,@function
ampjack_stub_getstate:
    cmpb    $0, ampjack_enable_flag
    jne     .Lstate_virtual
    pushl   %ebx
    pushl   %esi
    xorl    %ebx, %ebx
    call    *ampjack_state_lock_dfptr # `call dword ptr [0x41b700]`
    jmp     *ampjack_resume_getstate
.Lstate_virtual:
    movl    4(%esp), %eax          # handle
    movl    8(%esp), %edx          # &XINPUT_STATE
    pushl   %esi
    pushl   %edi
    xorl    %ecx, %ecx
.Lstate_find:
    leal    ampjack_virtual_handles, %esi
    cmpl    (%esi,%ecx,4), %eax
    je      .Lstate_haveport
    incl    %ecx
    cmpl    $4, %ecx
    jb      .Lstate_find
    popl    %edi
    popl    %esi
    movl    $AMPJACK_MAGIC_RET_INVALID, %eax   # unknown handle
    ret     $8
.Lstate_haveport:
    # check connected[port]
    leal    ampjack_port_connected, %esi
    cmpb    $0, (%esi,%ecx,1)
    je      .Lstate_noconn
    # copy the 22-byte og_xinput_state_t (dwPacketNumber + 18-byte gamepad)
    # from ampjack_port_states[port] into the game's pState.
    leal    ampjack_port_states, %esi
    imull   $22, %ecx, %edi        # port stride = sizeof(og_xinput_state_t)=22
    addl    %edi, %esi             # &ampjack_port_states[port]
    movl    %edx, %edi             # &pState (arg2, saved in %edx above)
    movl    $5, %ecx               # 5 dwords = 20 bytes
    cld
    rep movsl
    movsw                          # +2 bytes = 22 total
    popl    %edi
    popl    %esi
    xorl    %eax, %eax             # XINPUT_ERR_SUCCESS
    ret     $8
.Lstate_noconn:
    popl    %edi
    popl    %esi
    movl    $AMPJACK_MAGIC_RET_NOCONN, %eax
    ret     $8
    .size ampjack_stub_getstate, .-ampjack_stub_getstate

# --------------------------------------------------------------------------
# XInputSetState(handle,&feedback) -> DWORD, ret 8
# displaced: 8B 4C 24 04 8D 81 A3 00 00 00 (mov ecx,[esp+4]; lea eax,[ecx+0xa3])
# --------------------------------------------------------------------------
    .globl ampjack_stub_setstate
    .type  ampjack_stub_setstate,@function
ampjack_stub_setstate:
    cmpb    $0, ampjack_enable_flag
    jne     .Lset_virtual
    movl    4(%esp), %ecx
    leal    0xa3(%ecx), %eax
    jmp     *ampjack_resume_setstate
.Lset_virtual:
    # Rumble is out of milestone scope: accept and drop (return success).
    xorl    %eax, %eax
    ret     $8
    .size ampjack_stub_setstate, .-ampjack_stub_setstate

# --------------------------------------------------------------------------
# Fixup slots: loader fills these with the absolute resume VAs / function ptrs.
# --------------------------------------------------------------------------
    .globl ampjack_resume_getdevicechanges
    .globl ampjack_resume_inputopen
    .globl ampjack_close_fclose_dev
    .globl ampjack_resume_getcaps
    .globl ampjack_state_lock_dfptr
    .globl ampjack_resume_getstate
    .globl ampjack_resume_setstate

    .section .data.ampjack_fixups,"aw",@progbits
    .align 4
ampjack_resume_getdevicechanges: .long 0x004139AC   # resume = 0x4139A5+7
ampjack_resume_inputopen:        .long 0x00413A19   # 0x413A12+7
ampjack_close_fclose_dev:        .long 0x0041493E   # XID_fCloseDevice
ampjack_resume_getcaps:          .long 0x00413A7A   # 0x413A74+6
ampjack_state_lock_dfptr:        .long 0x0041B700   # call dword ptr [0x41b700]
ampjack_resume_getstate:         .long 0x00413C56   # 0x413C4C+10
ampjack_resume_setstate:         .long 0x00413CC9   # 0x413CBF+10

    .section .note.GNU-stack,"",@progbits
