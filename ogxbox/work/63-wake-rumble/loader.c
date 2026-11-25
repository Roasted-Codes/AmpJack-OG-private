/* SPDX-License-Identifier: GPL-3.0-or-later
 * AJ43 matched-pair pre-entry loader (W63 copy: entry argument = option flags,
 * six extra resolved-slot checks for the log file I/O + KeTickCount). No persistent globals or title pointers.
 * The on-disk envelope is deliberately NOT H2S2: the frozen ELF has code at
 * offset zero and cdecl entry ignores its argument, unlike H2S2 stdcall(host).
 * Preserve every original ELF virtual offset; inject its real BSS host first.
 */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef int s32;
#define ST __attribute__((stdcall))
#define V(p) (*(volatile u32 *)(p))
#include "pins.h"
#include "sha256.inc"
static void cp(u8*d,const u8*s,u32 n){while(n--)*d++=*s++;}
static int eq(const u8*a,const u8*b,u32 n){while(n--)if(*a++!=*b++)return 0;return 1;}
static int digest(const u8*p,u32 n,const u8*want){u8 got[32];sha(p,n,got);return eq(got,want,32);}
static u32 get(const u8*p){return (u32)p[0]|((u32)p[1]<<8)|((u32)p[2]<<16)|((u32)p[3]<<24);}
static int slot(u32 p,u32 ord){u32 v=V(p);return v>=0x80010000u && v!=(0x80000000u|ord);}
static int title_ok(void){
 u8 h[0x178];u32 i;
 cp(h,(const u8*)0x10000,sizeof(h));
 for(i=0;i<2;i++){
  u32 off=header_fields[i][0], live=get(h+off);
  if(live!=header_fields[i][1] && live!=header_fields[i][2])return 0;
  cp(h+off,(const u8*)&header_fields[i][1],4);
 }
 if(!digest(h,sizeof(h),header_sha))return 0;
 /* Header digest includes the certificate pointer; compare title ID itself. */
 if(V(CERT_VA+8)!=0x4d530064)return 0;
 for(i=0;i<7;i++)if(!eq((u8*)sites[i].va,sites[i].orig,sites[i].len))return 0;
 for(i=0;i<METHOD_COUNT;i++)if(!eq((u8*)methods[i].va,methods[i].orig,10))return 0;
 for(i=0;i<SLOT_COUNT;i++)if(!slot(slots[i][0],slots[i][1]))return 0;
 return 1;
}
static u8 *alloc(u32 n){return (*(u8*(ST **)(u32,u32,u32,u32,u32))0x41b640)(n,0,~0u,0,4);}
static void release(u8*p){(*(void(ST **)(void*))0x41b60c)(p);}
static s32 close_file(u32 h){return (*(s32(ST **)(u32))0x41b624)(h);}
static s32 read_file(u32 h,u8*p,u32 n,u32 *io,const u32 *off){
 io[0]=io[1]=0;
 return (*(s32(ST **)(u32,u32,u32,u32,u32*,u8*,u32,const u32*))0x41b6ac)(h,0,0,0,io,p,n,off);
}
/* Only reclaim allocations after all owned hook bytes are confirmed original.
 * A permanent write/readback failure is unrecoverable: retain reachable resident
 * memory and fail-stop pre-entry, NEVER return into partial/dangling hooks. */
__attribute__((noreturn,noinline)) static void unsafe_stop(void){
 __asm__ volatile("cli\n1: hlt\njmp 1b");__builtin_unreachable();
}
static int hooks_ok(u8 *b){
 u32 i;u8 p[5];p[0]=0xe9;
 for(i=0;i<7;i++){
  u32 rel=(u32)b+sites[i].off-sites[i].va-5;
  cp(p+1,(u8*)&rel,4);
  if(!eq((u8*)sites[i].va,p,5) || !eq((u8*)sites[i].va+5,sites[i].orig+5,sites[i].len-5))return 0;
 }
 return V(b+MODULE_OFF+STATUS_HOOKS)==191 && V(b+MODULE_OFF+STATUS_FAILED)==0;
}
static void restore_owned(void){
 u32 i,j;int ok=0;
 /* Single-thread pre-entry; preflight saved exact originals at every owned
  * site. Includes the CURRENT partial site the baseline installer omits. */
 for(j=0;j<3 && !ok;j++){
  for(i=0;i<7;i++){
   volatile u8*d=(volatile u8*)sites[i].va;u32 k;
   for(k=0;k<5;k++)d[k]=sites[i].orig[k];
  }
  ok=1;
  for(i=0;i<7;i++)if(!eq((u8*)sites[i].va,sites[i].orig,sites[i].len))ok=0;
 }
 if(!ok)unsafe_stop();
}
/* Compiler emits a real cdecl indirect call and caller-side argument cleanup.
 * Harness observes this actual function, then executes the untouched ELF entry. */
__attribute__((noinline)) static int adapter_call(u8 *b,u32 flags){
 return ((int(*)(u32)) (b+ENTRY_OFF))(flags);   /* W63: bit0 = write log */
}
extern u8 boot_end[] __attribute__((visibility("hidden")));
static int region_ok(u8 *p,u32 n,u8*t){
 u32 a=(u32)p,z=a+n;
 return a>=0x10000 && z>a && !(a<TITLE_END && z>0x10000) &&
        !(a<(u32)t+15193 && z>(u32)t);
}
void trainer_main(u8*t){
 u32 op=get(t+0x0a),sz=get(t),i,h=0,io[2],off[2]={0,0};
 u8 *f=0,*b=0; s32 rc;u8 extra;u32 flags;
 volatile struct {u16 len,max; const char *s;} name;
 struct {u32 root;void *name;u32 flags;} oa={0,(void*)&name,0x40};
 name.len=sizeof(payload_path)-1;name.max=sizeof(payload_path);name.s=payload_path;
 /* No cross-title state; retail/relaunch/off gates happen before I/O or alloc. */
 if(sz>15193 || op<(u32)boot_end-(u32)t || op>=sz || t[op]!=1)return;
 if(!title_ok())return;
 flags=(op+1<sz && t[op+1]==1)?1u:0u;   /* W63: XBTF option [1] */
 rc=(*(s32(ST **)(u32*,u32,void*,u32*,u32,u32))0x41b654)(&h,0x80100000,&oa,io,1,0x60);
 if(rc<0)return;
 f=alloc(FILE_ALLOC);
 if(!f)goto close;
 if(!region_ok(f,FILE_ALLOC,t))goto close;
 /* Exact size plus EOF probe prevents oversized appended code. */
 if(read_file(h,f,FILE_SIZE,io,off)<0 || io[1]!=FILE_SIZE)goto close;
 off[0]=FILE_SIZE;
 rc=read_file(h,&extra,1,io,off);
 if(io[1]!=0 || (rc!=0 && (u32)rc!=0xc0000011u))goto close;
 if(!digest(f,FILE_SIZE,payload_sha) || !eq(f,(u8*)expected_header,64))goto close;
 /* Even a malformed MATCHED build cannot relocate outside initialized image,
  * use an extra entry or overflow base math. Fixed expected metadata above. */
 for(i=0;i<RELOC_COUNT;i++){
  u32 r=get(f+64+IMAGE_SIZE+4*i);
  if(r>IMAGE_SIZE-4 || r!=reloc_offsets[i] || get(f+64+r)>=MEM_END)goto close;
 }
 b=alloc(RESIDENT_ALLOC);
 if(!b)goto close;
 if(!region_ok(b,RESIDENT_ALLOC,t) ||
    ((u32)b<(u32)f+FILE_ALLOC && (u32)b+RESIDENT_ALLOC>(u32)f))goto free_b;
 /* Refuse if title changed since file I/O; no title writes yet. */
 if(!title_ok())goto free_b;
 cp(b,f+64,IMAGE_SIZE);
 if(!eq(b,f+64,IMAGE_SIZE))goto free_b;
 for(i=IMAGE_SIZE;i<RESIDENT_ALLOC;i++)b[i]=0;
 for(i=IMAGE_SIZE;i<RESIDENT_ALLOC;i++)if(*(volatile u8*)(b+i)!=0)goto free_b;
 for(i=0;i<RELOC_COUNT;i++){
  u32 r=get(f+64+IMAGE_SIZE+4*i),want=get(f+64+r)+(u32)b;
  V(b+r)=want;
  if(V(b+r)!=want)goto free_b;
 }
 release(f);f=0;
 close_file(h);h=0;
 /* All BSS is zero BEFORE the first 44-byte host write. */
 for(i=0;i<11;i++)V(b+MODULE_OFF+4*i)=host_values[i];
 for(i=0;i<11;i++)if(V(b+MODULE_OFF+4*i)!=host_values[i])goto free_b;
 rc=adapter_call(b,flags);
 if(rc==0 && hooks_ok(b))return; /* resident remains title-owned, not persisted */
 restore_owned();
free_b:
 release(b);
close:
 if(f)release(f);
 if(h)close_file(h);
}
