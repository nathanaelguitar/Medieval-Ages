/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "OEMobile.h"
#include "OEClock.h"
#include "OEAssets.h"
#include "Video.h"
#include "Units.h"
#include "Config.h"
#include "Button.h"
#include "Buttons.h"
#include "Util.h"
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    Data data;
    Map map;
    Grid grid;
    Units units, floats;
    Field field;
    Overview overview;
    Input input;
    int32_t cycles;
    char path[4096], error[512];
} OESession;
static Video video;
static OESession *session;
static SDL_Thread *loader;
/* Publication uses acquire/release; the renderer never reads half-loaded assets. */
static atomic_int load_state; /* 0 idle, 1 loading, 2 ready, -1 preflight error */
static bool active = true, paused = true;
static OEClock clock_state;

static int LoadSession(void *context) {
    OESession *g = context;
    if (!OEAssets_CheckDirectory(g->path,g->error,sizeof(g->error))) {
        atomic_store_explicit(&load_state,-1,memory_order_release); return 1;
    }
    g->data = Data_Load(g->path);
    g->overview = Overview_Make(OE_WIDTH,OE_HEIGHT);
    g->overview.color = COLOR_BLU;
    g->overview.users = 3;       /* Two settlements; slot 2 is a non-rendered spectator. */
    g->overview.spectator = COLOR_GRN;
    g->overview.seed = 1337;
    Util_Srand(g->overview.seed);
    Unit_SetIdNext(0); Unit_SetCommandGroupNext(0);
    g->map = Map_Make(g->data.terrain);
    g->grid = Grid_Make(g->map.size,g->map.tile_width,g->map.tile_height);
    g->units = Units_Make(g->grid.size,video.cpu_count,CONFIG_UNITS_MAX,COLOR_BLU);
    g->floats = Units_Make(g->grid.size,video.cpu_count,CONFIG_UNITS_FLOAT_BUFFER,COLOR_BLU);
    for (int i=0;i<2;++i) {
        g->units.share[i].status.age = AGE_1;
        g->units.share[i].status.wood = 750;
        g->units.share[i].status.food = 750;
        g->units.share[i].status.gold = 750;
        g->units.share[i].status.stone = 750;
    }
    g->units = Units_Generate(g->units,g->map,g->grid,g->data.graphics,3,COLOR_GRN);
    g->overview.pan = Units_GetFirstTownCenterPan(g->units,g->grid);
    g->field = Field_Make(g->map.size);
    atomic_store_explicit(&load_state,2,memory_order_release);
    return 0;
}
bool OEApp_Initialize(void) {
    SDL_SetHint(SDL_HINT_RENDER_DRIVER,"metal");
    SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY,"linear");
    SDL_SetHint(SDL_HINT_TOUCH_MOUSE_EVENTS,"0");
    SDL_SetHint(SDL_HINT_MOUSE_TOUCH_EVENTS,"0");
    SDL_SetHint(SDL_HINT_ORIENTATIONS,"LandscapeLeft LandscapeRight");
    video = Video_Make(OE_WIDTH,OE_HEIGHT,"OpenEmpire");
    OEInput_Reset();
    return video.window && video.renderer && video.canvas;
}
SDL_Window *OEApp_Window(void) { return video.window; }
SDL_Renderer *OEApp_Renderer(void) { return video.renderer; }
bool OEApp_IsLoading(void) { return atomic_load_explicit(&load_state,memory_order_acquire) == 1; }
bool OEApp_HasGame(void) { return session && atomic_load_explicit(&load_state,memory_order_acquire) == 0; }
bool OEApp_Start(const char *path) {
    if (session) return false;
    char engine_path[sizeof(((OESession *)0)->path)];
    if (!OEAssets_EnginePath(path,engine_path,sizeof(engine_path))) {
        OEPlatform_ShowLauncher("The asset folder path is missing or too long."); return false;
    }
    session = calloc(1,sizeof(*session));
    if (!session) { OEPlatform_ShowLauncher("Not enough memory to start a game."); return false; }
    snprintf(session->path,sizeof(session->path),"%s",engine_path);
    atomic_store_explicit(&load_state,1,memory_order_release);
    paused = true; OEInput_Reset(); OEPlatform_ShowLoading();
    loader = SDL_CreateThread(LoadSession,"OpenEmpire asset loader",session);
    if (!loader) {
        free(session); session=NULL; atomic_store(&load_state,0);
        OEPlatform_ShowLauncher(SDL_GetError()); return false;
    }
    return true;
}
void OEApp_Pause(void) { paused=true; OEClock_Reset(&clock_state); OEInput_Reset(); }
void OEApp_Resume(void) {
    if (!OEApp_HasGame()) return;
    paused=false; OEClock_Reset(&clock_state); OEInput_Reset();
    session->input=Input_Ready(); OEPlatform_ShowGame();
}
void OEApp_SetActive(bool value) {
    active=value;
    if (!value) OEApp_Pause();
    else if (OEApp_HasGame()) OEPlatform_ShowPaused();
}
void OEApp_End(void) {
    if (!OEApp_HasGame()) return;
    OEApp_Pause();
    /* Upstream Units_Free does not release per-unit paths. */
    Units_FreeAllPathsForRecovery(session->units);
    Units_FreeAllPathsForRecovery(session->floats);
    Field_Free(session->field);
    Units_Free(session->floats); Units_Free(session->units);
    Map_Free(session->map); Data_Free(session->data);
    free(session); session=NULL;
    OEPlatform_ShowLauncher("Game ended. Imported assets remain on this device.");
}
void OEApp_Home(void) {
    if (OEApp_HasGame()) session->overview.pan=Units_GetFirstTownCenterPan(session->units,session->grid);
}
void OEApp_SwitchPlayer(void) {
    if (!OEApp_HasGame()) return;
    Color color = session->overview.color == COLOR_BLU ? COLOR_RED : COLOR_BLU;
    session->overview.color=color; session->units.color=color; session->floats.color=color;
    session->overview.share=session->units.share[color];
    OEInput_Reset(); OEApp_Home();
    OEPlatform_SetHint(color == COLOR_BLU ? "Controlling Blue. The other settlement is idle." : "Controlling Red. The other settlement is idle.");
}
static const char *ActionName(Button b) {
    if (b.icon_type == ICONTYPE_BUILD) {
        switch (b.index) {
            case ICONBUILD_HOUSE: return "House";
            case ICONBUILD_OUTPOST: return "Outpost";
            case ICONBUILD_MILL: return "Mill";
            case ICONBUILD_STONE_CAMP: return "Mining camp";
            case ICONBUILD_LUMBER_CAMP: return "Lumber camp";
            case ICONBUILD_TOWN_CENTER: return "Town center";
            case ICONBUILD_BARRACKS: return "Barracks";
            case ICONBUILD_STABLE: return "Stable";
            case ICONBUILD_CASTLE: return "Castle";
        }
    }
    if (b.icon_type == ICONTYPE_UNIT) {
        switch (b.index) {
            case ICONUNIT_MALE_VILLAGER: return "Train male villager";
            case ICONUNIT_FEMALE_VILLAGER: return "Train female villager";
            case ICONUNIT_MILITIA: return "Train militia / upgraded unit";
            case ICONUNIT_SPEARMAN: return "Train spearman / pikeman";
            case ICONUNIT_SCOUT: return "Train scout";
        }
    }
    if (b.icon_type == ICONTYPE_TECH) {
        switch (b.index) {
            case ICONTECH_AGE_2: return "Advance age";
            case ICONTECH_RESEARCH_MAN_AT_ARMS: return "Upgrade militia";
            case ICONTECH_RESEARCH_PIKEMAN: return "Upgrade spearmen";
        }
    }
    if (b.icon_type == ICONTYPE_COMMAND) return "Aggressive move";
    return "Action";
}
int OEApp_GetActions(OEAction *out, int capacity) {
    if (!OEApp_HasGame() || !out || capacity <= 0) return 0;
    Share share=session->units.share[session->units.color];
    Buttons buttons=Buttons_FromMotive(share.motive,share.status.age);
    int count=buttons.count;
    if (count > capacity) count=capacity;
    if (count > OE_MAX_ACTIONS) count=OE_MAX_ACTIONS;
    for (int i=0;i<count;++i) {
        out[i].index=i;
        snprintf(out[i].title,sizeof(out[i].title),"%s",ActionName(buttons.button[i]));
    }
    return count;
}
void OEApp_ChooseAction(int index) {
    OEAction actions[OE_MAX_ACTIONS];
    int n=OEApp_GetActions(actions,OE_MAX_ACTIONS);
    if (index < 0 || index >= n) return;
    OEApp_Resume(); OEInput_SetAction(index);
    OEPlatform_SetHint("Tap a map location to use the action. Train units next to their selected building. Select cancels.");
}
static void Step(void) {
    OESession *g=session;
    g->input=Input_Pump(g->input);
    if (g->input.done) { OEApp_Pause(); OEPlatform_ShowPaused(); return; }
    Field_Clear(g->field); Units_Field(g->units,g->map,g->field);
    Color color=g->overview.color;
    g->overview=Overview_Update(g->overview,g->input,0,g->cycles,0,g->units.share[color],0,false);
    int dx,dy; OEInput_TakePan(&dx,&dy);
    g->overview.pan.x-=dx; g->overview.pan.y-=dy;
    /* In-process packet dispatch uses the actual original command/selection code. */
    Packet packet={0}; packet.overview[color]=g->overview;
    g->units=Units_PacketService(g->units,g->data.graphics,packet,g->grid,g->map,g->field);
    g->units=Units_Caretake(g->units,g->data.graphics,g->grid,g->map,g->field,false);
    g->overview.share=g->units.share[color];
    if (g->input.lu && OEInput_Action() >= 0) {
        OEInput_ClearAction();
        OEPlatform_SetHint("Tap to select. Hold or use Order to move, gather, or attack. Two fingers pan.");
    }
    ++g->cycles;
}
void OEApp_Frame(void *unused) {
    (void)unused;
    if (!active) { OEClock_Reset(&clock_state); return; }
    SDL_PumpEvents();
    int state=atomic_load_explicit(&load_state,memory_order_acquire);
    if (state == 2 || state == -1) {
        SDL_WaitThread(loader,NULL); loader=NULL;
        atomic_store_explicit(&load_state,0,memory_order_release);
        if (state == -1) {
            char error[512]; snprintf(error,sizeof(error),"%s",session->error);
            free(session); session=NULL; OEPlatform_ShowLauncher(error);
        } else OEApp_Resume();
    }
    if (OEApp_HasGame()) {
        double now=(double)SDL_GetPerformanceCounter() / (double)SDL_GetPerformanceFrequency();
        if (!paused) {
            unsigned steps=OEClock_Advance(&clock_state,now);
            for (unsigned i=0;i<steps && !paused;++i) Step();
        } else OEClock_Reset(&clock_state);
        if (paused) return; /* Keep last frame visible beneath the pause UI. */
        OESession *g=session;
        uint32_t start=SDL_GetTicks();
        g->floats=Units_Float(g->floats,g->units,g->data.graphics,g->overview,g->grid,g->map,g->units.share[g->units.color].motive);
        Video_Draw(video,g->data,g->map,g->units,g->floats,g->overview,g->grid);
        Video_Render(video,g->units,g->overview,g->map,(int32_t)(SDL_GetTicks()-start),g->cycles,0);
    } else {
        SDL_SetRenderDrawColor(video.renderer,13,20,28,255);
        SDL_RenderClear(video.renderer); SDL_RenderPresent(video.renderer);
    }
}
