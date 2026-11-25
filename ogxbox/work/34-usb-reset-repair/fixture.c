/*
 * Deterministic reset/cancel lifecycle fixture for xemu OHCI.
 * Compiles REAL function bodies extracted by run_fixture.py from:
 *   hw/usb/hcd-ohci.c : ohci_stop_endpoints, ohci_roothub_reset,
 *                       ohci_child_detach, ohci_detach,
 *                       ohci_async_complete_packet, ohci_service_ed_list
 *   hw/usb/core.c     : usb_detach, usb_port_reset, usb_cancel_packet,
 *                       usb_packet_complete_one, usb_packet_complete
 *   include/hw/usb.h  : usb_packet_is_inflight
 * Everything else is a small counting double.  No guest, no QMP, no USB.
 */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define USB_MAX_ENDPOINTS 15
#define USB_TOKEN_IN 0x69
#define USB_ENDPOINT_XFER_INT 3
#define USB_RET_SUCCESS 0
#define USB_RET_NAK (-2)
#define USB_RET_ASYNC (-6)
#define USB_RET_REMOVE_FROM_QUEUE (-8)
#define USB_STATE_NOTATTACHED 0
#define USB_STATE_ATTACHED 1
#define container_of(ptr, type, member) \
    ((type *)((char *)(ptr) - offsetof(type, member)))
#define le32_to_cpu(x) (x)

typedef enum USBPacketState {
    USB_PACKET_UNDEFINED = 0, USB_PACKET_SETUP, USB_PACKET_QUEUED,
    USB_PACKET_ASYNC, USB_PACKET_COMPLETE, USB_PACKET_CANCELED,
} USBPacketState;

typedef struct USBPacket USBPacket;
typedef struct USBDevice USBDevice;
typedef struct USBPort USBPort;

/* One-slot queue double: removal of a packet that is not queued aborts. */
#define QTAILQ_FIRST(h) ((h)->first)
#define QTAILQ_EMPTY(h) ((h)->first == NULL)
#define QTAILQ_REMOVE(h, e, f) do { \
    if ((h)->first != (e)) { \
        fprintf(stderr, "FIXTURE: QTAILQ_REMOVE of non-queued packet\n"); \
        abort(); } (h)->first = NULL; } while (0)

typedef struct USBEndpoint {
    uint8_t nr, type;
    bool halted;
    USBDevice *dev;
    struct { USBPacket *first; } queue;
} USBEndpoint;

struct USBPacket {
    USBPacketState state;
    USBEndpoint *ep;
    int pid, status, actual_length, stream;
    uint64_t id;
    bool short_not_ok;
    struct { size_t size; } iov;
};

typedef struct USBPortOps {
    void (*detach)(USBPort *);
    void (*child_detach)(USBPort *, USBDevice *);
    void (*complete)(USBPort *, USBPacket *);
} USBPortOps;

struct USBPort { USBDevice *dev; void *opaque; int index; USBPortOps *ops; };

struct USBDevice {
    bool attached;
    int state;
    USBPort *port;
    USBEndpoint ep_ctl, ep_in[USB_MAX_ENDPOINTS], ep_out[USB_MAX_ENDPOINTS];
};

/* Real hcd-ohci.c constants and struct ohci_ed/td definitions. */
#include "extracted_trace_stubs.inc"
#include "extracted_constants.inc"
typedef struct OHCIPort { USBPort port; uint32_t ctrl; } OHCIPort;
typedef struct OHCIState {
    const char *name;
    int num_ports;
    OHCIPort rhport[4];
    uint32_t ctl, rhdesc_a, rhdesc_b, rhstatus;
    uint32_t async_td;
    bool async_complete;
    USBPacket usb_packet;
} OHCIState;

/* ---- counting doubles ---- */
static int n_dev_cancel, n_ep_stopped, n_process_lists, n_dev_reset, n_put_ed;
static int n_set_intr;
static struct ohci_ed fixture_ed;
static void usb_packet_set_state(USBPacket *p, USBPacketState s) { p->state = s; }
static void usb_packet_check_state(USBPacket *p, USBPacketState s)
{ if (p->state != s) { fprintf(stderr, "FIXTURE: packet state %d != %d\n", p->state, s); abort(); } }
static void usb_device_cancel_packet(USBDevice *d, USBPacket *p) { (void)d; (void)p; n_dev_cancel++; }
static void usb_device_ep_stopped(USBDevice *d, USBEndpoint *ep) { (void)d; (void)ep; n_ep_stopped++; }
static void usb_device_reset(USBDevice *d) { (void)d; n_dev_reset++; }
static void usb_attach(USBPort *p) { p->dev->state = USB_STATE_ATTACHED; }
static void usb_pcap_data(USBPacket *p, bool s) { (void)p; (void)s; }
static void usb_process_one(USBPacket *p) { (void)p; abort(); }
static void ohci_bus_stop(OHCIState *o) { (void)o; }
static void ohci_set_interrupt(OHCIState *o, uint32_t i) { (void)o; (void)i; n_set_intr++; }
static void ohci_process_lists(OHCIState *o) { (void)o; n_process_lists++; }
static void ohci_die(OHCIState *o) { (void)o; fprintf(stderr, "FIXTURE: ohci_die\n"); abort(); }
static int ohci_read_ed(OHCIState *o, uint32_t a, struct ohci_ed *ed) { (void)o; (void)a; *ed = fixture_ed; return 0; }
static int ohci_put_ed(OHCIState *o, uint32_t a, struct ohci_ed *ed) { (void)o; (void)a; (void)ed; n_put_ed++; return 0; }
static int ohci_service_td(OHCIState *o, struct ohci_ed *ed) { (void)o; (void)ed; fprintf(stderr, "FIXTURE: unexpected service_td\n"); abort(); }
static int ohci_service_iso_td(OHCIState *o, struct ohci_ed *ed) { (void)o; (void)ed; abort(); }

#include "extracted_usb_h.inc"
#include "extracted_core.inc"
#include "extracted_ohci.inc"

static USBPortOps ohci_port_ops = {
    .detach = ohci_detach, .child_detach = ohci_child_detach,
    .complete = ohci_async_complete_packet,
};

/* xemu Xbox topology: a hub on the root port, pad on hub port index 3. */
static USBDevice hub, pad;
static USBPort hub_port3;
static void hub_complete(USBPort *p, USBPacket *pk) { (void)p; hub.port->ops->complete(hub.port, pk); }
static void hub_child_detach(USBPort *p, USBDevice *d) { (void)p; hub.port->ops->child_detach(hub.port, d); }
static USBPortOps hub_port_ops = { .complete = hub_complete, .child_detach = hub_child_detach };

static OHCIState ohci;
#define TD_ADDR 0x3b25e20u

static void setup(bool via_hub)
{
    memset(&ohci, 0, sizeof(ohci));
    memset(&hub, 0, sizeof(hub));
    memset(&pad, 0, sizeof(pad));
    ohci.name = "pci-ohci";
    ohci.num_ports = 4;
    for (int i = 0; i < 4; i++) {
        ohci.rhport[i].port.opaque = &ohci;
        ohci.rhport[i].port.index = i;
        ohci.rhport[i].port.ops = &ohci_port_ops;
    }
    pad.attached = true;
    pad.state = USB_STATE_ATTACHED;
    if (via_hub) {
        hub.attached = true;
        hub.state = USB_STATE_ATTACHED;
        hub.port = &ohci.rhport[0].port;
        ohci.rhport[0].port.dev = &hub;
        hub_port3 = (USBPort){ .dev = &pad, .opaque = &hub, .index = 3, .ops = &hub_port_ops };
        pad.port = &hub_port3;
    } else {
        pad.port = &ohci.rhport[0].port;
        ohci.rhport[0].port.dev = &pad;
    }
    pad.ep_in[1] = (USBEndpoint){ .nr = 2, .type = USB_ENDPOINT_XFER_INT, .dev = &pad };
}

/* Mirrors ohci_service_td's submission of an interrupt IN that went async. */
static void submit_async_in(uint32_t td)
{
    USBPacket *p = &ohci.usb_packet;
    assert(!usb_packet_is_inflight(p)); /* core.c usb_packet_setup precondition */
    p->ep = &pad.ep_in[1];
    p->pid = USB_TOKEN_IN;
    p->id = td;
    p->iov.size = 64;
    p->actual_length = 0;
    p->status = USB_RET_ASYNC;
    p->ep->queue.first = p;
    usb_packet_set_state(p, USB_PACKET_ASYNC);
    ohci.async_td = td;
}

/* The real device-side completion: an 8-byte input report arrives. */
static void device_completes(void)
{
    USBPacket *p = &ohci.usb_packet;
    p->status = USB_RET_SUCCESS;
    p->actual_length = 8;
    usb_packet_complete(&pad, p);
}

static int check(bool ok, const char *what)
{
    printf("%s %s\n", ok ? "PASS" : "FAIL", what);
    return ok ? 0 : 1;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    const char *c = argv[1];
    int fail = 0;
    bool hubtopo = strstr(c, "_hub") != NULL;
    setup(hubtopo);

    if (!strcmp(c, "idle_reset")) {
        ohci_roothub_reset(&ohci);
        fail |= check(n_dev_cancel == 0 && ohci.async_td == 0, "idle reset: nothing cancelled");
    } else if (!strncmp(c, "reset_inflight", 14)) {
        submit_async_in(TD_ADDR);
        ohci_roothub_reset(&ohci);
        fail |= check(ohci.usb_packet.state == USB_PACKET_CANCELED, "in-flight packet cancelled");
        fail |= check(n_dev_cancel == 1, "device cancel callback exactly once");
        fail |= check(ohci.async_td == 0 && !ohci.async_complete, "slot free after reset");
    } else if (!strncmp(c, "reset_complete", 14)) {
        submit_async_in(TD_ADDR);
        device_completes();
        fail |= check(ohci.async_complete && ohci.usb_packet.state == USB_PACKET_COMPLETE,
                      "precondition: completed, not retired (matches core dump)");
        printf("STEP qmp-system_reset -> ohci_roothub_reset\n");
        fflush(stdout);
        ohci_roothub_reset(&ohci);
        fail |= check(n_dev_cancel == 0, "completed packet not cancelled at device");
        fail |= check(ohci.async_td == 0, "async_td released by reset");
        fail |= check(!ohci.async_complete, "async_complete cleared (no stale completion)");
        if (!strncmp(c, "reset_complete_then_input", 25)) {
            /* Next interrupt IN after reset must wait for its own completion:
             * ohci_service_td skips only if (completion && !async_complete). */
            submit_async_in(TD_ADDR + 0x40);
            fail |= check(!ohci.async_complete,
                          "new in-flight TD not treated as already complete");
            device_completes();
            fail |= check(ohci.async_complete && ohci.usb_packet.actual_length == 8,
                          "post-reset input report completes normally");
        }
    } else if (!strcmp(c, "listdisable_complete")) {
        submit_async_in(TD_ADDR);
        device_completes();
        ohci_stop_endpoints(&ohci); /* frame-boundary BLE/CLE disable path */
        fail |= check(ohci.async_td == 0 && !ohci.async_complete && n_dev_cancel == 0,
                      "list-disable releases completed slot");
    } else if (!strncmp(c, "edskip_", 7)) {
        submit_async_in(TD_ADDR);
        bool done = !strcmp(c, "edskip_complete");
        if (done) device_completes();
        fixture_ed = (struct ohci_ed){ .flags = OHCI_ED_K, .head = TD_ADDR, .tail = 0, .next = 0 };
        ohci_service_ed_list(&ohci, 0x1000);
        fail |= check(n_dev_cancel == (done ? 0 : 1), "cancel only if in flight");
        fail |= check(ohci.async_td == 0 && !ohci.async_complete, "skipped ED releases slot");
        fail |= check(n_ep_stopped == 1, "endpoint stopped once");
    } else if (!strcmp(c, "complete_then_retire_control")) {
        /* Normal path: completion, then the TD's own retirement clears the
         * slot (ohci_service_td completion branch); reset afterwards is idle. */
        submit_async_in(TD_ADDR);
        device_completes();
        fail |= check(n_process_lists == 1, "completion callback ran once");
        ohci.async_td = 0; ohci.async_complete = false; /* ohci_service_td:retire */
        ohci_roothub_reset(&ohci);
        fail |= check(n_dev_cancel == 0, "no cancel after retirement");
    } else {
        return 2;
    }
    return fail;
}
