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

# ---------------------------------------------------------------------------------------------
# Batch 2 (ten daily promos). Helpers: on-screen position of a tile, a fake fingertip for the HUD
# scenes, game-clock toasts (the game's own expire on real-time setTimeout, i.e. after a handful of
# slow capture frames), and wild animals placed where a scene needs them.
COMMON_JS += r"""
window.__scr = (wx, wy) => { const s = w2s(wx, wy); return [(s[0] - camX) * zoom + cw / 2, (s[1] - camY) * zoom + ch / 2]; };
window.__finger = (px, py, down) => { let d = document.getElementById('__fing');
  if (!d) { d = document.createElement('div'); d.id = '__fing';
    d.style.cssText = 'position:fixed;z-index:99999;width:38px;height:38px;margin:-19px 0 0 -19px;border-radius:50%;background:rgba(255,255,255,.42);border:2px solid rgba(255,255,255,.95);box-shadow:0 0 14px rgba(0,0,0,.55);pointer-events:none;transition:none';
    document.body.appendChild(d); }
  d.style.display = px === null ? 'none' : 'block'; if (px === null) return;
  d.style.left = px + 'px'; d.style.top = py + 'px'; d.style.transform = down ? 'scale(.78)' : 'scale(1)'; };
window.__toastsGT = () => { window.__TQ = [];
  toast = msg => { const box = $('toasts'); while (box.children.length > 1) box.firstChild.remove();
    const d = document.createElement('div'); d.className = 'toast in'; d.textContent = msg; box.appendChild(d); __TQ.push([d, __ts + 2600]); };
  const s0 = window.__step; window.__step = (n, dt) => { s0(n, dt); __TQ = __TQ.filter(([d, t]) => { if (__ts > t) { d.remove(); return false } return true }) }; };
window.__animal = (kind, x, y, amt, owner) => { const r = {kind, tx: Math.floor(x), ty: Math.floor(y), gx: x, gy: y, amt, amt0: amt, dead: false,
  animal: true, hx: x, hy: y, wt: 1 + Math.random() * 3, wax: 0, way: 0, face: Math.random() < .5 ? 1 : -1, flee: 0, fx: 0, fy: 0};
  if (kind === 'boar') { r.hp = r.maxhp = 60; r.bite = 0 } if (owner !== undefined) r.owner = owner; resources.push(r); return r; };
window.__clearAnimals = (x0, y0, x1, y1) => { resources = resources.filter(r => !(r.animal && r.gx >= x0 && r.gx <= x1 && r.gy >= y0 && r.gy <= y1)); };
"""
# only the toasts from the HUD, set below the two-line caption block (y 290..480 px) so the two never overlap
TOASTS_CSS = ("#hud{display:block!important} #hud>:not(#toasts){display:none!important}"
              " #toasts{display:flex!important;top:270px!important} .toast{font-size:15px!important;transition:none!important}")
# the full HUD, with the bottom-left Select button and bottom-right stick/sword lifted out of the caption zone
HUD_CSS = ("#toasts{top:270px!important} .toast{font-size:15px!important;transition:none!important}"
           " #selBtn{bottom:250px!important;left:40px!important} #joyZone{display:none!important}"
           " #sword{bottom:235px!important;right:95px!important} #mmWrap{display:none!important}")

# a small village for the HUD/wall scenes: TC, houses, a wood yard on the north treeline
HAMLET = CLEAR + r"""
window.__tc = __place(0,'tc',24,25,true);
[[20,22],[28,22],[20,28],[17,25]].map(p => __place(0,'house',p[0],p[1],true));
__place(0,'woodyard',25,21,true);
"""

SCENES.update({
    # stone wall line drawn and raised by eight villagers (time-lapse x4)
    "wall": dict(dur=8, warm=0.5, speed=4, setup=HAMLET + r"""
        window.__V = []; for (let i = 0; i < 8; i++) __V.push(mkUnit(0,'vill',20 + i*0.9, 33.2));
        selection = __V.slice(); placing = {type:'stonewall', line:[[17,32],[30,32]]}; approveWall(); selection = [];
        """,
        cam="__pan(f, 8, [19.6,29.6,2.25], [23.6,30.2,2.25])"),
    # five archers walk into the guard tower; the next red column eats a six-arrow volley
    "garrison": dict(dur=10, warm=0.3, css=TOASTS_CSS, setup=VILLAGE + r"""
        __toastsGT(); const tw = __tower;
        window.__GA = __army(0,'archer',5,tw.cx-3.2,tw.cy+0.6,5,0.8); orderMove(__GA, tw.cx-0.9, tw.cy+0.9);
        """,
        events=[(2.0, "garrisonVillagers(__GA, __tower); ping(__tower.cx,__tower.cy,'#7fd4ff');"),
                (2.4, "const tw = __tower; window.__R = __army(1,'swords',12,tw.cx+8.0,tw.cy-2.5,4,0.75); orderMove(__R, tw.cx+1.5, tw.cy+4.5);")],
        cam="const tw = __tower; __pan(f, 3.0, [tw.cx-1.6, tw.cy+0.4, 2.7], [tw.cx+1.4, tw.cy-0.4, 2.35]);"),
    # villagers hunt a boar at the treeline: it charges, they bring it down and butcher it
    "boar": dict(dur=9, warm=0.3, setup=CLEAR + r"""
        __clearAnimals(20, 20, 45, 40);
        // screen x follows (tx - ty): hunters on the boar's diagonal, below it, so both fit a tall frame
        window.__boar = __animal('boar', 31.0, 27.4, 300);
        window.__H = []; for (let i = 0; i < 2; i++) { const u = mkUnit(0,'vill', 33.6 + i*0.7, 30.6 + i*0.2); __H.push(u); }   // two hunters: a fight you can see
        """,
        events=[(0.6, "__H.forEach(u => setGather(u, __boar));")],
        cam="__pan(f, 9, [32.2,28.9,3.2], [32.0,28.7,3.5])"),
    # a flock of nine sheep led home through the village
    "sheep": dict(dur=8, warm=0.3, setup=HAMLET + r"""
        __clearAnimals(5, 15, 45, 45);
        window.__S = []; for (let i = 0; i < 9; i++) __S.push(__animal('sheep', 14.2 + (i%3)*0.7 + Math.random()*0.3, 30.4 + Math.floor(i/3)*0.7, 120, 0));
        const sh = mkUnit(0,'vill',13.6,31.2); window.__S.push(sh);
        sheepSel = __S.filter(r => r.kind === 'sheep'); leadSheep(22.2, 30.2); orderMove([sh], 21.4, 30.6); sheepSel = [];
        """,
        cam="__track(f, __S.map(o => ({x: o.gx !== undefined ? o.gx : o.x, y: o.gy !== undefined ? o.gy : o.y, dead: false})), 3.0, 0, -0.1, 0.07)"),
    # three companies, each under its lion standard, marching in column
    "banners": dict(dur=8, warm=0.6, setup=CLEAR + r"""
        const a = __army(0,'swords',12,14,30.0,4,0.7), b = __army(0,'swords',12,17.5,34.5,4,0.7), c = __army(0,'archer',10,12.5,35.5,4,0.7);
        window.__A = a.concat(b, c); orderMove(a, 27, 29.0); orderMove(b, 30.5, 33.5); orderMove(c, 25.5, 34.5);
        """,
        cam="__track(f, __A, 1.85, 0.3, 0.0, 0.06)"),
    # HUD: tap Select, drag a box round the villagers, send them to the trees
    "selbox": dict(dur=8, warm=0.5, hud=True, css=HUD_CSS, setup=HAMLET + r"""
        __toastsGT(); followMute = 1e9;
        window.__V = []; for (let i = 0; i < 6; i++) __V.push(mkUnit(0,'vill',22.4 + (i%3)*0.8, 31.0 + Math.floor(i/3)*0.8));
        __look(23.9, 30.6, 2.4);
        window.__sb = () => { const r = $('selBtn').getBoundingClientRect(); return [r.left + r.width/2, r.top + r.height/2]; };
        """,
        events=[(0.9, "$('selBtn').dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));"),
                (3.4, "box.x1 = __bx[2]; box.y1 = __bx[3]; doBox(); box = null;"),
                (4.2, "const t = findResByKind('tree', 25, 19, 10); __V.forEach(u => { const r = findResByKind('tree', 25, 19, 10); setGather(u, r); }); ping(t.gx, t.gy, '#9fe08a'); sfx('ok');")],
        cam=r"""
        if (f < 1.7 || !window.__bx) { const P = __V.map(u => __scr(u.x, u.y));    // the villagers' on-screen bounding box, padded
          window.__bx = [Math.min(...P.map(p => p[0])) - 26, Math.min(...P.map(p => p[1])) - 46, Math.max(...P.map(p => p[0])) + 26, Math.max(...P.map(p => p[1])) + 16]; }
        if (f < 0.9) { const s = __sb(); __finger(__lerp(300, s[0], __ease(f/0.8)), __lerp(560, s[1], __ease(f/0.8)), f > 0.75); }
        else if (f < 1.6) { const s = __sb(); __finger(__lerp(s[0], __bx[0], __ease((f-0.9)/0.6)), __lerp(s[1], __bx[1], __ease((f-0.9)/0.6)), false); }
        else if (f < 3.4) { const t = __ease((f-1.7)/1.6); if (f >= 1.7) { if (!box) box = {x0: __bx[0], y0: __bx[1], x1: __bx[0], y1: __bx[1], active: true};
            box.x1 = __lerp(__bx[0], __bx[2], t); box.y1 = __lerp(__bx[1], __bx[3], t); } __finger(box ? box.x1 : __bx[0], box ? box.y1 : __bx[1], f >= 1.7); }
        else if (f < 4.3) { const tr = __scr(25.5, 19.5); __finger(__lerp(__bx[2], tr[0], __ease((f-3.5)/0.6)), __lerp(__bx[3], tr[1], __ease((f-3.5)/0.6)), f > 4.1); }
        else __finger(null);
        """),
    # HUD: double-tap one soldier selects the whole army, a tap sends it off
    "dbltap": dict(dur=8, warm=0.6, hud=True, css=HUD_CSS, setup=CLEAR + r"""
        __toastsGT(); followMute = 1e9;
        window.__A = __army(0,'swords',10,20,31,5,0.8).concat(__army(0,'archer',6,24.5,33.5,3,0.8), __army(0,'swords',8,17,35,4,0.8));
        window.__U = __A[7]; __look(21.2, 32.6, 2.3);
        """,
        events=[(1.0, "{ const p = __scr(__U.x, __U.y); tap(p[0], p[1]-4); }"),
                (1.3, "{ const p = __scr(__U.x, __U.y); lastTap.t = performance.now(); tap(p[0], p[1]-4); }"),
                (3.0, "{ const p = __scr(29.5, 29.0); tap(p[0], p[1]); }")],
        cam=r"""
        const p = __scr(__U.x, __U.y - 0.1), g = __scr(29.5, 29.0);
        if (f < 1.0) __finger(__lerp(380, p[0], __ease(f/0.85)), __lerp(700, p[1], __ease(f/0.85)), f > 0.9);
        else if (f < 1.45) __finger(p[0], p[1], (f > 1.2 && f < 1.4) || f < 1.1);
        else if (f < 3.1) __finger(__lerp(p[0], g[0], __ease((f-1.8)/1.0)), __lerp(p[1], g[1], __ease((f-1.8)/1.0)), f > 2.9);
        else __finger(null);
        if (f > 3.2) __track(f, __A, __lerp(2.3, 2.2, (f-3.2)/4), 0, 0, 0.03); else window.__cx = undefined;
        """),
    # a village rises from bare ground (time-lapse x6)
    "timelapse": dict(dur=12, warm=0.2, speed=6, setup=CLEAR + r"""
        window.__tc = __place(0,'tc',24,25,true);
        window.__V = []; for (let i = 0; i < 16; i++) __V.push(mkUnit(0,'vill', 23 + (i%4)*0.8, 29 + Math.floor(i/4)*0.7));
        window.__plan = [['house',20,22],['house',28,22],['farm',19,32],['house',20,28],['farm',22,32],['woodyard',25,21],['mill',22,35],
          ['house',29,28],['farm',25,33],['barracks',15,29],['market',27,30],['house',17,25],['farm',19,35],['tower',31,33],['mine',29,25]];
        window.__build = i => { const p = __plan[i]; if (!p) return; const b = __place(0,p[0],p[1],p[2],false); if (!b) return;
          const idle = __V.filter(u => u.order.type === 'idle' || (u.order.type === 'build' && u.order.b && u.order.b.done));
          (idle.length >= 3 ? idle : __V).sort((p, q) => dist2(p.x,p.y,b.cx,b.cy) - dist2(q.x,q.y,b.cx,b.cy)).slice(0, 4).forEach(u => assignBuild(u, b)); };
        __build(0); __build(1);
        """,
        events=[(0.35 + 0.42 * i, f"__build({i + 2})") for i in range(13)],
        cam="__pan(f, 12, [23.6,27.6,1.45], [23.6,28.0,1.62])"),
    # pulling back from the turning mill over the worked fields
    "millwide": dict(dur=7, warm=3, setup=VILLAGE,
        cam="__pan(f, 7, [__mill.cx-0.6, __mill.cy-1.0, 3.2], [__mill.cx-1.2, __mill.cy-1.6, 2.0])"),
    # hold the gate: red men-at-arms hammer a gate in a stone wall; archers on the inside and a
    # garrisoned tower shoot them down
    "gate": dict(dur=9, warm=0.4, setup=CLEAR + r"""
        __clearAnimals(5, 15, 45, 45);
        for (let x = 16; x <= 32; x++) { if (x === 24) continue; const b = mkBuilding(0,'stonewall',x,30,true); completeB(b); }
        window.__gate = mkBuilding(0,'gate',24,30,true); completeB(__gate);
        window.__tw = __place(0,'tower',27,27,true); for (let i = 0; i < 5; i++) { const u = mkUnit(0,'archer',__tw.cx,__tw.cy); u.garrisoned = __tw; u.order = {type:'garrison',building:__tw}; __tw.garrison.push(u); }
        window.__BA = __army(0,'archer',8,23.2,28.2,4,0.8); window.__BS = __army(0,'swords',6,23.6,26.6,3,0.8);
        window.__R = __army(1,'swords',16,24.6,37.5,4,0.75);
        __R.forEach(u => { u.order = {type:'attack', target: __gate}; u.path = null; u.nT = 0; });
        // a gate under constant blows never stops flashing and reads as a pale ghost: keep its hit flash to a faint flicker
        const d0 = damage; damage = (t, ...a) => { const r = d0(t, ...a); if (t === __gate) t.flash = Math.min(t.flash || 0, 0.035); return r; };
        0;   // (Playwright calls a setup whose value is a function)
        """,
        cam="__pan(f, 9, [24.6,31.4,2.5], [24.6,31.0,2.75])"),
})
