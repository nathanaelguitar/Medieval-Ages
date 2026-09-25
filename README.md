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

The Pocket Empires target needs no asset importer and runs offline after installation. The original Trial-data importer remains in the older native-port code path but is not needed by this target.

**On 0 A.D. artwork — this section previously claimed the app "bundles no Microsoft or 0 A.D. game files". That was wrong and is corrected here.** The app ships 213 distributable actor/texture files from `ios/ZeroADArt/` into `OpenEmpire.app/ZeroADArt/`, consumed by the native SceneKit art scene in `ios/OEArtDemo.m`. It bundles no **Microsoft** files; the Trial-data path still requires a local installation the app does not supply.

This branch additionally renders the skirmish from that artwork. `scripts/bake_zeroad_art.py` renders the 0 A.D. meshes offline from the game's isometric angle into `ios/WebGame/sprites/` — 9 buildings, 4 trees, villagers, spearmen, animated boars and sheep, and a seamless ground texture. At runtime `index.html` draws these sprites in place of the procedural vector art, falling back per element if a sprite is missing. Its generated `manifest.js` feeds sprite and animation data to the game without fetching JSON from the local `file://` origin. Append **`?art=proc`** to the URL to force the original procedural look and compare the two directly.

Villagers, soldiers, boars, and sheep are **animated**, not frozen. `scripts/blender_bake_animation.py` applies 0 A.D.'s walk and idle cycles in Blender (which does the skinning), exports deformed geometry per frame, and the bake rasterises those frames. Unit props such as the spearman's helmet, spear, sheath, and greaves follow their skeleton bones in both the static and animated bakes. The archer has no mesh in this asset set, so it stays a static sprite.

0 A.D.'s art is **CC BY-SA 3.0** (C) Wildfire Games, not GPL. The baked sprites are modified derivatives and inherit that licence, including its share-alike term — see [the attribution](ios/WebGame/sprites/ATTRIBUTION.txt) and [dependency notes](docs/DEPENDENCIES.md). This port is not affiliated with or endorsed by Wildfire Games.

Farms, walls, palisades, and gates still use procedural art; the selected asset set has no standalone wall-segment mesh or gateway.

## Playing

The game starts Blue and Red settlements, each with a town center, starting villagers, nearby resources, and a delayed enemy attack. You control Blue initially. The goal is to gather, build defenses and production, raise an army, and destroy the red Town Center.

| Control | Result |
| --- | --- |
| Tap a friendly unit or building | Select it. |
| Double-tap a friendly unit | Select all friendly units of that type. |
| Tap a tree, berry patch, gold mine, stone mine, boar, or sheep with villagers selected | Start gathering or hunting. Resources return to the Town Center, Wood Yard, or Mining Camp. Wounded game bolts, so the villager has to chase it down and the animal drops to a carcass as it is used up. |
| Drag one finger on the map | Rubber-band select: every unit you control inside the box is selected. Dragging over empty ground clears the selection. |
| Drag two fingers on the map | Pan the camera. |
| Pinch | Zoom in/out. |
| Drag on the minimap | Pan the camera. |
| Bottom-right stick | Directly move the selected units; with nothing selected it pans the camera instead. |
| Camera follow | The view glides to keep the units you have selected in sight once they would leave the comfort margin. Panning by hand suspends the follow for a couple of seconds so it never fights you. |
| Mouse wheel | Zoom in and out, anchored on the cursor. Web build only. |
| Space | Pause and resume. The pause pill in the status strip and a tap on the dimmed map do the same. |
| Tap an enemy or the sword button | Attack the target/nearest enemy with selected military units. |
| Tap your Town Center with villagers selected | Garrison them for protection; the Town Center fires stronger/faster arrows. |
| Select your Town Center | Use **Unload** to release garrisoned villagers. |
| Build actions | Place Houses, Barracks, Wood Yards, Mills, Mining Camps, Markets, Farms, Wood Palisades, Stone Walls, Gates, and Guard Towers. Each button shows a one-word caption as well as its icon. |
| Drop-offs | Wood Yards take wood, Mills take food from berries, farms and hunted game, Mining Camps take gold and stone. The Town Center accepts all four, so the camps exist to shorten the walk when a resource is far from home. |
| Build a Gate | Gates sit in a wall line and are owned by whoever built them: your units walk straight through, enemy units are blocked. The portcullis lifts on its own while one of your units is in the opening. |
| Tap the Idle pill | Selects every idle villager and pans to them if they are off screen. The pill highlights while any villager is idle. |
| Select a completed Market | Trade 100 wood for 125 food, or 100 food for wood, gold, or stone. |
| Top HUD | Population is shown beside the current idle-villager count. |
| Artwork | Buildings, trees, characters and ground use sprites baked from the bundled 0 A.D. art. Add `?art=proc` to the URL to switch back to the procedural vector art and compare. |

A basic acceptance sequence is: select a villager, tap a tree, verify wood increases at a drop-off, build a Wood Yard, send a villager to berries and build a Mill, gather stone and build a Stone Wall, then train troops in the Barracks and use the stick to move them. This sequence still needs manual touch verification on the phone.

## What this version does and does not add

Implemented in source: a self-contained two-settlement offline skirmish; tap/double-tap selection; one-finger camera pan; pinch and wheel zoom; unit joystick movement, or camera panning from the same stick with an empty selection; a follow camera that keeps your selected units in view; resource gathering and drop-offs; huntable boar and sheep that wander, flee and decay to carcasses; Wood Yards, Mills, Mining Camps, and Markets; resource trading; an idle-villager HUD counter that doubles as a jump-to-idle button; Houses, Barracks, Farms, Wood Palisades, Stone Walls, team-owned Gates that open for their owner, and Guard Towers; villager garrisoning in Town Centers; training; pause; combat with ready stances, firing recoil, arrow trails, impact sparks and floating damage; ambient life, beach foam and a sun grade; a delayed enemy wave; and regression tests.

Rendering is dual-path. Buildings, trees, characters and the ground draw from 0 A.D. sprites baked offline; everything else, and anything whose sprite has not loaded, draws with the original procedural vector art. The switch is one constant in `index.html`, and `?art=proc` forces the procedural path.

The app opens straight into the skirmish. The native launcher the port used to park on ("Start sandbox") is no longer shown at boot. Note the consequence: the legacy C/SDL art scene it used to start now has no UI entry point, though its code and the launcher view are still in the tree and still compile.

Not added: repairing damaged buildings, campaigns, matchmaking/network multiplayer, persistent saves, cloud sync, or App Store distribution. The match remains in memory only; force-quitting or the OS terminating the process loses it.

On repair specifically, since it is the next thing anyone reaches for: a damaged Town Center cannot currently be repaired. Tapping your own Town Center with villagers selected garrisons them instead, which is the wanted behaviour, and there is no path that restores hit points to a finished building at all -- the build action only advances construction on an unfinished one, so `buildStep` has nothing to do once `b.done` is set. A repair order would want to be routed from the hammer, not from the plain tap: the tap already means "garrison", and overloading it would make a full Town Center the only one you could repair. The work is a repair order alongside build that walks villagers to the building and trades resources for hit points at a rate scaled by how many villagers are on it.

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
