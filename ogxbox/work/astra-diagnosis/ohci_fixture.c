/* Isolated source-function regression, NOT a physical USB test.
 * ohci_service_td and OHCI constants are extracted verbatim by run_fixture.py.
 * Only external memory/device services below are deterministic test doubles. */
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
typedef struct {int nr;} USBEndpoint;
typedef struct {int unused;} USBDevice;
typedef struct {int status,actual_length,pid;void *buf;size_t len;} USBPacket;
typedef struct {uint8_t usb_buf[8192]; uint32_t async_td,done;bool async_complete;int done_count;USBPacket usb_packet;} OHCIState;
static uint8_t memory[16384];
static USBDevice device;
static USBEndpoint endpoint={2};
static unsigned submits,blocked;
static void ohci_die(OHCIState *s){(void)s;abort();}
static int ohci_read_td(OHCIState *s,uint32_t a,struct ohci_td *t){(void)s;assert(a+sizeof(*t)<=sizeof(memory));memcpy(t,memory+a,sizeof(*t));return 0;}
static int ohci_put_td(OHCIState *s,uint32_t a,struct ohci_td *t){(void)s;memcpy(memory+a,t,sizeof(*t));return 0;}
static int ohci_copy_td(OHCIState *s,struct ohci_td *t,uint8_t *b,size_t n,int d){(void)s;assert(t->cbp+n<=sizeof(memory));if(d==DMA_DIRECTION_TO_DEVICE)memcpy(b,memory+t->cbp,n);else memcpy(memory+t->cbp,b,n);return 0;}
static USBDevice *ohci_find_device(OHCIState *s,uint8_t a){(void)s;(void)a;return &device;}
static USBEndpoint *usb_ep_get(USBDevice *d,int pid,int n){(void)d;(void)pid;endpoint.nr=n;return &endpoint;}
static void usb_packet_setup(USBPacket *p,int pid,USBEndpoint *ep,int stream,uint32_t addr,int short_not_ok,int intr){(void)ep;(void)stream;(void)addr;(void)short_not_ok;(void)intr;p->pid=pid;p->actual_length=0;}
static void usb_packet_addbuf(USBPacket *p,void *b,size_t n){p->buf=b;p->len=n;}
static void usb_handle_packet(USBDevice *d,USBPacket *p){(void)d;submits++;p->status=USB_RET_ASYNC;}
static void usb_device_flush_ep_queue(USBDevice *d,USBEndpoint *ep){(void)d;(void)ep;}
static void ohci_td_pkt(const char *s,uint8_t *b,size_t n){(void)s;(void)b;(void)n;}
#include "ohci_trace_stubs.inc"
#ifdef GUARD_EARLY
#include "ohci_service_td_guarded.inc"
#else
#include "ohci_service_td.inc"
#endif
static struct ohci_ed make_ed(uint32_t td_addr,uint32_t data_addr,size_t n,int dir){
 struct ohci_td td={.flags=OHCI_TD_R,.cbp=data_addr,.next=td_addr+16,.be=data_addr+n-1};
 memcpy(memory+td_addr,&td,sizeof(td));
 return (struct ohci_ed){.flags=(dir<<OHCI_ED_D_SHIFT)|(2<<OHCI_ED_EN_SHIFT)|(64<<OHCI_ED_MPS_SHIFT)|1,.head=td_addr,.tail=td_addr+16};
}
static void dump(const char *label,const uint8_t *p,size_t n){printf("%s",label);for(size_t i=0;i<n;i++)printf(" %02x",p[i]);puts("");}
static void trial(const uint8_t *command,size_t n,const uint8_t *expect){
 OHCIState s={0};memset(memory,0,sizeof(memory));submits=blocked=0;
 struct ohci_ed in=make_ed(0x100,0x1000,64,OHCI_TD_DIR_IN);
 struct ohci_ed out=make_ed(0x200,0x2000,n,OHCI_TD_DIR_OUT);
 memcpy(memory+0x2000,command,n);
 assert(ohci_service_td(&s,&in)==1 && submits==1 && s.async_td==0x100);
 /* OUT must not be submitted while that single async slot is occupied. */
 assert(ohci_service_td(&s,&out)==1 && submits==1 && blocked==1);
 /* Model libusb's real completion contract: copy 8 IN bytes then callback. */
 const uint8_t status[]={3,0x20,0x13,4,0x83,1,0,0};
 memcpy(s.usb_packet.buf,status,sizeof(status));
 s.usb_packet.actual_length=sizeof(status);s.usb_packet.status=USB_RET_SUCCESS;s.async_complete=true;
 /* OUT ED is visited before completed IN ED on this frame. */
 assert(ohci_service_td(&s,&out)==1 && submits==1 && blocked==2);
 assert(ohci_service_td(&s,&in)==0);
 dump("guest IN after pending OUT visit:",memory+0x1000,8);
#ifdef GUARD_EARLY
 (void)expect;
 assert(!memcmp(memory+0x1000,status,8));
#else
 assert(!memcmp(memory+0x1000,expect,8));
#endif
 assert(ohci_service_td(&s,&out)==1 && submits==2 && s.async_td==0x200);
 printf("submits=%u blocked=%u: OUT starts only after IN retirement\n",submits,blocked);
 /* Negative control: retire IN first, with identical command waiting. */
 s=(OHCIState){0};submits=blocked=0;
 in=make_ed(0x100,0x1000,64,OHCI_TD_DIR_IN);out=make_ed(0x200,0x2000,n,OHCI_TD_DIR_OUT);
 assert(ohci_service_td(&s,&in)==1);
 memcpy(s.usb_packet.buf,status,8);s.usb_packet.actual_length=8;s.usb_packet.status=0;s.async_complete=true;
 assert(ohci_service_td(&s,&in)==0);
 assert(!memcmp(memory+0x1000,status,8));
 dump("control (IN retired first):",memory+0x1000,8);
}
int main(void){
 const uint8_t power[]={5,0x20,1,1,0};
 const uint8_t sinit[]={5,0x20,2,15,6,0,0,0,0,0,0,0x55,0x53,0,0,0,0,0,0};
 const uint8_t e1[]={5,0x20,1,1,0,1,0,0},e2[]={5,0x20,2,15,6,0,0,0};
 trial(power,sizeof(power),e1);trial(sinit,sizeof(sinit),e2);
#ifdef GUARD_EARLY
 puts("PASS: test-only early busy guard prevents corruption; single-slot OUT blocking remains; no USB hardware used.");
#else
 puts("PASS: exact historical mixed prefixes reproduced; order control preserves IN; no USB hardware used.");
#endif
 return 0;
}
