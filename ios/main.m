/* SPDX-License-Identifier: GPL-3.0-or-later */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <SDL_main.h>
#include "OEMobile.h"

static int OpenEmpireMain(int argc, char **argv) {
    (void)argc; (void)argv;
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER) != 0) {
        SDL_LogCritical(SDL_LOG_CATEGORY_APPLICATION,"SDL initialization failed: %s",SDL_GetError());
        return 1;
    }
    if (!OEApp_Initialize()) return 1;
    OEPlatform_Install(OEApp_Window());
    /* Yield to UIKit. A desktop while(true) loop would block native sheets/lifecycle. */
    if (SDL_iPhoneSetAnimationCallback(OEApp_Window(),1,OEApp_Frame,NULL) != 0) {
        SDL_LogCritical(SDL_LOG_CATEGORY_APPLICATION,"Animation callback failed: %s",SDL_GetError());
        return 1;
    }
    return 0;
}
int main(int argc, char **argv) {
    return SDL_UIKitRunApp(argc,argv,OpenEmpireMain);
}
