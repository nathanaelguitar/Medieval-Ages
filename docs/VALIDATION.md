# Validation report

Prepared September 21, 2026. This report distinguishes executed checks from manual acceptance work still outstanding.

## Executed in the authoring environment

Environment: macOS with Xcode 26.5, iOS SDK, CMake, Node, and a connected iPhone named Nathanael.

| Check | Result |
| --- | --- |
| Pocket Empires JavaScript syntax | Passed with `node --check`. |
| CMake/CTest portable project checks | 2 of 2 registered suites passed. |
| iOS device build | Passed: `xcodebuild` produced the arm64 Debug app. |
| Code signing | Passed: `codesign --verify --deep --strict`. |
| Install | Passed: `devicectl` installed `com.nathanaelguitar.openempire`. |
| Native launch and web-game load | Passed on the preceding signed build: device console reported `Pocket Empires`, canvas present, 1704×786. The final one-line movement-resume tweak launched the app process successfully; its console attachment did not repeat that page-loaded line. |
| Source/bundle HTML identity | Passed: SHA-256 `fd39a49581d0bc4c3c385afe2a398ffea7617743ea62006843ccfa577510a6e3` matched. |
| Impeccable detector | Ran in degraded regex mode because optional HTML parser modules were unavailable; it reported no regex findings. |

The device launch proves that the signed app installs and the native wrapper can load the bundled game. It does **not** prove every touch path or gameplay sequence.

## Not executed

- Manual touch acceptance for joystick movement, one-finger panning, pinch zoom, gathering, drop-offs, building, walls, training, and combat.
- Long-session balance, memory, thermal, and frame-rate measurements on the iPhone.
- App Store archive validation, privacy audit, or distribution approval.

## Mac / device acceptance checklist

1. Start a match and tap a Blue villager.
2. Tap a tree and verify the villager gathers and the wood counter increases at a valid drop-off.
3. Build a Wood Yard, then send a villager to a tree; confirm the Wood Yard accepts the delivery.
4. Tap a gold or stone node, build a Mining Camp, and confirm the matching resource is delivered there.
5. Use the villager build actions to place a Market, House, Barracks, Wood Palisade, Stone Wall, and Guard Tower. Confirm the Market panel exposes resource exchanges and disables trades you cannot afford.
6. Watch the top HUD while villagers work, then interrupt one with a move command; confirm the idle count changes beside population.
7. Select villagers and tap the Town Center. Confirm they disappear into the building, are no longer targetable, and the Town Center shows a garrison count.
8. Send enemy units into Town Center range and confirm garrisoning increases defensive arrow fire. Select the Town Center and use **Unload** to release the villagers.
9. Train swordsmen/archers, select them, and drag the bottom-right stick. Confirm only selected units move; drag elsewhere on the map to pan.
10. Pinch to zoom in and out; tap and double-tap units/buildings; tap an enemy or the sword button to attack.
11. Verify the first enemy march does not occur before the delayed opening window and that later combat is winnable with normal gathering.
12. Test both landscape orientations and safe areas, then background/foreground the app and check that the match resumes without a catch-up burst.
13. Before distributing any binary, review licensing, the privacy manifest, linked dependencies, and device performance evidence.

## Reproduce local tests

```sh
./scripts/test.sh
clang -std=c11 -Wall -Wextra -Wpedantic -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer -g \
  -Iportable portable/OETouch.c portable/OEClock.c portable/OEAssets.c \
  tests/test_portable.c -lm -o /tmp/oe-tests
/tmp/oe-tests
```
