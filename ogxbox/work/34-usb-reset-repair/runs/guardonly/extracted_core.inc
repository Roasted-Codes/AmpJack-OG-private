void usb_detach(USBPort *port)
{
    USBDevice *dev = port->dev;

    assert(dev != NULL);
    assert(dev->state != USB_STATE_NOTATTACHED);
    port->ops->detach(port);
    dev->state = USB_STATE_NOTATTACHED;
}

void usb_port_reset(USBPort *port)
{
    USBDevice *dev = port->dev;

    assert(dev != NULL);
    usb_detach(port);
    usb_attach(port);
    usb_device_reset(dev);
}

void usb_packet_complete_one(USBDevice *dev, USBPacket *p)
{
    USBEndpoint *ep = p->ep;

    assert(p->stream || QTAILQ_FIRST(&ep->queue) == p);
    assert(p->status != USB_RET_ASYNC && p->status != USB_RET_NAK);

    if (p->status != USB_RET_SUCCESS ||
            (p->short_not_ok && (p->actual_length < p->iov.size))) {
        ep->halted = true;
    }
    usb_pcap_data(p, false);
    usb_packet_set_state(p, USB_PACKET_COMPLETE);
    QTAILQ_REMOVE(&ep->queue, p, queue);
    dev->port->ops->complete(dev->port, p);
}

void usb_packet_complete(USBDevice *dev, USBPacket *p)
{
    USBEndpoint *ep = p->ep;

    usb_packet_check_state(p, USB_PACKET_ASYNC);
    usb_packet_complete_one(dev, p);

    while (!QTAILQ_EMPTY(&ep->queue)) {
        p = QTAILQ_FIRST(&ep->queue);
        if (ep->halted) {
            /* Empty the queue on a halt */
            p->status = USB_RET_REMOVE_FROM_QUEUE;
            dev->port->ops->complete(dev->port, p);
            continue;
        }
        if (p->state == USB_PACKET_ASYNC) {
            break;
        }
        usb_packet_check_state(p, USB_PACKET_QUEUED);
        usb_process_one(p);
        if (p->status == USB_RET_ASYNC) {
            usb_packet_set_state(p, USB_PACKET_ASYNC);
            break;
        }
        usb_packet_complete_one(ep->dev, p);
    }
}

void usb_cancel_packet(USBPacket * p)
{
    bool callback = (p->state == USB_PACKET_ASYNC);
    assert(usb_packet_is_inflight(p));
    usb_packet_set_state(p, USB_PACKET_CANCELED);
    QTAILQ_REMOVE(&p->ep->queue, p, queue);
    if (callback) {
        usb_device_cancel_packet(p->ep->dev, p);
    }
}
