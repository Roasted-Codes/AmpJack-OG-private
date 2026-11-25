/*
 * QEMU USB OHCI Emulation
 * Copyright (c) 2004 Gianni Tedesco
 * Copyright (c) 2006 CodeSourcery
 * Copyright (c) 2006 Openedhand Ltd.
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with this library; if not, see <http://www.gnu.org/licenses/>.
 *
 * TODO:
 *  o Isochronous transfers
 *  o Allocate bandwidth in frames properly
 *  o Disable timers when nothing needs to be done, or remove timer usage
 *    all together.
 *  o BIOS work to boot from USB storage
 */

#define ED_LINK_LIMIT 32
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

static void ohci_process_lists(OHCIState *ohci)
{
    if ((ohci->ctl & OHCI_CTL_CLE) && (ohci->status & OHCI_STATUS_CLF)) {
        if (ohci->ctrl_cur && ohci->ctrl_cur != ohci->ctrl_head) {
            trace_usb_ohci_process_lists(ohci->ctrl_head, ohci->ctrl_cur);
        }
        if (!ohci_service_ed_list(ohci, ohci->ctrl_head)) {
            ohci->ctrl_cur = 0;
            ohci->status &= ~OHCI_STATUS_CLF;
        }
    }

    if ((ohci->ctl & OHCI_CTL_BLE) && (ohci->status & OHCI_STATUS_BLF)) {
        if (!ohci_service_ed_list(ohci, ohci->bulk_head)) {
            ohci->bulk_cur = 0;
            ohci->status &= ~OHCI_STATUS_BLF;
        }
    }
}

static void ohci_async_complete_packet(USBPort *port, USBPacket *packet)
{
    OHCIState *ohci = container_of(packet, OHCIState, usb_packet);

    trace_usb_ohci_async_complete();
    ohci->async_complete = true;
    ohci_process_lists(ohci);
}

