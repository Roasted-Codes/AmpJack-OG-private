#include <stddef.h>
#include "ogx_module.h"
#define O(n, f) __asm__ volatile(".globl OFF_" #n "\n.set OFF_" #n ", %c0" :: "i"(offsetof(struct ogx_module, f)));
void ogx_offsets(void){
O(att_device,att.device) O(att_rx_events,att.rx_events) O(att_tx_events,att.tx_events) O(att_in_flight,att.in_flight)
O(att_state,att.state) O(att_failed,att.failed) O(att_fail_step,att.fail_step) O(att_fail_status,att.fail_status)
O(att_in_submit_fail,att.in_submit_fail) O(att_tx_submit_fail,att.tx_submit_fail) O(att_control_handle,att.control_handle)
O(att_in_handle,att.in_handle) O(att_out_handle,att.out_handle) O(att_generation,att.generation) O(att_lifecycle,att.lifecycle)
O(att_detached,att.detached) O(att_add_complete_called,att.add_complete_called) O(att_add_status,att.add_status)
O(gip_started,gip.started) O(gip_identified,gip.identified) O(gip_gamepad,gip.gamepad) O(gip_ready,gip.ready)
O(gip_s_init_pending,gip.s_init_pending) O(gip_snapshot_valid,gip.snapshot_valid) O(gip_input_reports,gip.input_reports)
O(gip_unknown_cmds,gip.unknown_cmds) O(gip_snap,gip.snap) O(ring_head,ring.head) O(ring_tail,ring.tail) O(ring_overflow,ring.overflow)
O(present_attached_mask,present.attached_mask) O(present_native_connected_mask,present.native_connected_mask) O(present_prev_present,present.prev_present)
O(present_next_handle,present.next_handle) O(present_gen,present.gen) O(present_served_packet,present.served_packet) O(present_last_served_seq,present.last_served_seq) O(present_last_served_gen,present.last_served_gen) O(present_insertion_edges,present.insertion_edges) O(present_removal_edges,present.removal_edges) O(present_forged_handles,present.forged_handles) O(present_vh,present.vh)
O(attached,attached) O(installed_hooks,installed_hooks) O(install_failed,install_failed)
__asm__ volatile(".globl SIZEOF_module\n.set SIZEOF_module, %c0"::"i"(sizeof(struct ogx_module)));
}
