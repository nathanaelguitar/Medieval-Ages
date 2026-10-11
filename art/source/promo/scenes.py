"""Gameplay scenes for capture.py. JS runs inside the game page (globals: units, buildings, mkUnit,
mkBuilding, setGather, setPath, orderMove, camX, camY, zoom, w2s, ...). Tile coords: the player's
Town Center is at (9,41), the enemy's at (44,12); the map is 56x56.
cam: JS run every frame with f = seconds since recording started."""

COMMON_JS = r"""
window.__preloadAll = () => { for (const k in ANIM) if (ANIM[k].frames === null) clipFrame(k, 0); };
window.__pending = () => { let n = 0; for (const k in SPR) { const i = SPR[k]; if (i && !(i.complete)) n++; } return n; };
window.__look = (tx, ty, z) => { const c = w2s(tx, ty); camX = c[0]; camY = c[1]; if (z) zoom = z; };
window.__lerp = (a, b, t) => a + (b - a) * Math.max(0, Math.min(1, t));
window.__ease = t => { t = Math.max(0, Math.min(1, t)); return t * t * (3 - 2 * t); };
window.__pan = (f, dur, a, b) => { const t = __ease(f / dur); __look(__lerp(a[0], b[0], t), __lerp(a[1], b[1], t), __lerp(a[2], b[2], t)); };
window.__place = (team, type, tx, ty, done) => { const s = DEFS[type].size;
  for (let r = 0; r < 8; r++) for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) {
    if (Math.max(Math.abs(dx), Math.abs(dy)) !== r) continue;
    if (canPlace(tx + dx, ty + dy, s)) { const b = mkBuilding(team, type, tx + dx, ty + dy, done); if (done) completeB(b); return b; } }
  return null; };
window.__gatherers = (n, kind, x, y, team = 0) => { const out = [];
  for (let i = 0; i < n; i++) { const r = findResByKind(kind, x, y, 14); if (!r) break;
    const u = mkUnit(team, 'vill', r.gx + Math.random() - 0.5, r.gy + 1 + Math.random()); setGather(u, r); out.push(u); } return out; };
window.__farmers = (farms) => farms.forEach(f => { if (!f) return; const u = mkUnit(0, 'vill', f.gx + 0.3, f.gy + 0.3); setGather(u, f); });
window.__army = (team, type, n, x, y, cols = 5, sp = 0.9) => { const out = [];
  for (let i = 0; i < n; i++) { const c = i % cols, r = Math.floor(i / cols);
    out.push(mkUnit(team, type, x + (c - (cols - 1) / 2) * sp + (Math.random() - .5) * .2, y + r * sp + (Math.random() - .5) * .2)); } return out; };
window.__amove = (list, x, y) => list.forEach((u, i) => { const o = FORM[i % FORM.length];
  u.order = { type: 'amove', x: x + o[0], y: y + o[1], tgt: null }; u.path = null; u.nT = 0; setPath(u, u.order.x, u.order.y); });
window.__track = (f, list, z, ox = 0, oy = 0, k = 0.08) => { const a = list.filter(u => !u.dead); if (!a.length) return;
  let x = 0, y = 0; a.forEach(u => { x += u.x; y += u.y }); x /= a.length; y /= a.length;
  if (f === 0 || window.__cx === undefined) { window.__cx = x; window.__cy = y; }
  __cx += (x - __cx) * k; __cy += (y - __cy) * k; __look(__cx + ox, __cy + oy, z); };
aiThink = () => {}; ai.next = 1e9; followMute = 1e9; selection = [];
res[0] = { w: 2000, f: 2000, g: 1500, s: 1000 };
"""

# Everything is staged in the middle of the map (x+y around 55) so a tall 9:16 frame never shows
# the map's edge. CLEAR fells the central wood (keeping a treeline to the north for the woodcutters).
CLEAR = r"""
for (const r of resources) if (r.kind === 'tree' && r.tx >= 12 && r.tx <= 40 && r.ty >= 21 && r.ty <= 46 && !(r.tx > 31 && r.ty < 26)) deplete(r);
resources = resources.filter(r => !r.dead);
"""

# A lived-in village: Town Center, houses, farms round the post mill, a wood yard against the
# treeline, a mining camp on the gold, barracks, market, a tower, and a house going up.
VILLAGE = CLEAR + r"""
window.__tc = __place(0,'tc',24,25,true);
[[20,22],[28,22],[20,28],[29,28],[17,25]].map(p => __place(0,'house',p[0],p[1],true));
const farms = [[19,32],[22,32],[25,33],[19,35]].map(p => __place(0,'farm',p[0],p[1],true));
window.__mill = __place(0,'mill',22,35,true);
__place(0,'woodyard',25,21,true); __place(0,'mine',29,25,true);
__place(0,'barracks',15,29,true); __place(0,'market',27,30,true); window.__tower = __place(0,'tower',31,33,true);
window.__site = __place(0,'house',24,29,false);
__farmers(farms);
window.__W = __gatherers(5,'tree',25,19); window.__G = __gatherers(3,'gold',31,24); __gatherers(2,'gold',27,31);
for (let i = 0; i < 3; i++) { const u = mkUnit(0,'vill',__site.cx + 1.5 + i*0.4, __site.cy + 1.5); assignBuild(u, __site); }
__army(0,'swords',6,17,22,3); __army(0,'archer',3,15,23,3);
"""

SCENES = {
    "smoke": dict(dur=2, warm=1, setup="__look(10,41,1.2)"),
    # wide establishing push-in over the whole village
    "village": dict(dur=7, warm=4, setup=VILLAGE,
        cam="__pan(f, 7, [23.2,26.6,1.5], [23.6,26.9,1.85])"),
    # close on the house going up, villagers hammering
    "build": dict(dur=5, warm=3, setup=VILLAGE,
        after_warm="__site.progress = 0.45;",
        cam="__pan(f, 5, [__site.cx-0.4, __site.cy-0.4, 2.1], [__site.cx-0.2, __site.cy-0.2, 2.3])"),
    # the post mill turning over the farms
    "mill": dict(dur=5, warm=3, setup=VILLAGE,
        cam="__pan(f, 5, [__mill.cx-0.9, __mill.cy-1.3, 2.9], [__mill.cx-1.0, __mill.cy-1.4, 3.1])"),
    # woodcutters at the treeline and the mining camp
    "gather": dict(dur=5, warm=6, setup=VILLAGE,
        after_warm="window.__G2 = __gatherers(3,'gold',31,24); __step(40, 33.3);",
        cam="__pan(f, 5, [31.4,24.6,3.0], [31.5,24.6,3.3])"),
    # an army with banners marching across open ground; the camera tracks its centre
    "march": dict(dur=7, warm=0.5, setup=CLEAR + r"""
        window.__A = __army(0,'swords',15,15,40,5,0.7).concat(__army(0,'archer',10,15,42.2,5,0.7));
        orderMove(__A, 31, 36);
        """,
        cam="__track(f, __A, 3.0, -0.3, -0.3)"),
    # pitched battle on the cleared ground: blue from the west, red from the east, the lake behind
    "battle": dict(dur=9, warm=2.2, setup=CLEAR + r"""
        window.__B = __army(0,'swords',20,20,36,5,0.8); window.__BA = __army(0,'archer',12,17,36,4,0.8);
        window.__R = __army(1,'swords',20,28,34,5,0.8); window.__RA = __army(1,'archer',12,31,34,4,0.8);
        __amove(__B, 27, 35); __amove(__R, 21, 36); __amove(__BA, 22, 36); __amove(__RA, 26, 35);
        """,
        cam="__track(f, __B.concat(__R), __lerp(2.8, 3.2, f/9), -0.2, -0.4, 0.05)"),
    # a guard tower with five archers inside loosing volleys at a red column marching into range
    # (no red archers, so the tower is not struck and does not flash before the column arrives)
    "tower": dict(dur=7, warm=0.3, setup=VILLAGE + r"""
        const tw = __tower; for (let i = 0; i < 5; i++) { const u = mkUnit(0,'archer',tw.cx,tw.cy); u.garrisoned = tw; u.order = {type:'garrison',building:tw}; tw.garrison.push(u); }
        window.__R = __army(1,'swords',12,tw.cx+8.5,tw.cy-1.5,4,0.75);
        __amove(__R, tw.cx+0.5, tw.cy+0.5);
        """,
        cam="__pan(f, 7, [__tower.cx+1.4, __tower.cy-0.4, 2.35], [__tower.cx+1.2, __tower.cy-0.3, 2.55])"),
    # HUD visible: a selected army driven with the thumb stick (for the how-it-plays cut). The stick
    # is lifted by runtime CSS from the bottom-right corner (under TikTok's buttons) into the safe zone.
    "command": dict(dur=7, warm=1, hud=True,
        css="#joyZone{right:95px!important;bottom:235px!important} #sword{bottom:235px!important}",
        setup=VILLAGE + r"""
        window.__A = __army(0,'swords',10,17,40,5,0.85).concat(__army(0,'archer',6,17,42,3,0.85));
        selection = __A.slice(); refreshPanel(true); followMute = 0;
        __look(18.5,40.5,2.4);
        joy.id = 1; joy.mode = 'units';
        window.__thumb = (vx, vy) => { const r = joyBase.getBoundingClientRect();
          joyUpdate({clientX: r.left + r.width/2 + vx * r.width * 0.42, clientY: r.top + r.height/2 + vy * r.width * 0.42}); };
        """,
        cam="const m = __ease(f/0.5) * 0.95, ang = -0.35 + 0.55*Math.sin(f*0.7); __thumb(Math.cos(ang)*m, Math.sin(ang)*m*0.8);"
            "zoom = __lerp(2.4, 2.6, f/7);"),
}
