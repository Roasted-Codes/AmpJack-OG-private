/* Deterministic USB/DMA doubles around verbatim extracted xemu source.
 * No guest is booted and no physical USB input is used. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#include "ohci_constants.inc"
enum {USB_RET_SUCCESS=0,USB_RET_ASYNC=-6,USB_RET_IOERROR=-5,USB_RET_NODEV=-1,USB_RET_NAK=-2,USB_RET_STALL=-3,USB_RET_BABBLE=-4};
enum {USB_TOKEN_IN=0x69,USB_TOKEN_OUT=0xe1,USB_TOKEN_SETUP=0x2d};
enum {DMA_DIRECTION_TO_DEVICE=0,DMA_DIRECTION_FROM_DEVICE=1};
typedef struct {int unused;} USBDevice;
typedef struct {int nr;USBDevice *dev;} USBEndpoint;
typedef struct {int status,actual_length,pid;void *buf;size_t len;USBEndpoint *ep;} USBPacket;
typedef struct {uint8_t usb_buf[8192]; uint32_t async_td,done,ctl,status,ctrl_cur,ctrl_head,bulk_cur,bulk_head;bool async_complete;int done_count;USBPacket usb_packet;} OHCIState;
typedef struct {int unused;} USBPort;
#define container_of(ptr,type,member) ((type *)((char *)(ptr)-offsetof(type,member)))
static uint8_t memory[16384], dispatched[8192];
static USBDevice device;
static USBEndpoint endpoint={.nr=2};
static unsigned submits,blocked,received,reads;
static size_t dispatched_len;
static int dispatched_pid;
static void ohci_die(OHCIState *s){(void)s;abort();}
static int ohci_read_td(OHCIState *s,uint32_t a,struct ohci_td *t){(void)s;assert(a+sizeof(*t)<=sizeof(memory));memcpy(t,memory+a,sizeof(*t));return 0;}
static int ohci_put_td(OHCIState *s,uint32_t a,struct ohci_td *t){(void)s;memcpy(memory+a,t,sizeof(*t));return 0;}
static int ohci_copy_td(OHCIState *s,struct ohci_td *t,uint8_t *b,size_t n,int d){(void)s;assert(t->cbp+n<=sizeof(memory));if(d==DMA_DIRECTION_TO_DEVICE){memcpy(b,memory+t->cbp,n);reads++;}else{memcpy(memory+t->cbp,b,n);received+=n;}return 0;}
static USBDevice *ohci_find_device(OHCIState *s,uint8_t a){(void)s;(void)a;return &device;}
static USBEndpoint *usb_ep_get(USBDevice *d,int pid,int n){(void)d;(void)pid;endpoint.nr=n;return &endpoint;}
static void usb_packet_setup(USBPacket *p,int pid,USBEndpoint *ep,int stream,uint32_t addr,int short_not_ok,int intr){(void)ep;(void)stream;(void)addr;(void)short_not_ok;(void)intr;p->pid=pid;p->actual_length=0;}
static void usb_packet_addbuf(USBPacket *p,void *b,size_t n){p->buf=b;p->len=n;}
static void usb_handle_packet(USBDevice *d,USBPacket *p){(void)d;submits++;dispatched_len=p->len;dispatched_pid=p->pid;memcpy(dispatched,p->buf,p->len);p->status=USB_RET_ASYNC;}
static void usb_device_flush_ep_queue(USBDevice *d,USBEndpoint *ep){(void)d;(void)ep;}
static void ohci_td_pkt(const char *s,uint8_t *b,size_t n){(void)s;(void)b;(void)n;}
#include "ohci_trace_stubs.inc"
#include "ohci_service_td.inc"
static int ohci_read_ed(OHCIState *s,uint32_t a,struct ohci_ed *e){(void)s;assert(a+sizeof(*e)<=sizeof(memory));memcpy(e,memory+a,sizeof(*e));return 0;}
static int ohci_put_ed(OHCIState *s,uint32_t a,struct ohci_ed *e){(void)s;memcpy(memory+a,e,sizeof(*e));return 0;}
static void usb_cancel_packet(USBPacket *p){(void)p;abort();}
/* work34: candidate guards the (unmodelled, fail-loud) cancel path with this */
static int usb_packet_is_inflight(USBPacket *p){(void)p;abort();}
static void usb_device_ep_stopped(USBDevice *d,USBEndpoint *e){(void)d;(void)e;abort();}
static int ohci_service_iso_td(OHCIState *s,struct ohci_ed *e){(void)s;(void)e;abort();}
#include "ohci_service_ed_list.inc"
static struct ohci_ed make_ed(uint32_t td_addr,uint32_t data_addr,size_t n,int dir,bool rounded,bool control){
 struct ohci_td td={.flags=(rounded?OHCI_TD_R:0)|(dir<<OHCI_TD_DP_SHIFT),.cbp=n?data_addr:0,.next=td_addr+16,.be=n?data_addr+n-1:0};
 memcpy(memory+td_addr,&td,sizeof(td));
 return (struct ohci_ed){.flags=((control?0:dir)<<OHCI_ED_D_SHIFT)|((control?0:2)<<OHCI_ED_EN_SHIFT)|(64<<OHCI_ED_MPS_SHIFT)|1,.head=td_addr,.tail=td_addr+16};
}
static void complete(OHCIState *s,int status,const uint8_t *data,size_t n){
 if(data)memcpy(s->usb_packet.buf,data,n);
 s->usb_packet.actual_length=n;s->usb_packet.status=status;s->async_complete=true;
}
static void trial(size_t n,bool out_first,bool rounded,int status,int queued_dir,bool control){
 const uint8_t power[]={5,0x20,1,1,0};
 const uint8_t sinit[]={5,0x20,2,15,6,0,0,0,0,0,0,0x55,0x53,0,0,0,0,0,0};
 const uint8_t input[]={3,0x20,0x13,4,0x83,1,0,0};
 const uint8_t *command=n==5?power:sinit;
 OHCIState s={0};memset(memory,0,sizeof(memory));submits=blocked=received=reads=0;
 memset(memory+0x1000,0xa5,64);
 struct ohci_ed in=make_ed(0x100,0x1000,64,OHCI_TD_DIR_IN,rounded,control);
 struct ohci_ed out=make_ed(0x200,0x2000,n,queued_dir,true,control);
 struct ohci_ed unrelated=make_ed(0x300,0x3000,8,OHCI_TD_DIR_IN,true,false);
 memcpy(memory+0x2000,command,n);
 assert(ohci_service_td(&s,&in)==1 && submits==1 && s.async_td==0x100);
 /* Revisiting the owning TD before completion must not resubmit it. */
 assert(ohci_service_td(&s,&in)==1 && submits==1 && received==0);
 struct ohci_ed out_before=out;
 struct ohci_td td_before;memcpy(&td_before,memory+0x200,sizeof(td_before));
 assert(ohci_service_td(&s,&out)==1 && submits==1 && blocked==1);
 assert(!memcmp(&out_before,&out,sizeof(out)));
 assert(!memcmp(&td_before,memory+0x200,sizeof(td_before)));
 complete(&s,status,input,sizeof(input));
 /* Unrelated queued IN must neither steal completion nor retire owner. */
 assert(ohci_service_td(&s,&unrelated)==1 && submits==1 && s.async_td==0x100 && received==0);
 if(out_first)assert(ohci_service_td(&s,&out)==1 && submits==1);
 int rc=ohci_service_td(&s,&in);
 assert(s.async_td==0 && !s.async_complete && submits==1);
 if(status==USB_RET_SUCCESS){
  /* Test DMA's actual bytes, not a label or requested packet length. */
  printf("actual IN (%u):",received);for(unsigned i=0;i<received;i++)printf(" %02x",memory[0x1000+i]);puts("");fflush(stdout);
  assert(received==sizeof(input));
  assert(!memcmp(memory+0x1000,input,sizeof(input)));
  for(unsigned i=sizeof(input);i<64;i++)assert(memory[0x1000+i]==0xa5);
  assert(rc==(rounded?0:1));
  struct ohci_td td;memcpy(&td,memory+0x100,sizeof(td));
  assert(td.cbp==0x1008);
  assert(OHCI_BM(td.flags,TD_CC)==(rounded?OHCI_CC_NOERROR:OHCI_CC_DATAUNDERRUN));
 }else{
  assert(received==0 && rc==1);
  for(unsigned i=0;i<64;i++)assert(memory[0x1000+i]==0xa5);
 }
 if(status==USB_RET_NAK){assert((in.head&OHCI_DPTR_MASK)==0x100 && s.done==0);}
 else{assert((in.head&OHCI_DPTR_MASK)==in.tail && s.done==0x100);}
 /* Now the queued command really dispatches, with all 5/19 bytes intact. */
 assert(ohci_service_td(&s,&out)==1 && submits==2 && s.async_td==0x200);
 assert(dispatched_len==n && !memcmp(dispatched,command,n));
 assert(dispatched_pid==(queued_dir==OHCI_TD_DIR_SETUP?USB_TOKEN_SETUP:USB_TOKEN_OUT));
 complete(&s,USB_RET_SUCCESS,NULL,n);
 assert(ohci_service_td(&s,&out)==0 && s.async_td==0 && s.done==0x200);
 assert((out.head&OHCI_DPTR_MASK)==out.tail);
 /* The unrelated TD can then submit and consume its own completion. */
 assert(ohci_service_td(&s,&unrelated)==1 && submits==3);
 complete(&s,USB_RET_SUCCESS,input,sizeof(input));
 assert(ohci_service_td(&s,&unrelated)==0 && !memcmp(memory+0x3000,input,sizeof(input)));
 assert(s.done==0x300 && s.async_td==0);
 puts("PASS: preserved bytes/count, deferred dispatch and rightful retirement");
}
static int drive_list(OHCIState *s,uint32_t head,int kind){
 if(kind){ohci_process_lists(s);return !!(s->status&(OHCI_STATUS_CLF|OHCI_STATUS_BLF));}
 return ohci_service_ed_list(s,head);
}
static void list_trial(bool out_first,int kind){
 const uint8_t input[]={3,0x20,0x13,4,0x83,1,0,0}, command[]={5,0x20,1,1,0};
 OHCIState s={0};memset(memory,0,sizeof(memory));submits=blocked=received=0;
 struct ohci_ed in=make_ed(0x100,0x1000,64,OHCI_TD_DIR_IN,true,false);
 struct ohci_ed out=make_ed(0x200,0x2000,5,OHCI_TD_DIR_OUT,true,false);
 struct ohci_ed other=make_ed(0x300,0x3000,8,OHCI_TD_DIR_IN,true,false);
 memcpy(memory+0x2000,command,5);
 assert(ohci_service_td(&s,&in)==1);
 complete(&s,USB_RET_SUCCESS,input,8);
 /* Real list walker must continue past blocked EDs to the completed owner. */
 if(out_first){out.next=0x500;other.next=0x600;in.next=0;}
 else{in.next=0x400;out.next=0x500;other.next=0;}
 ohci_put_ed(&s,0x400,&out);ohci_put_ed(&s,0x500,&other);ohci_put_ed(&s,0x600,&in);
 uint32_t head=out_first?0x400:0x600;
 if(kind==1){s.ctl=OHCI_CTL_CLE;s.status=OHCI_STATUS_CLF;s.ctrl_head=head;}
 if(kind==2){s.ctl=OHCI_CTL_BLE;s.status=OHCI_STATUS_BLF;s.bulk_head=head;}
 /* Actual callback drives control/bulk; interrupt waits for list service. */
 s.async_complete=false;
 ohci_async_complete_packet(NULL,&s.usb_packet);
 if(!kind)assert(drive_list(&s,head,kind)==1);
 else assert(s.status&(OHCI_STATUS_CLF|OHCI_STATUS_BLF));
 assert(received==8);
 assert(!memcmp(memory+0x1000,input,8));
 ohci_read_ed(&s,0x600,&in);
 assert((in.head&OHCI_DPTR_MASK)==in.tail && s.done==0x100);
 assert(submits==(out_first?1u:2u));
 if(out_first){
  assert(!s.async_td);
  assert(drive_list(&s,head,kind)==1);
 }
 assert(submits==2 && s.async_td==0x200 && dispatched_len==5 && !memcmp(dispatched,command,5));
 complete(&s,USB_RET_SUCCESS,NULL,5);
 assert(drive_list(&s,head,kind)==1);
 assert(s.done==0x200 && submits==3 && s.async_td==0x300);
 complete(&s,USB_RET_SUCCESS,input,8);
 assert(drive_list(&s,head,kind)==1);
 assert(s.done==0x300 && s.async_td==0 && !memcmp(memory+0x3000,input,8));
 assert(drive_list(&s,head,kind)==0);
 puts("PASS: actual ED walker preserves completion and drains unrelated work");
}
int main(int argc,char **argv){
 if(argc==4 && !strcmp(argv[1],"list")){list_trial(atoi(argv[2]),atoi(argv[3]));return 0;}
 assert(argc==7);
 trial(strtoul(argv[1],NULL,0),atoi(argv[2]),atoi(argv[3]),atoi(argv[4]),atoi(argv[5]),atoi(argv[6]));
 return 0;
}
