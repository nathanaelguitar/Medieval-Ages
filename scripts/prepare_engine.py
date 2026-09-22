#!/usr/bin/env python3
"""Prepare a build-only copy of the pinned upstream engine. Never alter the source checkout."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import sys

UPSTREAM_COMMIT = "466fc251f1bcad69c917c31c94ffa4c069700cc2"
# Git blob IDs verified through GitHub's contents API, not guessed file checksums.
BLOBS = {
    "Video.c": "910db5fbfc5edf387252a56b8658775d34f399bf",
    "Registrar.c": "a1c7dd2220f479bf4c840fd0d4d01db857acb85a",
    "Drs.c": "c0c18667147aa0600c59695a4cd811e9d648b40e",
    "Table.c": "543e07ab7ea06a6461b7010fb77110051ac0b39c",
    "Units.c": "b61be08ee79e4861b0f9b81686b9da74b0ee4e74",
    "Blendomatic.c": "1fcf1211e36eb199bd478aa10d7e6145ec8f01ff",
    "Text.h": "be77772a74ae07103e7e50b696aacff3bb29777a",
}

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()

def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"Patch anchor must match once, not {source.count(old)}: {old[:100]!r}")
    return source.replace(old, new, 1)

def replace_function(source: str, name: str, new: str) -> str:
    # Upstream's top-level braces are in column zero; nested braces are indented.
    pattern = re.compile(r"^[^\n]*\b" + re.escape(name) + r"\([^\n]*\)\n\{.*?^\}", re.M | re.S)
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise ValueError(f"Expected one function {name}; found {len(matches)}")
    match = matches[0]
    return source[:match.start()] + new.strip() + source[match.end():]

VIDEO_MAKE = r'''
Video Video_Make(const int32_t xres, const int32_t yres, const char* const title)
{
    /* iOS port: the CPU canvas is uploaded through SDL's Metal renderer. */
    Video video = {0};
    video.window = SDL_CreateWindow(title, SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED,
        xres, yres, SDL_WINDOW_SHOWN | SDL_WINDOW_BORDERLESS | SDL_WINDOW_ALLOW_HIGHDPI);
    if(video.window)
        video.renderer = SDL_CreateRenderer(video.window, -1,
            SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if(video.renderer)
    {
        SDL_RenderSetLogicalSize(video.renderer, xres, yres);
        video.canvas = SDL_CreateTexture(video.renderer, SURFACE_PIXEL_FORMAT,
            SDL_TEXTUREACCESS_STREAMING, xres, yres);
    }
    if(!video.window || !video.renderer || !video.canvas)
    {
        SDL_LogCritical(SDL_LOG_CATEGORY_APPLICATION, "Video initialization: %s", SDL_GetError());
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "OpenEmpire", SDL_GetError(), video.window);
        abort();
    }
    video.title = title;
    video.text = Text_Build(NULL, 24, 0x00FFFFFF);
    video.text_small = Text_Build(NULL, 12, 0x00FFFFFF);
    video.xres = xres;
    video.yres = yres;
    video.middle = (Point){xres / 2, yres / 2};
    video.bot_rite = (Point){xres, yres};
    video.bot_left = (Point){0, yres};
    video.top_rite = (Point){xres, 0};
    video.top_left = (Point){0, 0};
    video.cpu_count = SDL_GetCPUCount() > 1 ? 2 : 1;
    return video;
}
'''
VIDEO_FREE = r'''
void Video_Free(const Video video)
{
    /* Text textures and canvas must die before the renderer, then the window. */
    Text_Free(video.text);
    Text_Free(video.text_small);
    SDL_DestroyTexture(video.canvas);
    SDL_DestroyRenderer(video.renderer);
    SDL_DestroyWindow(video.window);
    if(video.cursor) SDL_FreeCursor(video.cursor);
}
'''
LOAD_COLORS = r'''
static void LoadColors(const Registrar registrar, const Slp slp, const Palette palette, const int32_t file)
{
    /* Offline iOS mode renders Blue, Red and Gaia only. The other calloc'd
       animation slots remain empty and are safe for Animation_Free. This avoids
       decoding six unused palettes and thousands of short-lived load threads. */
    const Color colors[] = { COLOR_BLU, COLOR_RED, COLOR_GAIA };
    for(int32_t i = 0; i < (int32_t)(sizeof(colors) / sizeof(colors[0])); ++i)
    {
        ColorNeedle needle = {0};
        needle.registrar = registrar;
        needle.slp = slp;
        needle.palette = palette;
        needle.file = file;
        needle.color = colors[i];
        needle.index = colors[i];
        LoadColorNeedle(&needle);
    }
}
'''

def patch(name: str, text: str) -> str:
    if name == "Video.c":
        text = replace_function(text, "Video_Make", VIDEO_MAKE)
        text = replace_function(text, "Video_Free", VIDEO_FREE)
        text = replace_once(text,
            "#if 1\n    Vram_DrawDebugDimensionGrids",
            "#if 0 /* iOS: debug geometry is not gameplay UI. */\n    Vram_DrawDebugDimensionGrids")
        text = replace_once(text,
            "    PrintPerformanceMonitor(video, units, dt, cycles, ping);",
            "    (void)dt; (void)cycles; (void)ping; /* iOS: keep the resource HUD uncluttered. */")
    elif name == "Registrar.c":
        text = replace_function(text, "LoadColors", LOAD_COLORS)
    elif name == "Drs.c":
        text = replace_once(text, "assert(table_index <= drs.table_count);",
                            "assert(table_index >= 0 && table_index < drs.table_count); /* iOS: reject one-past-end. */")
    elif name == "Table.c":
        text = replace_once(text, "assert(file_index <= table.num_files);",
                            "assert(file_index >= 0 && file_index < table.num_files); /* iOS: reject one-past-end. */")
    elif name == "Units.c":
        text = replace_once(text, "    return ma > mb;",
                            "    return (ma > mb) - (ma < mb); /* iOS: qsort needs a three-way comparator. */")
        text = replace_once(text, "    for(int32_t i = 0; i < SIDES; i++)",
                            "    for(int32_t i = 0; i < SIDES && i < count; i++) /* iOS: inspect only valid candidates. */")
    elif name == "Blendomatic.c":
        text = replace_once(text, 'FILE* const fp = fopen(dat_path, "r");',
                            'FILE* const fp = fopen(dat_path, "rb");\n    if(!fp) Util_Bomb("Could not open %s\\n", dat_path);')
    return text.replace("<SDL2/", "<")

def prepare(source: Path, destination: Path, port: Path) -> int:
    source = source.resolve(); destination = destination.resolve(); port = port.resolve()
    if not (source / "src").is_dir():
        raise ValueError(f"Not an OpenEmpire source tree: {source}")
    if destination == source or source in destination.parents:
        raise ValueError("Destination must be outside the upstream source tree")
    # Verify everything before emitting a partial build tree.
    for name, expected in BLOBS.items():
        actual = git_blob((source / "src" / name).read_bytes())
        if actual != expected:
            raise ValueError(f"{name} is not from the verified {UPSTREAM_COMMIT} baseline: {actual}")
    destination.mkdir(parents=True, exist_ok=True)
    count = 0
    for entry in sorted((source / "src").iterdir()):
        if entry.suffix not in {".c", ".h"}:
            continue
        text = patch(entry.name, entry.read_text(encoding="utf-8"))
        (destination / entry.name).write_text(text, encoding="utf-8")
        count += 1
    shutil.copy2(port / "ios" / "Text.h", destination / "Text.h")
    shutil.copy2(source / "LICENSE", destination / "UPSTREAM-LICENSE")
    (destination / "UPSTREAM-COMMIT").write_text(UPSTREAM_COMMIT + "\n", encoding="ascii")
    return count

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--port", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        count = prepare(args.source, args.destination, args.port)
        print(f"Prepared {count} C source/header files from OpenEmpire {UPSTREAM_COMMIT}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Engine preparation failed: {exc}", file=sys.stderr)
        return 1
if __name__ == "__main__":
    raise SystemExit(main())
