# Pocket Empires for iOS

An unofficial iPhone/iPad build that bundles the self-contained **Pocket Empires** canvas game inside the existing OpenEmpire iOS workspace. The current target loads `ios/WebGame/index.html` in a native `WKWebView`; it does not require Trial data or a network connection at runtime. The original OpenEmpire C/SDL port remains in the workspace, but this target's playable experience is the bundled web game.

**Status:** the updated source was syntax-checked, the portable project tests passed, and a signed Debug build was installed and launched on the connected iPhone on September 21, 2026. Device interaction/performance testing still needs to be done manually. See [the validation report](docs/VALIDATION.md).

## Build and run

You need a Mac with full Xcode and its iOS SDK. The deployment target is iOS/iPadOS 15 or newer.

Extract this folder and run in Terminal:

```sh
cd /path/to/OpenEmpire-iOS
chmod +x open-xcode.command
./open-xcode.command
```

The script can download immutable snapshots of OpenEmpire, SDL2, and SDL2_net and generate/open the Xcode project. The working generated project is under `build-ios-clean/` in this checkout.

In Xcode, choose the **OpenEmpire** scheme and app target, select your signing **Team** under **Signing & Capabilities**, choose a connected iPhone or iPad, and press **Run**. Use a unique bundle identifier for your own signing account. Enable Developer Mode on the device when Xcode requests it.

If CMake is missing, install it first, for example with `brew install cmake`. If Xcode is not selected, open Xcode, finish its first-run installation, and use `sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer` when that is your Xcode installation path.

For the Simulator:

```sh
./open-xcode.command --simulator
```

Use **Order** and **Pan** for interactions that are awkward with a Simulator mouse. A physical device is still required to verify multitouch, safe areas, performance, and background behavior.

For repeatable command-line configuration with signing settings:

```sh
cmake -S . -B build-ios -G Xcode \
  -DCMAKE_SYSTEM_NAME=iOS \
  -DCMAKE_OSX_SYSROOT=iphoneos \
  -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=15.0 \
  -DOE_BUNDLE_ID=com.yourname.openempire \
  -DOE_DEVELOPMENT_TEAM=YOUR_TEAM_ID
```

The engine copy is under `build-ios/engine`; edit port code or `scripts/prepare_engine.py`, not that generated copy. Upstream checkouts in `_deps` are never edited by the patcher.

## Assets and offline play

The current Pocket Empires target uses procedural canvas artwork and its own icons. It bundles no Microsoft or 0 A.D. game files, needs no asset importer, and can run offline after installation. The original Trial-data importer remains in the older native-port code path but is not needed by this target.

## Playing

The game starts Blue and Red settlements, each with a town center, starting villagers, nearby resources, and a delayed enemy attack. You control Blue initially. The goal is to gather, build defenses and production, raise an army, and destroy the red Town Center.

| Control | Result |
| --- | --- |
| Tap a friendly unit or building | Select it. |
| Double-tap a friendly unit | Select all friendly units of that type. |
| Tap a tree, berry patch, gold mine, or stone mine with villagers selected | Start gathering. Resources return to the Town Center, Wood Yard, or Mining Camp. |
| Drag one finger on the map | Pan the camera. |
| Pinch | Zoom in/out. |
| Bottom-right stick | Directly move the selected units. |
| Tap an enemy or the sword button | Attack the target/nearest enemy with selected military units. |
| Tap your Town Center with villagers selected | Garrison them for protection; the Town Center fires stronger/faster arrows. |
| Select your Town Center | Use **Unload** to release garrisoned villagers. |
| Build actions | Place Houses, Barracks, Wood Yards, Mining Camps, Markets, Farms, Wood Palisades, Stone Walls, and Guard Towers. |
| Select a completed Market | Trade 100 wood for 125 food, or 100 food for wood, gold, or stone. |
| Top HUD | Population is shown beside the current idle-villager count. |

A basic acceptance sequence is: select a villager, tap a tree, verify wood increases at a drop-off, build a Wood Yard, gather stone and build a Stone Wall, then train troops in the Barracks and use the stick to move them. This sequence still needs manual touch verification on the phone.

## What this version does and does not add

Implemented in source: native `WKWebView` launcher; a self-contained two-settlement offline skirmish; tap/double-tap selection; one-finger camera pan; pinch zoom; unit joystick movement; resource gathering and drop-offs; Wood Yards, Mining Camps, and Markets; resource trading; an idle-villager HUD counter; Houses, Barracks, Farms, Wood Palisades, Stone Walls, and Guard Towers; villager garrisoning in Town Centers; training; combat; a delayed enemy wave; and regression tests.

Not added: campaigns, matchmaking/network multiplayer, persistent saves, cloud sync, or App Store distribution. The match remains in memory only; force-quitting or the OS terminating the process loses it.

The legacy C/SDL CPU sprite renderer is preserved in the workspace, but the current Pocket Empires screen is drawn by the bundled HTML canvas. Actual frame rate and memory use still need profiling on your device.

## Tests

No downloads or Apple SDK are needed for the portable tests on macOS/Linux:

```sh
./scripts/test.sh
```

The current CMake test run contains two portable project suites; both passed. JavaScript syntax was checked with Node, and the built app's bundled HTML hash matched the source HTML hash.

A GitHub Actions workflow is included for Linux portable checks and an unsigned Simulator compile on a macOS runner. It has **not** been run for this delivery. It is intended to reveal Apple-build errors before signing, not to certify gameplay.

## Source and licensing

OpenEmpire: https://github.com/glouw/openempire

The new port files use `GPL-3.0-or-later`; see `COPYING`. The prepared upstream engine retains its full original `UPSTREAM-LICENSE`, including its game-content and Trial-use notices. The upstream license describes the project as educational/noncommercial and requires a valid Trial installation. This port does not grant rights to Microsoft artwork or waive those restrictions. It is not affiliated with or endorsed by Microsoft or the original game studios. Do not assume importing assets into an app grants permission to redistribute or sell them.

Before distributing a build, review the upstream notices, source-distribution obligations, asset permissions, dependency licenses, and Apple's current requirements. The supplied privacy manifest is a starting declaration for this implementation, not an App Store compliance certification.

See [architecture and changes](docs/ARCHITECTURE.md), [validation and remaining checks](docs/VALIDATION.md), and [pinned dependencies](docs/DEPENDENCIES.md).
