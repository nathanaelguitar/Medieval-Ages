/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "Position.h"
#include "Point.h"
#include <SDL.h>
typedef struct { int point_size; SDL_Color color; SDL_Rect size; } Text;
Text Text_Build(const char *path, int32_t size, uint32_t color);
int32_t Text_Puts(Text, SDL_Renderer *, Point, Position, int32_t alpha, int32_t line, const char *string);
int32_t Text_Printf(Text, SDL_Renderer *, Point, Position, int32_t alpha, int32_t line, const char *fmt, ...);
void Text_Free(Text);
