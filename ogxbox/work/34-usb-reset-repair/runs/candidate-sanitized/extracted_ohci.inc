void ohci_stop_endpoints(OHCIState *ohci)
{
    USBDevice *dev;
    int i, j;

    if (ohci->async_td) {
        /*
         * A completed packet stays owned by async_td until its TD is
         * retired; only a packet still in flight can be cancelled.
         */
        if (usb_packet_is_inflight(&ohci->usb_packet)) {
            usb_cancel_packet(&ohci->usb_packet);
        }
        ohci->async_td = 0;
        ohci->async_complete = false;
    }
    for (i = 0; i < ohci->num_ports; i++) {
        dev = ohci->rhport[i].port.dev;
        if (dev && dev->attached) {
            usb_device_ep_stopped(dev, &dev->ep_ctl);
            for (j = 0; j < USB_MAX_ENDPOINTS; j++) {
                usb_device_ep_stopped(dev, &dev->ep_in[j]);
                usb_device_ep_stopped(dev, &dev->ep_out[j]);
            }
        }
    }
}

static void ohci_roothub_reset(OHCIState *ohci)
{
    OHCIPort *port;
    int i;

    ohci_bus_stop(ohci);
    ohci->rhdesc_a = OHCI_RHA_NPS | ohci->num_ports;
    ohci->rhdesc_b = 0x0; /* Impl. specific */
    ohci->rhstatus = 0;

    for (i = 0; i < ohci->num_ports; i++) {
        port = &ohci->rhport[i];
        port->ctrl = 0;
        if (port->port.dev && port->port.dev->attached) {
            usb_port_reset(&port->port);
        }
    }
    ohci_stop_endpoints(ohci);
}

static void ohci_child_detach(USBPort *port1, USBDevice *dev)
{
    OHCIState *ohci = port1->opaque;

    if (ohci->async_td &&
        usb_packet_is_inflight(&ohci->usb_packet) &&
        ohci->usb_packet.ep->dev == dev) {
        usb_cancel_packet(&ohci->usb_packet);
        ohci->async_td = 0;
    }
}

static void ohci_detach(USBPort *port1)
{
    OHCIState *s = port1->opaque;
    OHCIPort *port = &s->rhport[port1->index];
    uint32_t old_state = port->ctrl;

    ohci_child_detach(port1, port1->dev);

    /* set connect status */
    if (port->ctrl & OHCI_PORT_CCS) {
        port->ctrl &= ~OHCI_PORT_CCS;
        port->ctrl |= OHCI_PORT_CSC;
    }
    /* disable port */
    if (port->ctrl & OHCI_PORT_PES) {
        port->ctrl &= ~OHCI_PORT_PES;
        port->ctrl |= OHCI_PORT_PESC;
    }
    trace_usb_ohci_port_detach(port1->index);

    if (old_state != port->ctrl) {
        ohci_set_interrupt(s, OHCI_INTR_RHSC);
    }
}

static void ohci_async_complete_packet(USBPort *port, USBPacket *packet)
{
    OHCIState *ohci = container_of(packet, OHCIState, usb_packet);

    trace_usb_ohci_async_complete();
    ohci->async_complete = true;
    ohci_process_lists(ohci);
}

static int ohci_service_ed_list(OHCIState *ohci, uint32_t head)
{
    struct ohci_ed ed;
    uint32_t next_ed;
    uint32_t cur;
    int active;
    uint32_t link_cnt = 0;
    active = 0;

    if (head == 0) {
        return 0;
    }
    for (cur = head; cur && link_cnt++ < ED_LINK_LIMIT; cur = next_ed) {
        if (ohci_read_ed(ohci, cur, &ed)) {
            trace_usb_ohci_ed_read_error(cur);
            ohci_die(ohci);
            return 0;
        }

        next_ed = ed.next & OHCI_DPTR_MASK;

        if ((ed.head & OHCI_ED_H) || (ed.flags & OHCI_ED_K)) {
            uint32_t addr;
            /* Cancel pending packets for ED that have been paused. */
            addr = ed.head & OHCI_DPTR_MASK;
            if (ohci->async_td && addr == ohci->async_td) {
                if (usb_packet_is_inflight(&ohci->usb_packet)) {
                    usb_cancel_packet(&ohci->usb_packet);
                }
                ohci->async_td = 0;
                ohci->async_complete = false;
                usb_device_ep_stopped(ohci->usb_packet.ep->dev,
                                      ohci->usb_packet.ep);
            }
            continue;
        }

        while ((ed.head & OHCI_DPTR_MASK) != ed.tail) {
            trace_usb_ohci_ed_pkt(cur, (ed.head & OHCI_ED_H) != 0,
                    (ed.head & OHCI_ED_C) != 0, ed.head & OHCI_DPTR_MASK,
                    ed.tail & OHCI_DPTR_MASK, ed.next & OHCI_DPTR_MASK);
            trace_usb_ohci_ed_pkt_flags(
                    OHCI_BM(ed.flags, ED_FA), OHCI_BM(ed.flags, ED_EN),
                    OHCI_BM(ed.flags, ED_D), (ed.flags & OHCI_ED_S) != 0,
                    (ed.flags & OHCI_ED_K) != 0, (ed.flags & OHCI_ED_F) != 0,
                    OHCI_BM(ed.flags, ED_MPS));

            active = 1;

            if ((ed.flags & OHCI_ED_F) == 0) {
                if (ohci_service_td(ohci, &ed)) {
                    break;
                }
            } else {
                /* Handle isochronous endpoints */
                if (ohci_service_iso_td(ohci, &ed)) {
                    break;
                }
            }
        }

        if (ohci_put_ed(ohci, cur, &ed)) {
            ohci_die(ohci);
            return 0;
        }
    }

    return active;
}
