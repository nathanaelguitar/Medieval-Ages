/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "OEMobile.h"
#include "Input.h"
#include <math.h>
#include <string.h>

static OETouch touch;
static uint8_t keys[SDL_NUM_SCANCODES];
static int action = -1;
static bool show_map;
static double pan_remainder_x, pan_remainder_y;
static const SDL_Scancode action_keys[OE_MAX_ACTIONS] = {
    SDL_SCANCODE_Q, SDL_SCANCODE_W, SDL_SCANCODE_E, SDL_SCANCODE_R, SDL_SCANCODE_T,
    SDL_SCANCODE_A, SDL_SCANCODE_S, SDL_SCANCODE_D, SDL_SCANCODE_F, SDL_SCANCODE_G,
    SDL_SCANCODE_Z, SDL_SCANCODE_X, SDL_SCANCODE_C, SDL_SCANCODE_V, SDL_SCANCODE_B
};
void OEInput_Reset(void) {
    OETouch_SetMode(&touch, OE_SELECT); action = -1;
    show_map = false; pan_remainder_x = pan_remainder_y = 0;
}
void OEInput_SetMode(OEMode mode) { action = -1; OETouch_SetMode(&touch, mode); }
void OEInput_SetAction(int index) {
    if (index < 0 || index >= OE_MAX_ACTIONS) return;
    OETouch_SetMode(&touch, OE_SELECT); action = index;
}
int OEInput_Action(void) { return action; }
void OEInput_ClearAction(void) { action = -1; }
void OEInput_ToggleMap(void) { show_map = !show_map; }
void OEInput_TakePan(int *x, int *y) {
    double dx, dy; OETouch_TakePan(&touch, &dx, &dy);
    pan_remainder_x += dx; pan_remainder_y += dy;
    *x = (int)lround(pan_remainder_x); *y = (int)lround(pan_remainder_y);
    pan_remainder_x -= *x; pan_remainder_y -= *y;
}
void OEInput_Begin(int64_t id, double x, double y, double time) { OETouch_Begin(&touch,id,x,y,time); }
void OEInput_Move(int64_t id, double x, double y) { OETouch_Move(&touch,id,x,y); }
void OEInput_End(int64_t id, double x, double y, double time) { OETouch_End(&touch,id,x,y,time); }

Input Input_Pump(Input in) {
    /* Drain ALL events. The original code read an uninitialized event on empty polls. */
    SDL_Event event = {0};
    while (SDL_PollEvent(&event)) {
        if (event.type == SDL_QUIT) in.done = true;
    }
    int key_count = 0;
    const uint8_t *hardware = SDL_GetKeyboardState(&key_count);
    memset(keys,0,sizeof(keys));
    if (hardware) memcpy(keys,hardware,(size_t)(key_count < SDL_NUM_SCANCODES ? key_count : SDL_NUM_SCANCODES));
    if (keys[SDL_SCANCODE_ESCAPE] || keys[SDL_SCANCODE_END]) in.done = true;
    if (action >= 0) { keys[SDL_SCANCODE_LALT] = 1; keys[action_keys[action]] = 1; }
    keys[SDL_SCANCODE_TAB] |= show_map;
    OETouchSample sample = OETouch_Next(&touch);
    in.key = keys;
    in.cursor.x = (int32_t)lround(sample.x); in.cursor.y = (int32_t)lround(sample.y);
    in.l = sample.left; in.r = sample.right;
    in.ld = sample.left_down; in.lu = sample.left_up;
    in.rd = sample.right_down; in.ru = sample.right_up;
    in.ll = in.l; in.lr = in.r;
    return in;
}
Input Input_Ready(void) {
    Input in = {0}; in.key = keys;
    return in;
}
