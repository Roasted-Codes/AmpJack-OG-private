#define main previous_fixture_main
#include "../tests/test_close_contract.c"
#undef main
/* Unlike the previous fixture, a rejected/failed close does NOT free a handle. */
static long strict_submit(void *device,void *urb) {
 gdr_urb_header *h=(gdr_urb_header*)urb;(void)device;
 if(sim_n<SIM_MAX){sim_fn[sim_n]=h->Function;sim_hdl[sim_n]=*(u32*)((u8*)urb+0x10);sim_n++;}
 return sim_ret;
}
static void finish_close(u32 status) {
 ctx.close_urb.Hdr.Status=status;
 if((int)status>=0)open_handle_count--;
 gdr_close_complete(&ctx.close_urb,&ctx);
}
int main(void) {
 reset_all();drive_to_live();ctx.submit=strict_submit;
 gdr_remove_device(&ctx,(void*)0x1234);
 while(ctx.close_pending)finish_close(0);
 CHECK(rm_calls==1 && open_handle_count==0,"successful closes retire handles before the single ack");
 reset_all();drive_to_live();ctx.submit=strict_submit;sim_ret=-1;
 gdr_remove_device(&ctx,(void*)0x1234);
 CHECK(open_handle_count==3,"rejected close does not magically release native handles");
 CHECK(rm_calls==0 && ctx.lifecycle==GDR_LIFE_REMOVING,"rejected close cannot release/reuse device with live endpoints");
 reset_all();drive_to_live();ctx.submit=strict_submit;
 gdr_remove_device(&ctx,(void*)0x1234);finish_close(0xc0000004u);
 while(ctx.close_pending)finish_close(0xc0000004u);
 CHECK(open_handle_count==3,"failure completion does not establish successful handle retirement");
 CHECK(rm_calls==0 && ctx.lifecycle==GDR_LIFE_REMOVING,"unproven close failure must remain fail-closed, not acknowledge removal");
 printf("STRICT_CLOSE failures=%d\n",g_fail);return g_fail?1:0;
}
