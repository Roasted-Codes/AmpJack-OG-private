// Compile-check for ogxbox_urb_abi.h — static asserts on the pinned offsets.
#include "ogxbox_urb_abi.h"
#include <stddef.h>
#include <stdio.h>

#define SA(cond) ((void)sizeof(char[2 * !!(cond) - 1]))

int main(void)
{
    // URB header
    SA(offsetof(ogx_urb_header_urb, Length)          == 0x00);
    SA(offsetof(ogx_urb_header_urb, Function)        == 0x01);
    SA(offsetof(ogx_urb_header_urb, Reserved)        == 0x02);
    SA(offsetof(ogx_urb_header_urb, Status)          == 0x04);
    SA(offsetof(ogx_urb_header_urb, CompleteProc)    == 0x08);
    SA(offsetof(ogx_urb_header_urb, CompleteContext) == 0x0C);
    SA(sizeof(ogx_urb_header_urb) == 0x10);

    // Open endpoint
    SA(offsetof(ogx_urb_open_endpoint_urb, EndpointHandle)  == 0x10);
    SA(offsetof(ogx_urb_open_endpoint_urb, FunctionAddress) == 0x14);
    SA(offsetof(ogx_urb_open_endpoint_urb, EndpointAddress) == 0x15);
    SA(offsetof(ogx_urb_open_endpoint_urb, TransferType)    == 0x16);
    SA(offsetof(ogx_urb_open_endpoint_urb, Interval)        == 0x17);
    SA(offsetof(ogx_urb_open_endpoint_urb, TransferBuffer)  == 0x18);
    SA(offsetof(ogx_urb_open_endpoint_urb, MaxPacketSize)   == 0x1C);
    SA(offsetof(ogx_urb_open_endpoint_urb, Direction)       == 0x1E);
    SA(sizeof(ogx_urb_open_endpoint_urb) == 0x20);

    // Transfer (control / bulk-interrupt)
    SA(offsetof(ogx_urb_transfer_urb, EndpointHandle) == 0x10);
    SA(offsetof(ogx_urb_transfer_urb, TransferLength) == 0x14);
    SA(offsetof(ogx_urb_transfer_urb, TransferBuffer) == 0x18);
    SA(offsetof(ogx_urb_transfer_urb, Direction)      == 0x1E);
    SA(offsetof(ogx_urb_transfer_urb, ByteCount)      == 0x20);
    SA(offsetof(ogx_urb_transfer_urb, State)          == 0x22);
    SA(offsetof(ogx_urb_transfer_urb, TransferStatus) == 0x24);
    SA(offsetof(ogx_urb_transfer_urb, SetupPacket)    == 0x28);

    // Close endpoint
    SA(offsetof(ogx_urb_close_endpoint_urb, EndpointHandle) == 0x10);
    SA(sizeof(ogx_urb_close_endpoint_urb) == 0x1C); /* full URB Length allocation, not only used fields */

    printf("ogxbox_urb_abi.h layout asserts OK\n");
    return 0;
}
