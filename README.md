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

**On 0 A.D. artwork — this section previously claimed the app "bundles no Microsoft or 0 A.D. game files". That was wrong and is corrected here.** The app has always shipped 210 files from `ios/ZeroADArt/` (0 A.D. actor XML, meshes, and textures) into `OpenEmpire.app/ZeroADArt/`, consumed by the native SceneKit art scene in `ios/OEArtDemo.m`. It bundles no **Microsoft** files; the Trial-data path still requires a local installation the app does not supply.

This branch additionally renders the skirmish from that artwork. `scripts/bake_zeroad_art.py` renders the 0 A.D. meshes offline from the game's isometric angle into `ios/WebGame/sprites/` — 9 buildings, 4 trees, 2 characters, an animated villager, and a seamless ground texture. At runtime `index.html` draws those sprites in place of the procedural vector art, falling back to the vector art per-element whenever a sprite is missing or has not decoded yet. Append **`?art=proc`** to the URL to force the original procedural look and compare the two directly.

Villagers and soldiers are **animated**, not frozen. The bundled character meshes are rigged but ship with no clips, so 0 A.D.'s own walk and idle cycles are bundled alongside them under the same licence; `scripts/blender_bake_animation.py` applies them in Blender (which does the skinning) and exports deformed geometry per frame, which the bake then rasterises like everything else. Walking units play the walk cycle, idle ones the idle cycle. The archer has no mesh in this asset set, so it stays a static sprite.

Units render their **body mesh only**. 0 A.D. attaches a unit's helmet, shield, spear and greaves to named skeleton bones (`helmet`, `shield_arm`, `weapon_R`, `leg_R`), and those prop meshes are authored flat in the bone's local space — so merging them at identity, which is correct for buildings, drops a helmet at knee height. Attaching them properly needs the bone rest matrices; until then they are excluded, and the body mesh carries its own head.

0 A.D.'s art is **CC BY-SA 3.0** (C) Wildfire Games, not GPL. The baked sprites are modified derivatives and inherit that licence, including its share-alike term — see [the attribution](ios/WebGame/sprites/ATTRIBUTION.txt) and [dependency notes](docs/DEPENDENCIES.md). This port is not affiliated with or endorsed by Wildfire Games.

What the bake does **not** reach: farms, walls, palisades and gates keep their procedural art (this asset set has no wall-segment mesh, and its gate is a prop authored to sit inside a fortress wall rather than a standalone gateway); boar and sheep stay procedural, though 0 A.D. does have `actors/fauna/boar.xml` and a full `animal_boar_*` clip set upstream, so that is reachable by widening the art bundle; and unit props (helmet, shield, spear) are not rendered, for the bone-attachment reason above.

## Playing

The game starts Blue and Red settlements, each with a town center, starting villagers, nearby resources, and a delayed enemy attack. You control Blue initially. The goal is to gather, build defenses and production, raise an army, and destroy the red Town Center.

| Control | Result |
| --- | --- |
| Tap a friendly unit or building | Select it. |
| Double-tap a friendly unit | Select all friendly units of that type. |
| Tap a tree, berry patch, gold mine, stone mine, boar, or sheep with villagers selected | Start gathering or hunting. Resources return to the Town Center, Wood Yard, or Mining Camp. Wounded game bolts, so the villager has to chase it down and the animal drops to a carcass as it is used up. |
| Drag one finger on the map | Pan the camera. |
| Pinch | Zoom in/out. |
| Bottom-right stick | Directly move the selected units. |
| Tap an enemy or the sword button | Attack the target/nearest enemy with selected military units. |
| Tap your Town Center with villagers selected | Garrison them for protection; the Town Center fires stronger/faster arrows. |
| Select your Town Center | Use **Unload** to release garrisoned villagers. |
| Build actions | Place Houses, Barracks, Wood Yards, Mining Camps, Markets, Farms, Wood Palisades, Stone Walls, Gates, and Guard Towers. Each button shows a one-word caption as well as its icon. |
| Build a Gate | Gates sit in a wall line and are owned by whoever built them: your units walk straight through, enemy units are blocked. The portcullis lifts on its own while one of your units is in the opening. |
| Tap the Idle pill | Selects every idle villager and pans to them if they are off screen. The pill highlights while any villager is idle. |
| Select a completed Market | Trade 100 wood for 125 food, or 100 food for wood, gold, or stone. |
| Top HUD | Population is shown beside the current idle-villager count. |
| Artwork | Buildings, trees, characters and ground use sprites baked from the bundled 0 A.D. art. Add `?art=proc` to the URL to switch back to the procedural vector art and compare. |

A basic acceptance sequence is: select a villager, tap a tree, verify wood increases at a drop-off, build a Wood Yard, gather stone and build a Stone Wall, then train troops in the Barracks and use the stick to move them. This sequence still needs manual touch verification on the phone.

## What this version does and does not add

Implemented in source: a self-contained two-settlement offline skirmish; tap/double-tap selection; one-finger camera pan; pinch zoom; unit joystick movement; resource gathering and drop-offs; huntable boar and sheep that wander, flee and decay to carcasses; Wood Yards, Mining Camps, and Markets; resource trading; an idle-villager HUD counter that doubles as a jump-to-idle button; Houses, Barracks, Farms, Wood Palisades, Stone Walls, team-owned Gates that open for their owner, and Guard Towers; villager garrisoning in Town Centers; training; combat with impact shake and floating damage; a delayed enemy wave; and regression tests.

Rendering is dual-path. Buildings, trees, characters and the ground draw from 0 A.D. sprites baked offline; everything else, and anything whose sprite has not loaded, draws with the original procedural vector art. The switch is one constant in `index.html`, and `?art=proc` forces the procedural path.

The app opens straight into the skirmish. The native launcher the port used to park on ("Start sandbox") is no longer shown at boot. Note the consequence: the legacy C/SDL art scene it used to start now has no UI entry point, though its code and the launcher view are still in the tree and still compile.

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
