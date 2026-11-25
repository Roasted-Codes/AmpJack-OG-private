/* Parent review: exercise real implementation, including untested failure/reentry. */
#define main lifecycle_original_main
#include "../tests/test_lifecycle.c"
#undef main

static int checks, failures;
#define VERIFY(c,msg) do { checks++; if (!(c)) { failures++; printf("FAIL %s\n",msg); } else printf("PASS %s\n",msg); } while (0)
static int at_reentry;
static void add_with_removal(void *device,long status) {
 fake_add_complete(device,status);
 if (status==0) { gdr_remove_device(&ctx,device); at_reentry=sim_n; }
}
int main(void) {
 reset_all(); sim_ret=-1;
 gdr_attach_begin(&ctx,(void*)0x1234,fake_submit,&ring);
 VERIFY(ctx.pending==0,"rejected initial open leaves no pending URB");
 gdr_remove_device(&ctx,(void*)0x1234);
 VERIFY(cancel_calls==0,"failed attach must not cancel an already-rejected URB");
 VERIFY(rm_calls==1,"failed attach removal must acknowledge immediately without future completion");
 reset_all();drive_to_live();
 gdr_remove_device(&ctx,(void*)0x1234);
 VERIFY(ctx.pending==1,"removing context still owns cancelled IN until its completion");
 gdr_attach_begin(&ctx,(void*)0x5678,fake_submit,&ring);
 VERIFY(ctx.device==(void*)0x1234 && ctx.pending==1 && ctx.lifecycle==GDR_LIFE_REMOVING,
        "another attach must not overwrite a nonquiescent context");
 reset_all();ctx.add_complete=add_with_removal;at_reentry=-1;drive_to_live();
 VERIFY(at_reentry>=0,"AddComplete removal reentry was exercised");
 VERIFY(ctx.detached && sim_n==at_reentry,"S5 must not submit an IN after AddComplete reenters removal");
 printf("PARENT_RESULT checks=%d failures=%d\n",checks,failures);
 return failures?1:0;
}
