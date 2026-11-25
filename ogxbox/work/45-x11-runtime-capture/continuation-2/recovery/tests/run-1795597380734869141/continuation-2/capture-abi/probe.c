#include <stddef.h>
#include "ogx_module.h"
const unsigned o_module_size = sizeof(struct ogx_module);
const unsigned o_att_size = sizeof(struct gdr_attach_ctx);
const unsigned o_ring = offsetof(struct ogx_module, ring);
const unsigned o_ring_head = offsetof(struct ogx_module, ring.head);
const unsigned o_ring_tail = offsetof(struct ogx_module, ring.tail);
const unsigned o_ring_overflow = offsetof(struct ogx_module, ring.overflow);
const unsigned o_evt_size = sizeof(struct gdr_evt);
const unsigned o_ring_cap = GDR_RING_CAP;
const unsigned o_evt_data = offsetof(struct gdr_evt, data);
const unsigned o_evt_type = offsetof(struct gdr_evt, kind);
const unsigned o_gip_reports = offsetof(struct ogx_module, gip.input_reports);
const unsigned o_gip_valid = offsetof(struct ogx_module, gip.snapshot_valid);
const unsigned o_served = offsetof(struct ogx_module, present.served_packet[1]);
const unsigned o_served_seq = offsetof(struct ogx_module, present.last_served_seq[1]);
const unsigned o_native_mask = offsetof(struct ogx_module, present.native_connected_mask);
const unsigned o_gamepad = offsetof(struct ogx_module, gport[1].gamepad);
const unsigned o_port_valid = offsetof(struct ogx_module, gport[1].snapshot_valid);
const unsigned o_vh = offsetof(struct ogx_module, present.vh);
const unsigned o_vh_size = sizeof(struct ogx_vhandle);
const unsigned o_present = offsetof(struct ogx_module, present);
