#define main historical_close_main
#include "../tests/test_close_contract.c"
#undef main
int main(void){
 test_remove_live_closes(); test_remove_mid_config(); test_three_reattaches();
 test_refused_second_device(); test_no_new_io_after_detach();
 printf("POSITIVE_CLOSE failures=%d\n",g_fail);return g_fail?1:0;
}
