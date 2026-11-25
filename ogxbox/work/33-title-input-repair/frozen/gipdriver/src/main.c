/*
 * main.c — AmpJack-OG worker 16: GIP class-driver transport proof (v4).
 *
 * Runs the title-linked USBD (xapilib.lib) on the real console, REGISTERS a
 * class driver for the Xbox One pad's GIP interface (PNP_CLASS_ID 0xFF81) by
 * hooking FindClassDriver, opens the interrupt IN and OUT endpoints, submits
 * a persistent interrupt IN URB, drives the wired GIP handshake (power-on
 * FIRST at open, then S-init, LED, rumble-off; identify only on announce;
 * ack on needs-ack) over a dedicated OUT queue with its own CompleteProc,
 * logs raw packets + decoded GIP state to E:\AmpJack-OG\gip-probe.log, and
 * auto-exits after 60 s.
 *
 * v4 fixes the bugs the second real-pad xemu run (work/15-handshake/xemu-pad-2)
 * exposed:
 *   1. OUT latency: the OUT URB copied the IN URB's FlagB0/FlagB1 (2,1). The
 *      stock XID interrupt-OUT URB uses 1,0 (Direction stays 0) — mis-flagged
 *      OUT transfers only completed when the interrupt-IN DPC swept the list.
 *   2. IN stop: gip_in_complete never reset TransferLength before re-submitting,
 *      so the HCD's short-length completion clobbered it and the re-armed URB
 *      read fewer bytes and stalled. gdr_in_complete now ALWAYS resets
 *      TransferLength to mps_in (64) and logs the true ByteCount (+0x20).
 *   3. Handshake order: power-on is sent FIRST (xpad open order); IDENTIFY is
 *      no longer sent blind — only in reply to an announce (02 20).
 *   4. A per-second LIVE in_flight=0/1 tx_q=N rx=N tx=N line so the next run
 *      shows whether the IN URB is still pending (HEARTBEAT is 30 s now).
 *
 * Completion callbacks are DPC-safe (ring push + re-submit only; no file I/O).
 * Main loop: ring drain -> format events -> feed RX to the GIP state machine ->
 * bridge state-machine TX into the OUT queue -> submit next OUT.
 *
 * Colour screen: yellow=armed, cyan=attached, green=decoded input.
 * BACK+START on a stock pad exits, or auto-exit at 60 s.
 */

#include <xtl.h>
#include <string.h>
#include "gipdrive.h"
#include "pinned_findclass.h"

static const char kLogPath[] = "E:\\AmpJack-OG\\gip-probe.log";
static const char kLogDir [] = "E:\\AmpJack-OG";
static const char kLogPathD[] = "D:\\gip-probe.log";

/* ---- private USBD call surface (lld-link /alternatename, matched to the
 *      diagnostic's pattern: __thiscall getters + __stdcall/__fastcall) ---- */

extern void * __stdcall usbd_FindClassDriver(unsigned short classId);
/* __fastcall decl for pinning/detour only; the real ABI pushes classId on the
 * stack as a 4-byte slot (see worker07). The trampoline reads it from [esp+X]. */
extern void __fastcall usbd_FindClassDriver_addr(void);
/* SubmitRequest: __thiscall (self=ECX, urb=stack). Ret LONG. */
extern long __thiscall usbd_SubmitRequest(void *self, void *urb);
/* Slice2 lifecycle methods (VERIFIED map symbols; see gipdrive.h section 5).
 *   AddComplete(status)   __thiscall, void  — IUsbDevice::AddComplete(long)
 *   CancelRequest(urb)    __thiscall, long  — IUsbDevice::CancelRequest(URB*)
 *   RemoveComplete()      __thiscall, void  — IUsbDevice::RemoveComplete(void) */
extern void __thiscall usbd_AddComplete(void *self, long status);
extern long __thiscall usbd_CancelRequest(void *self, void *urb);
extern void __thiscall usbd_RemoveComplete(void *self);

/* Force the symbols to LINK. */
static const void * const g_abi_probe[] = {
    (const void *)&usbd_FindClassDriver,
    (const void *)&usbd_SubmitRequest,
    (const void *)&usbd_AddComplete,
    (const void *)&usbd_CancelRequest,
    (const void *)&usbd_RemoveComplete,
};

/* E: mapping (copy from diagnostic, shared with diagnostic's code). */
typedef struct { unsigned short Length; unsigned short MaximumLength; char *Buffer; } GD_ANSI_STRING;
extern unsigned long __stdcall IoCreateSymbolicLink(GD_ANSI_STRING *n, GD_ANSI_STRING *t);
#define STATUS_OBJECT_NAME_COLLISION 0xC0000035u

/* ---- our class-driver description -------------------------------------- */
static void __stdcall gip_register_stub(void *iUsbInit) { (void)iUsbInit; }
static void __stdcall gip_attach(void *device);  /* fwd */

static struct gdr_class_desc g_gip_desc;   /* fields set in main(), before arm */

/* ---- GIP state --------------------------------------------------------- */
static struct gdr_ring g_ring;
static struct gdr_gip   g_gip;
static volatile u32     g_now_ms      = 0;    /* injected clock (main loop) */
static volatile u32     g_seq         = 0;    /* event seq (main-loop events) */
static volatile u32     g_input_seen  = 0;
static volatile u32     g_attached    = 0;
static u32              g_device;             /* IUsbDevice* from attach */

/* Attach state machine (worker14): completion-driven S0..S5. Reworked because
 * the stack has NOT fetched the config descriptor / sent SET_CONFIGURATION for
 * a DEVICE-level 0xFF81 class, so Attach drives GET_DESCRIPTOR(config) →
 * SET_CONFIGURATION → OPEN endpoints itself, from completions (worker13). */
static struct gdr_attach_ctx g_att;   /* single global ctx: one GIP pad for now */

/* ---- slice2 lifecycle method wrappers + remove callback ----------------- */
/* These wrap the __thiscall IUsbDevice methods behind plain function seams the
 * header's state machine injects; the host harness substitutes fakes. */
static void gip_add_complete_wrap(void *device, long status) {
    usbd_AddComplete(device, status);
}
static long gip_cancel_request_wrap(void *device, void *urb) {
    return usbd_CancelRequest(device, urb);
}
static void gip_remove_complete_wrap(void *device) {
    usbd_RemoveComplete(device);
}

/* RemoveDevice (the description's +0x0C field, __stdcall(1 device)) — invoked
 * by the tree on disconnect. Delegates to the lifecycle state machine
 * (invalidate -> cancel -> quiesce -> RemoveComplete); the main loop
 * neutralizes the decoded snapshot when it drains the DETACH event. */
static void __stdcall gip_remove(void *device) {
    gdr_remove_device(&g_att, device);
}

/* ---- log helpers (copy from diagnostic, adapted) ------------------------ */
static BOOL   g_logE = FALSE, g_logD = FALSE;
static HANDLE g_hE = (HANDLE)0xFFFFFFFF, g_hD = (HANDLE)0xFFFFFFFF;

#define LOG_LIT(s) log_write((s), GDR_LIT_LEN(s))
static void log_write(const char *s, size_t len);

static void log_map_e(void) {
    GD_ANSI_STRING link, tgt;
    link.Buffer = "\\??\\E:"; link.Length = (unsigned short)strlen(link.Buffer);
    link.MaximumLength = (unsigned short)(link.Length + 1);
    tgt.Buffer  = "\\Device\\Harddisk0\\Partition1";
    tgt.Length = (unsigned short)strlen(tgt.Buffer);
    tgt.MaximumLength = (unsigned short)(tgt.Length + 1);
    IoCreateSymbolicLink(&link, &tgt);
}
static HANDLE log_open(const char *path, const char *dir) {
    if (dir) CreateDirectory(dir, NULL);
    HANDLE h = CreateFile(path, GENERIC_WRITE, FILE_SHARE_READ, NULL,
                          OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h != (HANDLE)0xFFFFFFFF && h) { SetFilePointer(h, 0, NULL, FILE_END); return h; }
    return (HANDLE)0xFFFFFFFF;
}
static void log_start(void) {
    log_map_e();
    g_hE = log_open(kLogPath, kLogDir); g_logE = (g_hE != (HANDLE)0xFFFFFFFF);
    g_hD = log_open(kLogPathD, NULL);   g_logD = (g_hD != (HANDLE)0xFFFFFFFF);
    char line[64]; size_t n = 0;
    n = gdr_str(line,sizeof line,n,"SYNTH log=E "); n = gdr_str(line,sizeof line,n,g_logE?"ok":"fail");
    n = gdr_str(line,sizeof line,n," D ");          n = gdr_str(line,sizeof line,n,g_logD?"ok":"fail");
    n = gdr_str(line,sizeof line,n,"\n"); log_write(line,n);
}
static void log_write(const char *s, size_t len) {
    DWORD w=0;
    if (g_logE) WriteFile(g_hE,s,(DWORD)len,&w,NULL);
    if (g_logD) WriteFile(g_hD,s,(DWORD)len,&w,NULL);
}
static void log_flush(void) {
    if (g_logE) FlushFileBuffers(g_hE);
    if (g_logD) FlushFileBuffers(g_hD);
}

/* ---- completion callbacks (DPC-safe: only ring push + (re)submit) ------- */

static long gip_submit(void *device, void *urb) {
    return usbd_SubmitRequest(device, urb);
}

/* Interrupt-IN completion is the SHARED gdr_in_complete (gipdrive.h): it logs
 * RX with the true ByteCount and ALWAYS resets TransferLength + re-submits the
 * same URB. Bound below in gip_attach. */
static void __stdcall gip_in_complete(void *urb, void *ctx) {
    gdr_in_complete(urb, ctx);
}

/* ---- ATTACH (runs during XInitDevices/Process, PASSIVE context) --------- */
/*
 * Worker 14: completion-driven rewrite. 0xFF81 is a DEVICE-level class, so at
 * Attach time the stack has fetched only the device descriptor — NOT the config
 * descriptor and NOT issued SET_CONFIGURATION. Attach only opens the DEFAULT
 * CONTROL endpoint (fn 0x82) and hands off to the S0..S5 completion chain in
 * gipdrive.h — no endpoint opens here, and no handshake: the wired fallback
 * state machine drives the GIP init over the OUT queue (v3).
 */
static void __stdcall gip_attach(void *device) {
    struct gdr_evt ev; memset(&ev, 0, sizeof ev);
    ev.kind = GDR_EVT_ATTACH; ev.a = (u32)device; ev.seq = ++g_seq;
    gdr_ring_push(&g_ring, &ev);
    g_device = (u32)device;
    g_attached = 1;
    g_att.in_complete = (gdr_complete_fn)&gip_in_complete;
    g_att.cb_log = 1;   /* enable per-completion discriminator lines (CB kind=…) */
    if (gdr_attach_begin(&g_att, device, gip_submit, &g_ring)) {
        /* REFUSED: a previous generation is still quiescing (REMOVING / pending
         * URBs). Fail-closed: do NOT clobber the live context; signal
         * AddComplete(<0) for THIS device so the stack aborts its enumeration
         * instead of leaving a claimed-idle device. */
        LOG_LIT("ATTACH_REFUSED dev=0x");
        {
            char hline[16]; size_t hn = 0;
            hn = gdr_hex_u(hline, sizeof hline, hn, (u32)(u32)device, 8);
            hn = gdr_str(hline, sizeof hline, hn, "\n");
            log_write(hline, hn);
        }
        g_att.add_complete(device, (long)(int)0xC0000001L);  /* STATUS_UNSUCCESSFUL */
    }
}

/* ---- FindClassDriver Hook ---------------------------------------------- */

/* pin bits come from gipdrive.h (GDR_PIN_SHAPE/BEGIN/WRITABLE) so the host
 * harness and this title can never disagree on numbering. */

static u8  g_fc_bytes[16];      /* first 16 bytes at fc_va, read at pin time  */
static u32 g_fc_begin_v = 0;    /* live begin imm (mov eax), read at arm time */
static u32 g_fc_end_v   = 0;    /* live end   imm (mov esi), read at pin time */
static u32 g_fc_resume_v = 0;   /* entry + 6 */
static u32 g_desc_va = 0;       /* address of g_gip_desc */
static volatile int  g_armed = 0;

__declspec(naked) static void gip_fchook(void);   /* fwd (defined below) */

static int gip_pin_findclass(void) {
    u8 *t = (u8*)(u32)&usbd_FindClassDriver;
    for (int i = 0; i < 16; i++) g_fc_bytes[i] = t[i];
    unsigned int pins = gdr_pin_findclass(t, PINNED_FC_BEGIN_IMM, &g_fc_begin_v);
    g_fc_end_v = *(u32*)(t + 7);            /* mov esi, imm32 (end of table) */
    if (PINNED_FC_SECTION_WRITABLE) pins |= GDR_PIN_WRITABLE;
    return pins;
}

static int gip_arm_findclass(unsigned int pins) {
    u8 *t = (u8*)(u32)&usbd_FindClassDriver;
    if (gdr_gip_arm_gate(pins)) return 1;
    g_fc_begin_v  = *(u32*)(t + 2);         /* live begin imm */
    g_fc_resume_v = (u32)(u32)&usbd_FindClassDriver + 6;
    g_desc_va     = (u32)(u32)&g_gip_desc;
    u32 rel = (u32)(u32)&gip_fchook - ((u32)(u32)t + 5);
    u8 patch[5]; patch[0]=0xE9;
    patch[1]=(u8)(rel&0xFF); patch[2]=(u8)((rel>>8)&0xFF); patch[3]=(u8)((rel>>16)&0xFF); patch[4]=(u8)((rel>>24)&0xFF);
    memcpy(t, patch, 5);
    g_armed = 1;
    return 0;
}

__declspec(naked) static void gip_fchook(void) {
    __asm {
        pushad
        pushfd
        movzx  eax, word ptr [esp+40]   ; classId (stdcall 1 arg at [esp+40])
        cmp    eax, 0FF81h              ; GDR_PNP_GIP
        jne    fccall_through
        ; match: return our description (EAX = &g_gip_desc)
        popfd
        popad
        mov    eax, g_desc_va
        ret    4                        ; stdcall cleanup
    fccall_through:
        popfd
        popad
        push   esi                      ; re-execute displaced 'push esi'
        mov    eax, g_fc_begin_v        ; re-execute displaced 'mov eax, imm32'
        mov    ecx, g_fc_resume_v       ; resume addr in ECX (original sets ecx=eax soon after)
        jmp    ecx
    }
}

/* ---- d3d colour (mirror diagnostic) ------------------------------------ */
static Direct3D  *g_pD3D = NULL;
static D3DDevice *g_pDev = NULL;
static void video_init(void) {
    g_pD3D = Direct3DCreate8(D3D_SDK_VERSION); if (!g_pD3D) return;
    D3DPRESENT_PARAMETERS pp; memset(&pp,0,sizeof pp);
    pp.BackBufferWidth=640; pp.BackBufferHeight=480; pp.BackBufferFormat=D3DFMT_X8R8G8B8;
    pp.BackBufferCount=1; pp.SwapEffect=D3DSWAPEFFECT_DISCARD;
    pp.FullScreen_RefreshRateInHz=D3DPRESENT_RATE_DEFAULT;
    pp.FullScreen_PresentationInterval=D3DPRESENT_INTERVAL_ONE;
    if(FAILED(Direct3D_CreateDevice(0,D3DDEVTYPE_HAL,NULL,D3DCREATE_HARDWARE_VERTEXPROCESSING,&pp,&g_pDev)))
        g_pDev = NULL;
}
static void video_clear(D3DCOLOR c) {
    if(!g_pDev) return;
    D3DDevice_Clear(0,NULL,D3DCLEAR_TARGET,c,1.0f,0); D3DDevice_Swap(0);
}

/* ---- MAIN -------------------------------------------------------------- */
int main(void) {
    XDEVICE_PREALLOC_TYPE prealloc[1];
    prealloc[0].DeviceType=XDEVICE_TYPE_GAMEPAD; prealloc[0].dwPreallocCount=4;

    gdr_ring_reset(&g_ring);
    gdr_gip_init(&g_gip, 0);
    log_start();

    /* populate our class-driver description BEFORE anything resolves it */
    g_gip_desc.MatchByte0 = 0x81;   /* low byte of PNP_CLASS_ID 0xFF81 */
    g_gip_desc.MatchByte1 = 0xFF;   /* high byte                          */
    g_gip_desc.pad[0] = 0xFF; g_gip_desc.pad[1] = 0xFF;
    g_gip_desc.Register = (u32)(u32)&gip_register_stub;
    g_gip_desc.Attach   = (u32)(u32)&gip_attach;
    /* slice2: the full 24-byte description. RemoveDevice is the disconnect
     * callback the tree calls; TypeInfo/DispatchTable stay 0 (the GIP pad has
     * device class 0xFF, so AddComplete never dereferences DispatchTable). */
    g_gip_desc.RemoveDevice  = (u32)(u32)&gip_remove;
    g_gip_desc.TypeInfo      = 0;
    g_gip_desc.DispatchTable = 0;

    /* wire the lifecycle method seams BEFORE enumeration (they persist across
     * re-attach; Attach only resets the per-generation counters, not these). */
    g_att.add_complete    = gip_add_complete_wrap;
    g_att.cancel_request  = gip_cancel_request_wrap;
    g_att.remove_complete = gip_remove_complete_wrap;

    /* pin + arm FindClassDriver hook */
    unsigned int pins = gip_pin_findclass();
    void *xid_desc = usbd_FindClassDriver(0x5882);
    void *hub_desc = usbd_FindClassDriver(0x0981);
    int armcode = gip_arm_findclass(pins);

    {
        char line[256]; size_t n=0;
        n=gdr_str(line,sizeof line,n,"GIPINIT pin=0x"); n=gdr_hex_u(line,sizeof line,n,pins,8);
        n=gdr_str(line,sizeof line,n," armed=");        n=gdr_dec(line,sizeof line,n,g_armed?1:0);
        n=gdr_str(line,sizeof line,n," armcode=");       n=gdr_dec(line,sizeof line,n,armcode);
        n=gdr_str(line,sizeof line,n," fc_va=0x");      n=gdr_hex_u(line,sizeof line,n,(u32)(u32)&usbd_FindClassDriver,8);
        n=gdr_str(line,sizeof line,n," begin=0x");      n=gdr_hex_u(line,sizeof line,n,g_fc_begin_v,8);
        n=gdr_str(line,sizeof line,n," end=0x");        n=gdr_hex_u(line,sizeof line,n,g_fc_end_v,8);
        n=gdr_str(line,sizeof line,n," wr=");           n=gdr_dec(line,sizeof line,n,PINNED_FC_SECTION_WRITABLE?1:0);
        n=gdr_str(line,sizeof line,n," bytes=");
        for (int i=0;i<16;i++){ n=gdr_hex_u(line,sizeof line,n,g_fc_bytes[i],2); n=gdr_str(line,sizeof line,n," "); }
        n=gdr_str(line,sizeof line,n," xid=0x");        n=gdr_hex_u(line,sizeof line,n,(u32)(u32)xid_desc,8);
        n=gdr_str(line,sizeof line,n," hub=0x");        n=gdr_hex_u(line,sizeof line,n,(u32)(u32)hub_desc,8);
        n=gdr_str(line,sizeof line,n,"\n"); log_write(line,n);
    }
    if (armcode != 0) {
        char line[128]; size_t n=0;
        n=gdr_str(line,sizeof line,n,"PINFAIL armcode="); n=gdr_dec(line,sizeof line,n,armcode);
        n=gdr_str(line,sizeof line,n," pins=0x");          n=gdr_hex_u(line,sizeof line,n,pins,8);
        n=gdr_str(line,sizeof line,n,"\n"); log_write(line,n); log_flush();
    }

    /* enumerate (hits our hook if armed) */
    XInitDevices(1, prealloc);

    video_init();

    /* stock-pad handles for BACK+START exit */
    HANDLE pads[4]={0}; DWORD last_ins=~0u;
    DWORD bs_held=0;

    g_now_ms = 0;
    u32 rx_logged=0;
    u32 last_hb_ms=0;
    u32 last_live_ms=0;
    struct gdr_snapshot last_snap; memset(&last_snap,0,sizeof last_snap);

    u32 startup_wait=0, no_pkt_logged=0;

    for (;;) {
        DWORD ins=0, rem=0;
        XGetDeviceChanges(XDEVICE_TYPE_GAMEPAD, &ins, &rem);
        for (int port=0;port<4;port++) {
            if((rem&(1u<<port))&&pads[port]){ XInputClose(pads[port]); pads[port]=0; }
            if((ins&(1u<<port))&&!pads[port])
                pads[port]=XInputOpen(XDEVICE_TYPE_GAMEPAD,port,XDEVICE_NO_SLOT,NULL);
        }
        if (ins!=last_ins) last_ins=ins;

        /* inject clock (250 ms steps) + feed the wired state machine */
        g_now_ms += GDR_TICK_MS;
        g_att.tick = g_now_ms;   /* coarse tick for completion-event tagging */

        /* drain event ring with the safe single-producer/consumer handoff
         * (gdr_ring_pop), so a concurrent DPC push can never overwrite an
         * event the main loop is about to read (the legacy gdr_ring_drain
         * reset the producer storage before consumption). */
        {
            u32 o = gdr_ring_take_overflow(&g_ring);
            if (o) { char ln[64]; size_t n2=0;
                n2=gdr_str(ln,sizeof ln,n2,"OVERFLOW dropped="); n2=gdr_dec(ln,sizeof ln,n2,o);
                n2=gdr_str(ln,sizeof ln,n2,"\n"); log_write(ln,n2); }
            struct gdr_evt ev;
            while (gdr_ring_pop(&g_ring, &ev)) {
                int do_log = 1;
                if (ev.kind == GDR_EVT_RX) {
                    gdr_gip_rx(&g_gip, ev.data, (int)ev.len);
                    /* log raw RX hex only for the first 32 frames (input can
                     * arrive ~125/s), but always feed/parse the frame. */
                    if (rx_logged >= 32) do_log = 0; else rx_logged++;
                } else if (ev.kind == GDR_EVT_TXDONE && ev.b == GIP_CMD_POWER
                           && (long)(int)ev.a >= 0) {
                    /* serialized minimal startup: a successful power-on OUT
                     * completion queues the follow-up S-init exactly once. */
                    gdr_gip_on_power_done(&g_gip);
                } else if (ev.kind == GDR_EVT_DETACH) {
                    /* device removed: full decoder reset (snapshot + identity +
                     * TX queue + sequence) in main-loop context, then EMIT the
                     * neutral/disconnected STATE once (the STATE block below only
                     * logs on snapshot_valid, which is now 0), and clear the
                     * generation-scoped flags so a replug cannot inherit green
                     * or a stale device identity from the previous generation. */
                    gdr_gip_neutralize(&g_gip);
                    memset(&last_snap, 0, sizeof last_snap);
                    {
                        char sline[128]; size_t sn = gdr_format_state(sline, sizeof sline, &g_gip.snap);
                        LOG_LIT("STATE ");
                        log_write(sline, sn);
                        log_write("\n", 1);
                    }
                    g_input_seen = 0;
                    g_device = 0;
                    g_attached = 0;
                }
                if (do_log) {
                    char line[256]; size_t ln = gdr_format_event(line, sizeof line, &ev);
                    log_write(line, ln);
                }
            }
        }

        /* transport is live ONLY when Attach ran AND the interrupt IN endpoint
         * opened. Re-evaluated AFTER draining events: a DETACH drained in this
         * pass zeroes in_handle, so the qualified startup / OUT submit below
         * can never run for a stale (previous) generation. */
        int transport = gdr_transport_live(g_attached, g_att.in_handle);

        /* GIP poll (no-op hook) + bridge the state machine's TX queue into the
         * OUT queue, then submit the next OUT frame. Startup is explicit: the
         * qualified wired path fires once here (state 6), never a blind poll. */
        if (transport) {
            /* qualified first-party wired startup: no announce/identify. Once
             * the interrupt endpoints are fully open, mark the decoder gamepad
             * path and send minimal power-on (S-init follows on completion). */
            if (g_att.state >= 6u && g_gip.gamepad == 0) {
                gdr_gip_qualify_wired(&g_gip);
            }
            gdr_gip_poll(&g_gip, g_now_ms);

            u8 out_pkt[64]; int out_n;
            while ((out_n = gdr_tx_drain(&g_gip, out_pkt, 64)) > 0) {
                /* record what we are about to send, as its own log kind */
                if (out_pkt[0] == GIP_CMD_IDENTIFY || out_pkt[0] == GIP_CMD_ACK) {
                    struct gdr_evt ev; memset(&ev,0,sizeof ev);
                    ev.kind = (out_pkt[0] == GIP_CMD_IDENTIFY) ? GDR_EVT_IDENTIFY : GDR_EVT_ACK;
                    ev.seq = ++g_seq; ev.len = (u32)out_n;
                    for (int j=0;j<out_n && j<GDR_PKT_MAX;j++) ev.data[j]=out_pkt[j];
                    gdr_ring_push(&g_ring, &ev);
                }
                gdr_tx_enqueue(&g_att, out_pkt, out_n);
            }
            gdr_tx_submit_next(&g_att);
        }

        /* log decoded state change — written DIRECTLY (main-loop context, not a
         * DPC event) so the full A/B/X/Y/Black/White/LT/RT + stick line is never
         * truncated to the 64-byte packet-event buffer. */
        if (g_gip.snapshot_valid) {
            if (!gdr_snap_equal(&g_gip.snap, &last_snap)) {
                char sline[128]; size_t sn = gdr_format_state(sline, sizeof sline, &g_gip.snap);
                memcpy(&last_snap, &g_gip.snap, sizeof last_snap);
                LOG_LIT("STATE ");
                log_write(sline, sn);
                log_write("\n", 1);
                g_input_seen++;
            }
        }

        /* WAITING pad notification every 5 s */
        if (g_att.rx_events == 0) {
            startup_wait += GDR_TICK_MS;
            if (startup_wait % 5000 == 0 && no_pkt_logged++ < 10) {
                LOG_LIT("WAITING pad\n");
            }
        }

        /* LIVE every 1 s: is the IN URB pending, and the OUT queue depth /
         * IN / OUT completion counters — the next run shows an IN stall as
         * in_flight=0 with no further RX. */
        if (g_now_ms - last_live_ms >= GDR_LIVE_PERIOD_MS) {
            last_live_ms = g_now_ms;
            char lline[64]; size_t lln=0;
            lln=gdr_str(lline,sizeof lline,lln,"LIVE in_flight=");
            lln=gdr_dec(lline,sizeof lline,lln,g_att.in_flight ? 1u : 0u);
            lln=gdr_str(lline,sizeof lline,lln," tx_q=");
            lln=gdr_dec(lline,sizeof lline,lln,g_att.tx_head - g_att.tx_tail);
            lln=gdr_str(lline,sizeof lline,lln," rx=");
            lln=gdr_dec(lline,sizeof lline,lln,g_att.rx_events);
            lln=gdr_str(lline,sizeof lline,lln," tx=");
            lln=gdr_dec(lline,sizeof lline,lln,g_att.tx_events);
            lln=gdr_str(lline,sizeof lline,lln," inf=");
            lln=gdr_dec(lline,sizeof lline,lln,g_att.in_submit_fail);
            lln=gdr_str(lline,sizeof lline,lln," outf=");
            lln=gdr_dec(lline,sizeof lline,lln,g_att.tx_submit_fail);
            lln=gdr_str(lline,sizeof lline,lln,"\n");
            log_write(lline,lln);
        }

        /* HEARTBEAT every 30 s, flushed — a future hang shows how far it got. */
        if (g_now_ms - last_hb_ms >= GDR_HB_PERIOD_MS) {
            last_hb_ms = g_now_ms;
            char hline[32]; size_t hn=0;
            hn=gdr_str(hline,sizeof hline,hn,"HEARTBEAT t=");
            hn=gdr_dec(hline,sizeof hline,hn,g_now_ms/1000);
            hn=gdr_str(hline,sizeof hline,hn,"s\n");
            log_write(hline,hn);
            log_flush();
        }

        /* colour screen: red=PINFAIL/STEPFAIL/CFGFAIL, yellow=armed,
         * cyan=attached (S0 ran), green=decoded input packets. */
        if (g_pDev) {
            D3DCOLOR col;
            if (armcode != 0)        col = 0xFFFF0000;   /* red: pinfail      */
            else if (g_att.failed)   col = 0xFFFF0000;   /* red: step/cfg fail */
            else if (g_att.detached) col = 0xFFFF8000;   /* orange: disconnected/waiting replug */
            else if (g_input_seen>0) col = 0xFF00FF00;   /* green: input      */
            else if (g_attached)     col = 0xFF00FFFF;   /* cyan: attached    */
            else                     col = 0xFFFFFF00;   /* yellow: armed     */
            if (bs_held>0 && bs_held<1000) col = ((bs_held/250)&1) ? 0xFF000000 : col;
            video_clear(col);
        }

        /* BACK+START exit */
        {
            int held=0;
            for (int port=0;port<4&&!held;port++) {
                XINPUT_STATE st;
                if (pads[port]&&XInputGetState(pads[port],&st)==ERROR_SUCCESS&&
                    (st.Gamepad.wButtons&(XINPUT_GAMEPAD_BACK|XINPUT_GAMEPAD_START))==
                    (XINPUT_GAMEPAD_BACK|XINPUT_GAMEPAD_START))
                    held=1;
            }
            if (held) { bs_held+=250; if (bs_held>=1000) goto do_exit; }
            else bs_held=0;
        }

        /* auto-return watchdog (6 min for the lifecycle probe) */
        if (g_now_ms >= GDR_EXIT_AFTER_MS) goto do_exit;

        log_flush();
        Sleep(GDR_TICK_MS);
    }

do_exit:
    LOG_LIT("GIPEXIT auto\n");
    log_flush();
    XLaunchNewImage(NULL, NULL);
    return 0;
}
