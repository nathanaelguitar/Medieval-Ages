# Pinned sources and build inputs

These are compatibility pins, not claims that the selected releases are the newest.

| Component | Selected revision | Role |
| --- | --- | --- |
| glouw/openempire | `466fc251f1bcad69c917c31c94ffa4c069700cc2` | Original C engine. |
| libsdl-org/SDL | `2359383fc187386204c3bb22de89655a494cd128` (2.32.4) | iOS platform, input/event primitives, timing, threading, Metal-backed texture upload. |
| libsdl-org/SDL_net | `669e75b84632e2c6cc5c65974ec9e28052cb7a4e` (2.2.0) | Existing engine's network headers and object-file dependencies. |

Repositories:

- https://github.com/glouw/openempire
- https://github.com/libsdl-org/SDL
- https://github.com/libsdl-org/SDL_net

The CMake file uses archive URLs containing full commit IDs. The source package does not vendor these dependencies; the initial configure must be able to download them. Seven modified upstream files are additionally checked against their exact Git blob IDs before patches are applied. These checks prevent accidentally applying the known patches to a different baseline; they are not a cryptographic review of every dependency file.

SDL and SDL_net carry zlib licenses. Inspect their downloaded source licenses when redistributing a binary. OpenEmpire retains its upstream LICENSE in the prepared engine directory. SDL_ttf is not linked. Font files from the upstream archive are not copied into the prepared engine or app bundle; native UIFont provides the app's text.

## Bundled 0 A.D. artwork — CC BY-SA 3.0

Unlike the engine dependencies above, the 0 A.D. art is **not** merely a build input: it is redistributed inside the app. This carries an obligation that the table above does not cover.

| Path | What it is | Shipped in the bundle |
| --- | --- | --- |
| `ios/ZeroADArt/` | 0 A.D. actor XML, COLLADA meshes, OBJ/MTL, and PNG/DDS textures selected from the 2024 GitHub mirror | Yes — 210 files under `ZeroADArt/` (the `.dae` and `.dds` sources are not packaged) |
| `ios/WebGame/sprites/` | Isometric sprites baked from those meshes by `scripts/bake_zeroad_art.py` | Yes — under `open-empire-mobile/sprites/` |

Licence: **Creative Commons Attribution-ShareAlike 3.0** (CC BY-SA 3.0), (C) 2009 Wildfire Games. Full text and the original notices are retained at `ios/ZeroADArt/LICENSE.txt` and `ios/ZeroADArt/ATTRIBUTION.txt`; the baked sprites carry an equivalent notice at `ios/WebGame/sprites/ATTRIBUTION.txt`.

The share-alike term is the part that matters here and is easy to miss: **the baked sprites are modified (rasterised) derivatives of that artwork, so they must themselves be distributed under CC BY-SA 3.0.** They are not covered by this repository's GPL-3.0-or-later licence, and they cannot be relicensed more restrictively. Attribution must name Wildfire Games and link both the licence and https://www.wildfiregames.com/. Anything that redistributes the app — including a binary-only build — has to carry that attribution and those licence terms.

This is separate from, and in addition to, the upstream OpenEmpire Trial-data notice, which concerns Microsoft artwork. This port grants no rights to Microsoft assets in either case.

Regenerating the sprites (`python3 scripts/bake_zeroad_art.py`) requires Pillow and the `assimp` CLI, and reproduces the same licence position. The output is committed, so no build step depends on either tool.

Useful primary documentation:

- SDL iOS lifecycle and entry point: https://wiki.libsdl.org/SDL2/README-ios
- SDL logical coordinate conversion: https://wiki.libsdl.org/SDL2/SDL_RenderWindowToLogical
- Apple required-reason API documentation: https://developer.apple.com/documentation/bundleresources/describing-use-of-required-reason-api

`PrivacyInfo.xcprivacy` declares no tracking or collected-data types, app-container file metadata access, and elapsed-time measurement. The code does not upload assets or runtime telemetry. These declarations, all linked SDK uses, and distribution eligibility must still be reviewed against an actual archive and current Apple requirements before submission.
