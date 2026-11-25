#include <stddef.h>
#include <string.h>
#include "gipdrive.h"
#define O(x) offsetof(struct gdr_attach_ctx,x)
unsigned layout[]={sizeof(struct gdr_attach_ctx),O(device),O(rx_events),O(tx_events),O(in_flight),O(state),O(failed),O(generation),O(lifecycle),O(pending),O(detached),O(close_stage),O(close_pending),O(close_count),O(close_submit_fail),O(remove_complete_called),O(in_handle),O(out_handle),O(control_handle)};
