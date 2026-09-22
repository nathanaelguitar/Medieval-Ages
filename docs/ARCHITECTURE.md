# Architecture and implemented changes

## Execution flow

```text
main.m
  SDL_UIKitRunApp
    SDL initialization + window/Metal-backed SDL renderer
    native UIKit overlay
    SDL_iPhoneSetAnimationCallback -> return control to UIKit

UIKit Files picker
  security-scoped, coordinated folder read
  copy required files into staging
  structural preflight
  activate staged data with previous-dataset backup/rollback

Legacy native sandbox  [UNREACHABLE at runtime]
  background SDL loading thread
    Data_Load -> Map_Make -> Grid_Make -> Units_Generate
  acquire/release atomic completion publication
  main-thread fixed-step simulation and rendering

UIKit touches -> OETouch event queue -> replacement Input_Pump
  Overview_Update
  in-process Packet with only the active player's Overview populated
  Units_PacketService -> Units_Caretake
  Units_Float -> Video_Draw -> Video_Render
```

The steps from the Files picker down are the **legacy SDL path**. It still compiles, but nothing reaches it: the "Start sandbox" launcher button that used to start it is no longer shown at boot, so this flow is documented for the code that remains rather than for what runs. The playable target is the Pocket Empires web game described below.

There is no duplicate toy RTS implementation. The runtime calls the real upstream unit service, simulation, and draw functions. No network server is started. SDL2_net remains a static build dependency because the upstream compilation units and headers reference it; the mobile entry path does not connect to or listen on sockets.

## Files

| File or directory | Responsibility |
| --- | --- |
| `portable/OETouch.*` | Pure C gesture state machine, transition queue, selection cancellation, and accumulated camera deltas. |
| `portable/OEClock.*` | 15 ms simulation step, bounded catch-up, and reset after pauses. |
| `portable/OEAssets.*` | Required-file names, DRS/blend-table structural preflight, and slash-terminated engine paths. |
| `ios/OERuntime.c` | Engine integration, offline sessions, two player sides, action discovery, lifecycle, rendering. |
| `ios/OEInput.c` | Replacement for desktop input; combines hardware keys and queued touch state. |
| `ios/OEPlatform.m` | UIKit launcher, game overlay, Files importer, context/pause menus, safe-area controls. |
| `ios/OEWebGame.m` | `WKWebView` host for the bundled Pocket Empires game, and its page-load validation. |
| `ios/OEArtDemo.m` | Native SceneKit art scene over the bundled 0 A.D. meshes. Built and compiled, but **unreachable**: nothing calls `startInView:`. |
| `ios/OEText.m` | System-font rasterization and bounded SDL texture cache. |
| `ios/main.m` | SDL/UIKit entry and display callback. |
| `ios/WebGame/index.html` | The entire Pocket Empires skirmish: map generation, simulation, canvas rendering, and UI, in one self-contained file. |
| `ios/ZeroADArt/` | Selected 0 A.D. art (CC BY-SA 3.0), packaged into the bundle. |
| `scripts/bake_zeroad_art.py` | Offline rasteriser that bakes those meshes into `ios/WebGame/sprites/`. Not run by the build. |
| `scripts/prepare_engine.py` | Verified-baseline, build-only engine adaptation. |
| `CMakeLists.txt` | Pinned dependency retrieval, static linkage, resource packaging, generated Xcode scheme. |

## The Pocket Empires target

The playable target is not the SDL engine. `ios/OEWebGame.m` hosts `ios/WebGame/index.html` in a `WKWebView`; that file contains the whole game — isometric map generation, the simulation loop, and an immediate-mode canvas-2D renderer. It is loaded through `loadFileURL:allowingReadAccessToURL:`, which grants read access to the `open-empire-mobile/` directory only. That boundary is why the sprite set lives at `ios/WebGame/sprites/` rather than reusing `ios/ZeroADArt/` directly: the page cannot read outside its own directory. (`fetch` against `file://` is blocked regardless, so sprites load as `<img>` elements.)

`CMakeLists.txt` globs `ios/WebGame/*` unfiltered and recursively, so any new file under that directory is packaged automatically without a CMake edit.

## 0 A.D. artwork pipeline

0 A.D. is a 3D game and ships no sprites, so the artwork is **baked offline** rather than loaded:

```text
ios/ZeroADArt/actors/*.xml        actor graph: binds <mesh> to a baseTex that often
        |                         lives in a separate <group>, and composes buildings
        |                         from <props> actors
        v
scripts/bake_zeroad_art.py        expand props -> export each .dae via assimp (which
        |                         preserves map_Kd) -> software-rasterise from the game's
        |                         isometric angle with per-triangle UV sampling
        v
ios/WebGame/sprites/*.png         sprites + manifest.json (footprint width and centre)
        |                         + ATTRIBUTION.txt (CC BY-SA 3.0)
        v
index.html                        scales each sprite so its footprint maps onto the
                                  building's tile diamond; falls back to procedural
                                  vector art per element until an image decodes
```

Characters need a detour, because the bundled meshes are rigged and skinned — a 24-bone biped using 0 A.D.'s standard `Biped_*` bone names — but ship with **no animation clips**. The fix is to borrow 0 A.D.'s own: the clips under `ios/ZeroADArt/animations/` come from the same project and drive 102 of the 103 channel targets on these rigs exactly, so they are not retargeted so much as reapplied.

```text
ios/ZeroADArt/animations/biped/citizen/*.dae    0 A.D. walk + idle clips (CC BY-SA 3.0)
ios/ZeroADArt/meshes/skeletal/new/*.dae         rigged character
        |
        v
scripts/blender_bake_animation.py               Blender applies the clip and exports the
        |                                       DEFORMED mesh per frame as OBJ
        v
frame_000.obj ... frame_00N.obj                 linear blend skinning, done by Blender
        |
        v
bake_zeroad_art.py --with-animation             rasterises each frame with the same renderer
        |                                       as the buildings, so lighting matches
        v
ios/WebGame/sprites/unit_vill_walk_*.png        + a group record giving the playback rate
```

Splitting it this way avoids writing a second renderer: applying a skin to an animated skeleton is linear blend skinning, which Blender does well, and re-implementing glTF animation sampling in the bake tool would produce a worse version of something that already exists. Blender exports geometry; the existing rasteriser keeps units lit and projected exactly like everything else.

Three details here are load-bearing and were each found by testing rather than reading:

* **Blender 5.2 has no COLLADA importer.** The legacy importers left core, so `bpy.ops.wm.collada_import` does not exist on a stock install. Both the mesh and the clip arrive via assimp → glTF.
* **An action alone does not animate a rig in 4.4+.** Actions became slotted, and assigning `animation_data.action` without also binding `action_slot` leaves the rig static. That failure is silent: every sampled frame comes out identical and the bake produces a flawless sheet of one frozen pose. `blender_bake_animation.py` binds the slot and then measures actual vertex movement across the cycle, refusing to write frames if nothing moved.
* **The 0 A.D. materials point at an unresolvable absolute Windows path** (`C:/Users/micha/...`), so assimp drops the texture. It is re-attached from the bundled texture set.

`scripts/blender_character_setup.py` produces a plain `.blend` of the same character for hand-animating in the Blender UI, which is the route to clips that do not exist upstream.

Two details in that pipeline are load-bearing. The up-axis is decided **once per composite** from the mesh with the most vertices, because it is not consistent across this asset set (units are Z-up, the oak is Y-up, and small flat props guess wrong). And the vertical projection must subtract the model's lowest point as well as centring it horizontally, or every sprite is drawn partly below its own canvas and the front of the building is silently clipped.

## Important design choices

The animation callback returns to the UIKit run loop; there is no blocking desktop `while(true)` loop in the mobile entry point. Expensive sprite decoding runs on a worker, but UIKit operations, input dispatch, texture creation, and rendering stay on the main thread. The worker publishes the complete session with C11 acquire/release atomics.

Touch transitions are not implemented by pushing fake SDL mouse events and hoping `SDL_GetMouseState` changes. The replacement Input reads the gesture queue directly. A tap generates separate press and release transitions, including when both UIKit events arrive between simulation steps. Two-finger gestures cancel a pending selection without generating an accidental release command.

Simulation keeps the original 15 ms tick instead of coupling game speed to 60 or 120 Hz display refresh. Catch-up is bounded at eight steps; missed time beyond that is dropped to prevent a spiral of overload. This offline policy favors responsiveness over wall-clock synchronization under severe frame stalls. There is no network-lockstep claim.

The logical canvas remains 960 x 540 and is scaled with aspect-ratio preservation by SDL. UIKit coordinates are converted through `SDL_RenderWindowToLogical` so Retina scaling and letterboxing are accounted for. Controls use native safe-area layout. Actual usability and minimum display sizes still require device checks.

Only Blue, Red, and Gaia palette variants are decoded. The simulation uses two real player slots and an unused third spectator slot to satisfy upstream starting-position generation. Other palette arrays stay zero-initialized and are safe for upstream `Animation_Free`. Adding multiplayer colors requires restoring their decoding.

Native action menus reflect `Buttons_FromMotive`, not a separately maintained ruleset. Action selection drives the same Alt + action-key + left-release path used upstream. Training and construction placement rules therefore remain the engine's rules.

## Fixes applied to the build-only engine

1. `Video_Make`: high-DPI window, checked renderer/texture setup, logical size, native text, capped worker count.
2. `Video_Free`: release text textures and canvas before renderer, then window; no double SDL shutdown.
3. Replacement `Input.c`: drain initialized events and maintain explicit touch button edges.
4. `Registrar.LoadColors`: decode only the three required palettes and avoid per-color short-lived loading threads.
5. `Drs.GetTable` and `Table_GetFile`: reject negative and one-past-end indices rather than permitting `index == count`.
6. `Units.CompareByMag`: return a proper negative/zero/positive qsort comparison.
7. `Units.GetNextBestInanimateCoord`: examine only populated candidate entries.
8. `Blendomatic_Load`: open in binary mode and reject failed opens before reading.
9. Suppress debug dimension grids and the desktop performance text overlay.
10. Session shutdown releases per-unit paths before freeing the unit arrays.
11. Imported folder paths are normalized with a trailing slash because upstream joins directory and filename by direct concatenation.

The build retains assertions even in Release (`-UNDEBUG`), since upstream contains side effects in assertion expressions. This is a compatibility safeguard, not an endorsement of that upstream pattern.

## Asset validation boundaries

The preflight rejects missing/nonregular files, unreasonable sizes or table counts, invalid record spans, incompatible table positions/extensions, out-of-bounds DRS payload ranges, and truncated blend mask spans. The Files importer rejects symlinks and copies only the four expected files.

It does not deeply validate every SLP drawing command or catch every upstream allocation failure. `Data_Load` and parts of the original renderer still have fatal-error/assertion paths. A file passing preflight is not proof it is a compatible or safe Trial dataset. Malformed untrusted assets must not be supported without a separate parser-hardening effort.

## Remaining engineering work

First run the macOS compile workflow and the device acceptance checklist. Then profile memory and CPU rendering with real Trial assets before choosing broader hardware support. Persistent save state, autonomous opponents, native Metal sprite batching, and network compatibility are separate features, not silently assumed to exist in this delivery.
