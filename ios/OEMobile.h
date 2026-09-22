/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef OE_MOBILE_H
#define OE_MOBILE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <SDL.h>
#include "OETouch.h"
#define OE_WIDTH 960
#define OE_HEIGHT 540
#define OE_MAX_ACTIONS 15

typedef struct { int index; char title[80]; } OEAction;

bool OEApp_Initialize(void);
SDL_Window *OEApp_Window(void);
SDL_Renderer *OEApp_Renderer(void);
void OEApp_Frame(void *unused);
bool OEApp_Start(const char *asset_path);
void OEApp_Pause(void);
void OEApp_Resume(void);
void OEApp_End(void);
void OEApp_SetActive(bool active);
bool OEApp_HasGame(void);
bool OEApp_IsLoading(void);
void OEApp_SwitchPlayer(void);
void OEApp_Home(void);
int OEApp_GetActions(OEAction *actions, int capacity);
void OEApp_ChooseAction(int index);

void OEInput_Reset(void);
void OEInput_SetMode(OEMode mode);
void OEInput_SetAction(int index);
int OEInput_Action(void);
void OEInput_ClearAction(void);
void OEInput_ToggleMap(void);
void OEInput_TakePan(int *x, int *y);
void OEInput_Begin(int64_t id, double x, double y, double time);
void OEInput_Move(int64_t id, double x, double y);
void OEInput_End(int64_t id, double x, double y, double time);

/* Implemented in the small Objective-C/UIKit boundary. Main-thread only. */
void OEPlatform_Install(SDL_Window *window);
void OEPlatform_ShowLauncher(const char *message);
void OEPlatform_ShowLoading(void);
void OEPlatform_ShowGame(void);
void OEPlatform_ShowPaused(void);
void OEPlatform_SetHint(const char *message);
#endif
