# Medieval Ages: pitch for Poki

**Live demo:** https://nathanaelguitar.github.io/Medieval-Ages/

## Hook

A real-time strategy game built for a thumb: grow a medieval village, raise an army under your banner and burn the enemy's Town Center, in a browser tab or on a phone.

## Pitch

Medieval Ages is a compact, classic-style RTS that runs in one HTML5 canvas page. You start with a Town Center and three villagers. You gather wood, food, gold and stone, put up houses, farms, a mill and a barracks, and wall in your village with drawn wall lines, gates and garrisoned towers. Then you march companies of men-at-arms and archers, each under its own lion standard, across the map to raze the enemy's Town Center. Ten levels raise the difficulty step by step, and a narrated tutorial teaches the controls in the first minutes. Touch was the design target: a thumb stick drives the army, a Select button turns a drag into a box selection, and building placement is one tap on a glowing button and one on the map. On desktop it switches to a full mouse-and-keyboard layout with RTS hotkeys. The art is photoreal pre-rendered 3D sprites, set to an original orchestral soundtrack.

## Features

- **Touch-first controls:** a thumb stick to steer selected troops or pan the camera, a Select button for box selection, double-tap to select a whole army, and one-tap build buttons with a gold glow on the armed choice.
- **Keyboard and mouse on desktop:** a fine pointer switches to a desktop layout. Left-click selects, drag boxes, right-click gives orders, and the camera scrolls with WASD, the arrow keys, the screen edge or the wheel. AoE-style hotkeys cover every building and unit, Ctrl+1-9 sets control groups, and Shift queues several buildings at once. A key card explains it all on the first desktop game.
- **10 levels on a rising difficulty curve,** from *The Quiet Border* to *No Mercy*. Each level tunes the enemy's attack timing, wave size, archer share, economy and army cap.
- **A guided tutorial with a narrator:** coach marks over the live game and a spoken line for each step. It can be replayed from the menu.
- **Defences:** garrison villagers in the Town Center or archers in guard towers (each garrisoned archer adds arrows to the volley), drag out stone walls and wooden palisades, and set gates into them.
- **Economy:** wood, food, gold and stone, plus farms, a turning post mill, a wood yard, a mining camp and a market for trading resources.
- **Hunting and herding:** villagers hunt boar that fight back, and you can lead a flock of sheep home and butcher it for food.
- **Original soundtrack:** title, village and battle themes, with music that shifts when fighting starts.
- **Photoreal art:** pre-rendered 3D units in eight facings, with heraldic banners, a blood-and-dust combat finish and an intro film.

## Tech facts

- Pure HTML5 canvas 2D in one `index.html` (about 245 KB of code). No framework, no build step, no WebGL requirement.
- About 140 MB of assets (6,000 files): 84 MB of sprites, 29 MB of audio and a 21 MB intro film. Sprites are lazy-loaded per animation, so the first match starts before most of the art has loaded.
- Works offline. The game makes no network calls of any kind (no fetch, XHR or WebSocket, and no external URLs). The iOS build runs the same page from local files with no connection.
- No external networking, accounts or backend. Progress (unlocked levels, settings) is saved in `localStorage`.
- Runs in mobile Safari and Chrome (landscape and portrait, with safe-area insets handled) and in desktop browsers.
- The same build ships as a native iOS app (WKWebView wrapper).

## Genre and tags

- **Genre:** strategy, real-time strategy (RTS)
- **Tags:** strategy, RTS, medieval, base building, army, war, kingdom, castle, knights, archers, simulation, mobile, touch

## Media in this kit

All gameplay is captured from the real game (the committed web build). Nothing is AI-generated film.

- **Trailer:** 86.6 s, 1920x1080, 30 fps, H.264 + AAC, -14 LUFS. Master: `art/out/pitch/medieval_ages_trailer.mp4` (148 MB). Upload copy: `art/out/pitch/upload/medieval_ages_trailer.mp4` (48 MB).
- **30-second cut:** master `art/out/pitch/medieval_ages_30s.mp4`, upload copy `art/out/pitch/upload/medieval_ages_30s.mp4` (19 MB).
- **Six screenshots** (village, battle, mill and farms, army with banners, UI with a building being placed, title screen) at 1920x1080 and 1280x720, as PNG and JPEG: `art/out/pitch/screenshots/`.
- **Icons** at 512 and 256 px: `art/source/pitch/icons/`.
- **Portal thumbnail** (1280x720, key art and title): `art/source/pitch/thumbnail_1280x720.jpg`.

## Questions for Poki

1. **Promotion:** if the game is accepted, what promotion do you commit to, such as homepage or category placement, featured slots, and how long they last? Is any of it guaranteed in the contract?
2. **Exclusivity term:** is the 5-year web exclusivity negotiable? Is a shorter term possible, or one that is reviewed after a first period?
3. **Exit if performance is low:** what are the termination terms if the game underperforms? Do the rights revert to me, and after how long?
4. **Self-hosting under exclusivity:** may I keep a playable demo on my own site, or a link from my site to the Poki page? What about a trailer or devlog video that shows gameplay?
5. **Online multiplayer:** the game is single-player today, but I'd like to add online multiplayer later. Given your external-networking restrictions, what's your position on that? Would it have to run on Poki infrastructure, and could it be added during the exclusivity term?
6. **SDK timing:** can the Poki SDK integration come after acceptance, or must it be in the build you review?
7. **Native apps:** the iOS app (and any later native release) sits outside web exclusivity, correct?

## Next steps if accepted

- [ ] Add a Poki SDK adapter: one small module that wraps the SDK and no-ops when it is absent, so the iOS build and local testing keep working.
- [ ] Call `gameplayStart()` on Begin and on resume, and `gameplayStop()` on pause, on the Victory or Defeat screen and when the tab is hidden.
- [ ] Show commercial breaks only between levels (on Next Level or Play Again), never mid-match. Mute music and SFX while an ad plays.
- [ ] Do a loading-time pass: pack the per-frame sprite PNGs into atlases, defer the intro film and narration until they are needed, and set a first-play download budget.
- [ ] Take down the GitHub Pages build (the `gh-pages` branch, published by `web/deploy_pages.sh`) if the deal is exclusive.
