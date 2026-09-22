/* SPDX-License-Identifier: GPL-3.0-or-later */
#define _POSIX_C_SOURCE 200809L
#include "OETouch.h"
#include "OEClock.h"
#include "OEAssets.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static unsigned tests;
#define CHECK(test) do { assert(test); ++tests; } while (0)
static OETouchSample drain(OETouch *t, int *ld, int *lu, int *rd, int *ru) {
    OETouchSample s = {0};
    while (t->count) {
        s = OETouch_Next(t);
        *ld += s.left_down; *lu += s.left_up; *rd += s.right_down; *ru += s.right_up;
    }
    return s;
}
static void tap(bool command, double duration) {
    OETouch t; OETouch_Init(&t);
    if (command) OETouch_SetMode(&t, OE_COMMAND);
    OETouch_Begin(&t, 1, 100, 120, 10);
    OETouch_End(&t, 1, 100, 120, 10 + duration);
    int ld=0,lu=0,rd=0,ru=0;
    OETouchSample s = drain(&t,&ld,&lu,&rd,&ru);
    bool right = command || duration >= 0.45;
    CHECK(ld == !right && lu == !right && rd == right && ru == right);
    CHECK(!s.left && !s.right && s.x == 100 && s.y == 120);
}
static void gestures(void) {
    tap(false, 0.01); tap(false, 0.7); tap(true, 0.01);
    OETouch t; OETouch_Init(&t);
    OETouch_Begin(&t,1,10,10,0); OETouch_Move(&t,1,40,45);
    int ld=0,lu=0,rd=0,ru=0;
    OETouchSample s = drain(&t,&ld,&lu,&rd,&ru);
    CHECK(ld == 1 && lu == 0 && s.left);
    OETouch_End(&t,1,50,60,1);
    s = drain(&t,&ld,&lu,&rd,&ru);
    CHECK(lu == 1 && ru == 0 && !s.left && s.x == 50);
    OETouch_Begin(&t,1,100,100,2); OETouch_Move(&t,1,130,100);
    drain(&t,&ld,&lu,&rd,&ru);
    OETouch_Begin(&t,2,150,100,2.1);
    s = OETouch_Next(&t);
    CHECK(s.cancelled && !s.left_up && !s.left);
    OETouch_Move(&t,1,150,100); OETouch_Move(&t,2,170,110);
    double dx=0,dy=0; OETouch_TakePan(&t,&dx,&dy);
    CHECK(dx == 20 && dy == 5);
    OETouch_End(&t,1,150,100,3); OETouch_End(&t,2,170,110,3);
    ld=lu=rd=ru=0; drain(&t,&ld,&lu,&rd,&ru);
    CHECK(ld+lu+rd+ru == 0);
    OETouch_SetMode(&t,OE_PAN); OETouch_Next(&t);
    OETouch_Begin(&t,1,10,10,0); OETouch_Move(&t,1,20,40);
    OETouch_End(&t,1,30,50,1); OETouch_TakePan(&t,&dx,&dy);
    CHECK(dx == 20 && dy == 40);
    drain(&t,&ld,&lu,&rd,&ru); CHECK(ld+lu+rd+ru == 0);
    OETouch_Init(&t);
    OETouch_Begin(&t,1,NAN,0,0); CHECK(t.count == 0);
    for (int i=0;i<400;i++) { OETouch_Begin(&t,1,10,10,i); OETouch_End(&t,1,10,10,i+0.01); }
    CHECK(t.overflow_count > 0 && t.count <= OE_TOUCH_QUEUE_CAPACITY);
    OETouch_Cancel(&t); s=OETouch_Next(&t);
    CHECK(s.cancelled && !s.left_up && !s.right_up);
    /* Untracked third fingers cannot release or move tracked fingers. */
    OETouch_Init(&t); OETouch_Begin(&t,11,0,0,0); OETouch_Begin(&t,22,10,10,0);
    OETouch_Begin(&t,33,20,20,0); OETouch_End(&t,33,100,100,1);
    CHECK(t.fingers[0].active && t.fingers[1].active);
}
static void clock_tests(void) {
    OEClock c={0}; CHECK(OEClock_Advance(&c,0)==0);
    CHECK(OEClock_Advance(&c,0.014)==0);
    CHECK(OEClock_Advance(&c,0.015)==1);
    CHECK(OEClock_Advance(&c,0.060)==3);
    CHECK(OEClock_Advance(&c,200)==8);
    OEClock_Reset(&c); CHECK(OEClock_Advance(&c,300)==0);
    CHECK(OEClock_Advance(&c,NAN)==0);
    CHECK(OEClock_Advance(&c,200)==0);
    OEClock_Reset(&c); OEClock_Advance(&c,0);
    unsigned n=0; for(int i=1;i<=120;i++) n += OEClock_Advance(&c,i/120.0);
    CHECK(n==66);
    OEClock_Reset(&c); OEClock_Advance(&c,0);
    n=0; for(int i=1;i<=60;i++) n += OEClock_Advance(&c,i/60.0);
    CHECK(n==66);
}

static void put32(unsigned char *p, uint32_t value) {
    for(int i=0;i<4;++i) p[i]=(unsigned char)(value >> (i*8));
}
static void write_bytes(const char *path, const unsigned char *bytes, size_t count) {
    FILE *f=fopen(path,"wb"); assert(f); assert(fwrite(bytes,1,count,f)==count); fclose(f);
}
static void asset_tests(void) {
    char path[]="/tmp/openempire-drs-XXXXXX";
    int fd=mkstemp(path); assert(fd>=0); close(fd);
    unsigned char bytes[92]={0}; char error[512];
    put32(bytes+56,1); put32(bytes+60,88); memcpy(bytes+64," pls",4);
    put32(bytes+68,76); put32(bytes+72,1);
    put32(bytes+76,100); put32(bytes+80,88); put32(bytes+84,4);
    write_bytes(path,bytes,sizeof(bytes));
    CHECK(OEAssets_CheckDRS(path,0,error,sizeof(error)));
    CHECK(!OEAssets_CheckDRS(path,1,error,sizeof(error)));
    write_bytes(path,bytes,91); CHECK(!OEAssets_CheckDRS(path,0,error,sizeof(error)));
    put32(bytes+80,UINT32_MAX); write_bytes(path,bytes,sizeof(bytes));
    CHECK(!OEAssets_CheckDRS(path,0,error,sizeof(error)));
    put32(bytes+80,88); put32(bytes+72,UINT32_MAX); write_bytes(path,bytes,sizeof(bytes));
    CHECK(!OEAssets_CheckDRS(path,0,error,sizeof(error)));
    put32(bytes+72,1); put32(bytes+56,17); write_bytes(path,bytes,sizeof(bytes));
    CHECK(!OEAssets_CheckDRS(path,0,error,sizeof(error)));
    put32(bytes+56,1); put32(bytes+68,77); write_bytes(path,bytes,sizeof(bytes));
    CHECK(!OEAssets_CheckDRS(path,0,error,sizeof(error)));
    put32(bytes+68,76); memcpy(bytes+64,"anib",4); write_bytes(path,bytes,sizeof(bytes));
    CHECK(!OEAssets_CheckDRS(path,0,error,sizeof(error)));
    remove(path);
}

static void path_tests(void) {
    char path[12];
    CHECK(OEAssets_EnginePath("/data",path,sizeof(path)) && strcmp(path,"/data/")==0);
    CHECK(OEAssets_EnginePath("/data/",path,sizeof(path)) && strcmp(path,"/data/")==0);
    CHECK(OEAssets_EnginePath("/",path,sizeof(path)) && strcmp(path,"/")==0);
    CHECK(!OEAssets_EnginePath("",path,sizeof(path)));
    CHECK(!OEAssets_EnginePath(NULL,path,sizeof(path)));
    CHECK(!OEAssets_EnginePath("/data",path,6));
    CHECK(OEAssets_EnginePath("/data",path,7) && strcmp(path,"/data/")==0);
    CHECK(!OEAssets_EnginePath("/data",NULL,7));
}

int main(void) {
    gestures(); clock_tests(); asset_tests(); path_tests();
    char error[512]; CHECK(!OEAssets_CheckDirectory("/certainly/not/a/data/folder",error,sizeof(error)));
    CHECK(strstr(error,"DRS") != NULL);
    CHECK(!OEAssets_CheckDirectory(NULL,error,sizeof(error)));
    printf("PASS: %u portable assertions\n",tests);
    return 0;
}
