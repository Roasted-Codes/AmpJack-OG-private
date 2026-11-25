static inline bool usb_packet_is_inflight(USBPacket *p)
{
    return (p->state == USB_PACKET_QUEUED ||
            p->state == USB_PACKET_ASYNC);
}
