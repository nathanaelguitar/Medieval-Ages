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

Start sandbox
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
| `ios/OEText.m` | System-font rasterization and bounded SDL texture cache. |
| `ios/main.m` | SDL/UIKit entry and display callback. |
| `scripts/prepare_engine.py` | Verified-baseline, build-only engine adaptation. |
| `CMakeLists.txt` | Pinned dependency retrieval, static linkage, resource packaging, generated Xcode scheme. |

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
