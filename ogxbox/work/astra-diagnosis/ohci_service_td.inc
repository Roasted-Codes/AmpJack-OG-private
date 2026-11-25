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

static int ohci_service_td(OHCIState *ohci, struct ohci_ed *ed)
{
    int dir;
    size_t len = 0, pktlen = 0;
    const char *str = NULL;
    int pid;
    int ret;
    int i;
    USBDevice *dev;
    USBEndpoint *ep;
    struct ohci_td td;
    uint32_t addr;
    int flag_r;
    int completion;

    addr = ed->head & OHCI_DPTR_MASK;
    if (addr == 0) {
        ohci_die(ohci);
        return 1;
    }

    /* See if this TD has already been submitted to the device. */
    completion = (addr == ohci->async_td);
    if (completion && !ohci->async_complete) {
        trace_usb_ohci_td_skip_async();
        return 1;
    }
    if (ohci_read_td(ohci, addr, &td)) {
        trace_usb_ohci_td_read_error(addr);
        ohci_die(ohci);
        return 1;
    }

    dir = OHCI_BM(ed->flags, ED_D);
    switch (dir) {
    case OHCI_TD_DIR_OUT:
    case OHCI_TD_DIR_IN:
        /* Same value. */
        break;
    default:
        dir = OHCI_BM(td.flags, TD_DP);
        break;
    }

    switch (dir) {
    case OHCI_TD_DIR_IN:
        str = "in";
        pid = USB_TOKEN_IN;
        break;
    case OHCI_TD_DIR_OUT:
        str = "out";
        pid = USB_TOKEN_OUT;
        break;
    case OHCI_TD_DIR_SETUP:
        str = "setup";
        pid = USB_TOKEN_SETUP;
        if (OHCI_BM(ed->flags, ED_EN) > 0) {  /* setup only allowed to ep 0 */
            trace_usb_ohci_td_bad_pid(str, ed->flags, td.flags);
            ohci_die(ohci);
            return 1;
        }
        break;
    default:
        trace_usb_ohci_td_bad_direction(dir);
        return 1;
    }
    if (td.cbp && td.be) {
        if ((td.cbp & 0xfffff000) != (td.be & 0xfffff000)) {
            len = (td.be & 0xfff) + 0x1001 - (td.cbp & 0xfff);
        } else {
            if (td.cbp - 1 > td.be) {  /* rely on td.cbp != 0 */
                trace_usb_ohci_td_bad_buf(td.cbp, td.be);
                ohci_die(ohci);
                return 1;
            }
            len = (td.be - td.cbp) + 1;
        }
        if (len > sizeof(ohci->usb_buf)) {
            len = sizeof(ohci->usb_buf);
        }

        pktlen = len;
        if (len && dir != OHCI_TD_DIR_IN) {
            /* The endpoint may not allow us to transfer it all now */
            pktlen = (ed->flags & OHCI_ED_MPS_MASK) >> OHCI_ED_MPS_SHIFT;
            if (pktlen > len) {
                pktlen = len;
            }
            if (!completion) {
                if (ohci_copy_td(ohci, &td, ohci->usb_buf, pktlen,
                                 DMA_DIRECTION_TO_DEVICE)) {
                    ohci_die(ohci);
                }
            }
        }
    }

    flag_r = (td.flags & OHCI_TD_R) != 0;
    trace_usb_ohci_td_pkt_hdr(addr, (int64_t)pktlen, (int64_t)len, str,
                              flag_r, td.cbp, td.be);
    ohci_td_pkt("OUT", ohci->usb_buf, pktlen);

    if (completion) {
        ohci->async_td = 0;
        ohci->async_complete = false;
    } else {
        dev = ohci_find_device(ohci, OHCI_BM(ed->flags, ED_FA));
        if (dev == NULL) {
            trace_usb_ohci_td_dev_error();
            return 1;
        }
        ep = usb_ep_get(dev, pid, OHCI_BM(ed->flags, ED_EN));
        if (ohci->async_td) {
            /*
             * ??? The hardware should allow one active packet per
             * endpoint.  We only allow one active packet per controller.
             * This should be sufficient as long as devices respond in a
             * timely manner.
             */
            trace_usb_ohci_td_too_many_pending(ep->nr);
            return 1;
        }
        usb_packet_setup(&ohci->usb_packet, pid, ep, 0, addr, !flag_r,
                         OHCI_BM(td.flags, TD_DI) == 0);
        usb_packet_addbuf(&ohci->usb_packet, ohci->usb_buf, pktlen);
        usb_handle_packet(dev, &ohci->usb_packet);
        trace_usb_ohci_td_packet_status(ohci->usb_packet.status);

        if (ohci->usb_packet.status == USB_RET_ASYNC) {
            usb_device_flush_ep_queue(dev, ep);
            ohci->async_td = addr;
            return 1;
        }
    }
    if (ohci->usb_packet.status == USB_RET_SUCCESS) {
        ret = ohci->usb_packet.actual_length;
    } else {
        ret = ohci->usb_packet.status;
    }

    if (ret >= 0) {
        if (dir == OHCI_TD_DIR_IN) {
            if (ohci_copy_td(ohci, &td, ohci->usb_buf, ret,
                             DMA_DIRECTION_FROM_DEVICE)) {
                ohci_die(ohci);
            }
            ohci_td_pkt("IN", ohci->usb_buf, pktlen);
        } else {
            ret = pktlen;
        }
    }

    if (ret >= 0) {
        if ((td.cbp & 0xfff) + ret > 0xfff) {
            td.cbp = (td.be & ~0xfff) + ((td.cbp + ret) & 0xfff);
        } else {
            td.cbp += ret;
        }
    }

    /* Writeback */
    if (ret == pktlen || (dir == OHCI_TD_DIR_IN && ret >= 0 && flag_r)) {
        /* Transmission succeeded. */
        if (ret == len) {
            td.cbp = 0;
        }
        td.flags |= OHCI_TD_T1;
        td.flags ^= OHCI_TD_T0;
        OHCI_SET_BM(td.flags, TD_CC, OHCI_CC_NOERROR);
        OHCI_SET_BM(td.flags, TD_EC, 0);

        if ((dir != OHCI_TD_DIR_IN) && (ret != len)) {
            /* Partial packet transfer: TD not ready to retire yet */
            goto exit_no_retire;
        }

        /* Setting ED_C is part of the TD retirement process */
        ed->head &= ~OHCI_ED_C;
        if (td.flags & OHCI_TD_T0) {
            ed->head |= OHCI_ED_C;
        }
    } else {
        if (ret >= 0) {
            trace_usb_ohci_td_underrun();
            OHCI_SET_BM(td.flags, TD_CC, OHCI_CC_DATAUNDERRUN);
        } else {
            switch (ret) {
            case USB_RET_IOERROR:
            case USB_RET_NODEV:
                trace_usb_ohci_td_dev_error();
                OHCI_SET_BM(td.flags, TD_CC, OHCI_CC_DEVICENOTRESPONDING);
                break;
            case USB_RET_NAK:
                trace_usb_ohci_td_nak();
                return 1;
            case USB_RET_STALL:
                trace_usb_ohci_td_stall();
                OHCI_SET_BM(td.flags, TD_CC, OHCI_CC_STALL);
                break;
            case USB_RET_BABBLE:
                trace_usb_ohci_td_babble();
                OHCI_SET_BM(td.flags, TD_CC, OHCI_CC_DATAOVERRUN);
                break;
            default:
                trace_usb_ohci_td_bad_device_response(ret);
                OHCI_SET_BM(td.flags, TD_CC, OHCI_CC_UNDEXPETEDPID);
                OHCI_SET_BM(td.flags, TD_EC, 3);
                break;
            }
            /*
             * An error occurred so we have to clear the interrupt counter.
             * See spec at 6.4.4 on page 104
             */
            ohci->done_count = 0;
        }
        ed->head |= OHCI_ED_H;
    }

    /* Retire this TD */
    ed->head &= ~OHCI_DPTR_MASK;
    ed->head |= td.next & OHCI_DPTR_MASK;
    td.next = ohci->done;
    ohci->done = addr;
    i = OHCI_BM(td.flags, TD_DI);
    if (i < ohci->done_count) {
        ohci->done_count = i;
    }
    if (OHCI_BM(td.flags, TD_CC) != OHCI_CC_NOERROR) {
        ohci->done_count = 0;
    }
exit_no_retire:
    if (ohci_put_td(ohci, addr, &td)) {
        ohci_die(ohci);
        return 1;
    }
    return OHCI_BM(td.flags, TD_CC) != OHCI_CC_NOERROR;
}

