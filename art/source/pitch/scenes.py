"""Landscape gameplay scenes for the Poki pitch kit (capture.py). Helpers and the village layouts are
carried over from art/source/promo/scenes.py; cameras are re-framed for 16:9.

JS runs inside the game page (globals: units, buildings, resources, mkUnit, mkBuilding, setGather,
setPath, orderMove, tryQueue, startPlace, tryPlace, camX, camY, zoom, w2s, ...). Tile coords: the
player's own Town Center is at (9,41), the enemy's at (44,12); the map is 56x56. The staged village
sits in the middle of the map round a second Town Center at (24,25).
cam: JS run every frame with f = seconds since recording started.
speed: game steps per recorded frame (number, or a Python callable of t for a time-lapse that
starts part-way through a shot)."""

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
window.__scr = (wx, wy) => { const s = w2s(wx, wy); return [(s[0] - camX) * zoom + cw / 2, (s[1] - camY) * zoom + ch / 2]; };
window.__finger = (px, py, down) => { let d = document.getElementById('__fing');
  if (!d) { d = document.createElement('div'); d.id = '__fing';
    d.style.cssText = 'position:fixed;z-index:99999;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;background:rgba(255,255,255,.40);border:2px solid rgba(255,255,255,.95);box-shadow:0 0 12px rgba(0,0,0,.55);pointer-events:none;transition:none';
    document.body.appendChild(d); }
  d.style.display = px === null ? 'none' : 'block'; if (px === null) return;
  d.style.left = px + 'px'; d.style.top = py + 'px'; d.style.transform = down ? 'scale(.78)' : 'scale(1)'; };
// toasts that expire on the game clock (the game's own use real-time setTimeout)
window.__toastsGT = () => { window.__TQ = [];
  toast = msg => { const box = $('toasts'); while (box.children.length > 1) box.firstChild.remove();
    const d = document.createElement('div'); d.className = 'toast in'; d.textContent = msg; box.appendChild(d); __TQ.push([d, __ts + 2600]); };
  { const seen = new Set(); notice = m => { if (seen.has(m)) return; seen.add(m); toast(m); }; }
  const s0 = window.__step; window.__step = (n, dt) => { s0(n, dt); __TQ = __TQ.filter(([d, t]) => { if (__ts > t) { d.remove(); return false } return true }) }; };
window.__animal = (kind, x, y, amt, owner) => { const r = {kind, tx: Math.floor(x), ty: Math.floor(y), gx: x, gy: y, amt, amt0: amt, dead: false,
  animal: true, hx: x, hy: y, wt: 1 + Math.random() * 3, wax: 0, way: 0, face: Math.random() < .5 ? 1 : -1, flee: 0, fx: 0, fy: 0};
  if (kind === 'boar') { r.hp = r.maxhp = 60; r.bite = 0 } if (owner !== undefined) r.owner = owner; resources.push(r); return r; };
window.__clearAnimals = (x0, y0, x1, y1) => { resources = resources.filter(r => !(r.animal && r.gx >= x0 && r.gx <= x1 && r.gy >= y0 && r.gy <= y1)); };
// a static resource tile (berry bush, stone, gold), the same shape genResources() makes
window.__put = (kind, x, y, amt) => { const k = y * MAP + x; if (resMap.has(k) || grid[k] !== 1) return null;
  const r = {kind, tx: x, ty: y, gx: x + 0.5, gy: y + 0.5, amt, dead: false}; resources.push(r); resMap.set(k, r); grid[k] = 0; return r; };
// centre of a DOM element in CSS px
window.__el = sel => { const e = typeof sel === 'string' ? document.querySelector(sel) : sel; if (!e) return null;
  const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; };
// Capture-only cosmetics. (1) No x-ray silhouettes: units behind a building or tree are drawn as
// flat team-colour ghosts, which read as blue flashes in a trailer. (2) Hit flashes kept to a faint
// flicker: a building or a melee under constant blows otherwise turns into a pale ghost. (3) No
// floating damage numbers (texts with plain:true), and pickups lose the doubled '+' the game draws
// ("++10"); both filtered right before each render so no frame shows them.
silhouette = () => {};
{ const d0 = damage; damage = (t, ...a) => { const r = d0(t, ...a);
    if (t && t.kind === 'bld') t.flash = Math.min(t.flash || 0, 0.035); else if (t && t.kind === 'unit') t.flash = Math.min(t.flash || 0, 0.05); return r; }; }
{ const r0 = render; render = () => { if (!window.__keepDmg) texts = texts.filter(t => !t.plain);
    for (const t of texts) if (t.ic && t.str[0] === '+') t.str = t.str.slice(1); r0(); }; }
aiThink = () => {}; ai.next = 1e9; followMute = 1e9; selection = []; refreshPanel(true);
res[0] = { w: 640, f: 515, g: 285, s: 420 };   // a believable mid-game stock (round thousands read as a cheat)
"""

# fell the central wood (keeping a treeline to the north for the woodcutters)
CLEAR = r"""
for (const r of resources) if (r.kind === 'tree' && r.tx >= 12 && r.tx <= 40 && r.ty >= 21 && r.ty <= 46 && !(r.tx > 31 && r.ty < 26)) deplete(r);
resources = resources.filter(r => !r.dead);
"""

# a lived-in village: Town Center, houses, farms round the post mill, a wood yard on the treeline,
# a mining camp on the gold, berry bushes, barracks, market, a tower, and a house going up
VILLAGE = CLEAR + r"""
window.__tc = __place(0,'tc',24,25,true);
[[20,22],[28,22],[20,28],[29,28],[17,25]].map(p => __place(0,'house',p[0],p[1],true));
const farms = [[19,32],[22,32],[25,33],[19,35]].map(p => __place(0,'farm',p[0],p[1],true));
window.__mill = __place(0,'mill',22,35,true);
__place(0,'woodyard',25,21,true); __place(0,'mine',29,25,true);
window.__rax = __place(0,'barracks',15,29,true); __place(0,'market',27,30,true); window.__tower = __place(0,'tower',31,33,true);
window.__site = __place(0,'house',24,29,false);
[[22,29],[23,29],[22,30]].forEach(p => __put('berry', p[0], p[1], 150));
__farmers(farms);
window.__W = __gatherers(5,'tree',25,19); window.__G = __gatherers(3,'gold',31,24); __gatherers(2,'gold',27,31);
window.__BR = __gatherers(2,'berry',22,29); window.__ST = __gatherers(2,'stone',18,26);
for (let i = 0; i < 3; i++) { const u = mkUnit(0,'vill',__site.cx + 1.5 + i*0.4, __site.cy + 1.5); assignBuild(u, __site); }
window.__ARMY = __army(0,'swords',6,15.2,34.4,3).concat(__army(0,'archer',3,13.6,34.8,3));
"""

# a small village for the HUD/wall scenes: TC, houses, a wood yard on the north treeline
HAMLET = CLEAR + r"""
window.__tc = __place(0,'tc',24,25,true);
[[20,22],[28,22],[20,28],[17,25]].map(p => __place(0,'house',p[0],p[1],true));
__place(0,'woodyard',25,21,true);
"""

# the full HUD at laptop scale; toasts on the game clock and kept short
HUD_CSS = ".toast{transition:none!important}"
# the phone: the same HUD, nothing hidden (this is what a player sees)
PHONE_CSS = ".toast{transition:none!important}"

SCENES = {
    "smoke": dict(dur=1, warm=0.5, setup="__look(10,41,1.2)"),
    # wide establishing push-in over the whole village
    "village": dict(dur=8, warm=4, setup=VILLAGE,
        cam="__pan(f, 8, [23.6,26.4,1.22], [23.6,26.8,1.45])"),
    # the economy up close: berries, stone, the house going up, the woodcutters
    "gather": dict(dur=7, warm=5, setup=VILLAGE + r"""
        [[33,27],[34,27],[33,28]].forEach(p => __put('stone', p[0], p[1], 500));
        [[31,28],[32,28],[32,29]].forEach(p => __put('berry', p[0], p[1], 150));
        __gatherers(3,'stone',33,27); __gatherers(3,'berry',31,28);
        """,
        cam="__pan(f, 7, [32.4,26.6,2.3], [32.0,26.4,2.5])"),
    # woodcutters at the treeline, the wood yard taking their loads
    "wood": dict(dur=6, warm=6, setup=VILLAGE + "__gatherers(4,'tree',23,19);",
        cam="__pan(f, 6, [23.4,19.4,2.7], [23.9,19.5,2.9])"),
    # the mining camp on the gold
    "gold": dict(dur=6, warm=6, setup=VILLAGE,
        after_warm="window.__G2 = __gatherers(3,'gold',31,24); __step(40, 33.3);",
        cam="__pan(f, 6, [30.6,25.4,2.7], [30.9,25.2,2.9])"),
    # the post mill turning over the farms
    "mill": dict(dur=7, warm=3, setup=VILLAGE,
        cam="__pan(f, 7, [__mill.cx-0.8, __mill.cy-1.4, 2.9], [__mill.cx-1.3, __mill.cy-1.8, 2.1])"),
    # a village rises from bare ground (time-lapse x6)
    "timelapse": dict(dur=11, warm=0.2, speed=6, setup=CLEAR + r"""
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
        cam="__pan(f, 11, [24.0,28.0,1.3], [24.0,28.2,1.45])"),
    # a stone wall line: drawn with a finger, confirmed with Build, then raised by eight villagers
    # (real time while drawing, time-lapse x4 once the masons start)
    "wall": dict(dur=9, warm=0.5, hud=True, css=HUD_CSS + " #mmWrap,#joyZone,#sword,#selBtn,#panel{display:none!important}",
        speed=lambda t: 1 if t < 2.6 else 4,
        setup=HAMLET + r"""
        __toastsGT();
        window.__V = []; for (let i = 0; i < 8; i++) __V.push(mkUnit(0,'vill',20 + i*0.9, 33.4));
        selection = __V.slice(); refreshPanel(true);
        placing = {type:'stonewall', ghost:[17,32], line:null, pend:false};
        __look(23.5,32.0,1.75);
        """,
        cam=r"""
        const a = __scr(17.5, 32.5), b = __scr(30.5, 32.5);
        if (f < 0.5) __finger(__lerp(a[0]-60, a[0], __ease(f/0.45)), __lerp(a[1]+60, a[1], __ease(f/0.45)), f > 0.4);
        else if (f < 1.7) { const t = __ease((f-0.5)/1.1), x = Math.round(__lerp(17, 30, t));
          placing.line = [[17,32],[x,32]]; placing.pend = false; __finger(__lerp(a[0], b[0], t), __lerp(a[1], b[1], t), true); }
        else if (f < 1.8) { placing.pend = true; __finger(b[0], b[1], false); }
        else if (f < 2.4) { const k = __el('#wallOk'); if (k) __finger(__lerp(b[0], k[0], __ease((f-1.8)/0.5)), __lerp(b[1], k[1], __ease((f-1.8)/0.5)), f > 2.25); }
        else if (f < 2.5) { if (placing) approveWall(); selection = []; refreshPanel(true); __finger(null); }
        else __finger(null);
        """),
    # train soldiers and archers at the barracks: the bottom bar, the queue bar filling, units stepping out
    "train": dict(dur=8, warm=1.5, hud=True, css=HUD_CSS, setup=VILLAGE + r"""
        __toastsGT(); DEFS.swords.t = 2.2; DEFS.archer.t = 2.2;
        notice = () => {};   // no "House complete" from the site elsewhere in the village
        __rax.rally = {x: 15.6, y: 33.4}; selection = [__rax]; refreshPanel(true);
        __look(16.4, 31.4, 2.05);
        window.__btn = n => document.querySelector('#panel .abtn[title="' + n + '"]');
        window.__press = n => { const b = __btn(n); if (b) b.click(); };
        """,
        events=[(0.8, "__press('Man-at-Arms')"), (1.4, "__press('Man-at-Arms')"), (2.0, "__press('Archer')"), (2.6, "__press('Archer')"), (3.2, "__press('Man-at-Arms')")],
        cam=r"""
        const seq = [[0.8,'Man-at-Arms'],[1.4,'Man-at-Arms'],[2.0,'Archer'],[2.6,'Archer'],[3.2,'Man-at-Arms']];
        if (f > 3.6) { __finger(null); }
        else { let prev = [700, 420], cur = null, t0 = 0, tgt = null;
          for (const [t, n] of seq) { const p = __el(__btn(n)); if (!p) continue; if (f < t) { tgt = p; t0 = t; break; } prev = p; }
          if (tgt) { const k = __ease((f - (t0 - 0.5)) / 0.4); __finger(__lerp(prev[0], tgt[0], k), __lerp(prev[1], tgt[1], k), t0 - f < 0.08); }
          else __finger(prev[0], prev[1], f < 3.28); }
        __look(16.4 - 0.3 * __ease(f/8), 31.4 + 0.5 * __ease(f/8), __lerp(2.05, 1.95, f/8));
        """),
    # villagers selected, House armed (gold glow), the ghost dragged into place, the site laid
    "place": dict(dur=8, warm=1, hud=True, css=HUD_CSS, setup=VILLAGE + r"""
        __toastsGT(); DEFS.house.t = 4; notice = () => {};
        window.__V = []; for (let i = 0; i < 4; i++) __V.push(mkUnit(0,'vill', 26.0 + (i%2)*0.7, 37.4 + Math.floor(i/2)*0.7));
        selection = __V.slice(); refreshPanel(true);
        __look(28.0, 34.4, 2.2);
        window.__hb = () => __el('#panel .abtn[title="House"]');
        window.__dst = [29.0, 34.0];
        """,
        events=[(0.9, "startPlace('house')"),
                (3.3, "tryPlace(__dst[0], __dst[1])"),
                (7.0, "__V.forEach(u => { const r = findResByKind('berry', 30, 31, 12) || findResByKind('gold', 28, 31, 12); if (r) setGather(u, r); });")],
        cam=r"""
        const hb = __hb() || [480, 500], g = __scr(__dst[0], __dst[1]);
        if (f < 0.9) __finger(__lerp(640, hb[0], __ease(f/0.75)), __lerp(380, hb[1], __ease(f/0.75)), f > 0.78);
        else if (f < 1.5) __finger(hb[0], hb[1], f < 1.0);
        else if (f < 3.3) { const t = __ease((f-1.5)/1.5), s0 = placing && placing.g0 ? placing.g0 : null;
          if (placing && !placing.g0) placing.g0 = placing.ghost.slice();
          if (placing) { const st = __scr(placing.g0[0], placing.g0[1]); const px = __lerp(st[0], g[0], t), py = __lerp(st[1], g[1], t);
            placing.ghost = scr2w(px, py); __finger(px, py, f > 1.65); } }
        else if (f < 3.6) __finger(g[0], g[1], f < 3.4);
        else __finger(null);
        """),
    # three companies, each under its lion standard, marching in column
    "banners": dict(dur=8, warm=0.6, setup=CLEAR + r"""
        __clearAnimals(0, 0, 56, 56);
        const a = __army(0,'swords',12,11,30.0,4,0.7), b = __army(0,'swords',12,14.5,34.5,4,0.7), c = __army(0,'archer',10,9.5,35.5,4,0.7);
        window.__A = a.concat(b, c); orderMove(a, 27, 29.0); orderMove(b, 30.5, 33.5); orderMove(c, 25.5, 34.5);
        """,
        cam="__track(f, __A, 1.8, 0.1, -0.5, 0.06)"),
    # pitched battle on the cleared ground: blue from the west, red from the east
    "battle": dict(dur=9, warm=2.2, setup=CLEAR + r"""
        window.__B = __army(0,'swords',14,20.5,35.5,7,0.9); window.__BA = __army(0,'archer',10,17.5,35.5,5,0.9);
        window.__R = __army(1,'swords',14,27.5,34.5,7,0.9); window.__RA = __army(1,'archer',10,30.5,34.5,5,0.9);
        __amove(__B, 27, 35); __amove(__R, 21, 36); __amove(__BA, 22, 36); __amove(__RA, 26, 35);
        """,
        cam="__track(f, __B.concat(__R), __lerp(2.2, 2.5, f/9), -0.2, -0.2, 0.05)"),
    # villagers hunt a boar: it charges, they bring it down
    "boar": dict(dur=8, warm=0.3, setup=CLEAR + r"""
        __clearAnimals(20, 20, 45, 40);
        window.__boar = __animal('boar', 31.0, 27.4, 300);
        window.__H = []; for (let i = 0; i < 2; i++) { const u = mkUnit(0,'vill', 33.6 + i*0.7, 30.6 + i*0.2); __H.push(u); }
        """,
        events=[(0.6, "__H.forEach(u => setGather(u, __boar));")],
        cam="__pan(f, 8, [32.3,29.0,3.5], [31.9,28.8,3.9])"),
    # five archers walk into the guard tower; the next red column eats a six-arrow volley
    "garrison": dict(dur=9, warm=0.3, setup=VILLAGE + r"""
        const tw = __tower;
        window.__GA = __army(0,'archer',5,tw.cx-3.2,tw.cy+0.6,5,0.8); orderMove(__GA, tw.cx-0.9, tw.cy+0.9);
        """,
        events=[(2.0, "garrisonVillagers(__GA, __tower); ping(__tower.cx,__tower.cy,'#7fd4ff');"),
                (2.4, "const tw = __tower; window.__R = __army(1,'swords',12,tw.cx+8.0,tw.cy-2.5,4,0.75); __R.forEach(u => { u.order = {type:'attack', target: tw}; u.path = null; u.nT = 0; });")],
        cam="const tw = __tower; __pan(f, 4.0, [tw.cx-0.8, tw.cy+0.6, 2.35], [tw.cx+1.6, tw.cy+0.2, 2.05]);"),
    # a flock of nine sheep led home through the village
    "sheep": dict(dur=7, warm=0.3, setup=HAMLET + r"""
        __clearAnimals(5, 15, 45, 45);
        window.__S = []; for (let i = 0; i < 9; i++) __S.push(__animal('sheep', 14.2 + (i%3)*0.7 + Math.random()*0.3, 30.4 + Math.floor(i/3)*0.7, 120, 0));
        const sh = mkUnit(0,'vill',13.6,31.2); window.__S.push(sh);
        sheepSel = __S.filter(r => r.kind === 'sheep'); leadSheep(22.2, 30.2); orderMove([sh], 21.4, 30.6); sheepSel = [];
        """,
        cam="__track(f, __S.map(o => ({x: o.gx !== undefined ? o.gx : o.x, y: o.gy !== undefined ? o.gy : o.y, dead: false})), 3.3, 0, -0.1, 0.07)"),
    # the march on the enemy capital: the Town Center falls, then the game's own Victory screen
    "victory": dict(dur=9, warm=0.3, setup=r"""
        window.__etc = buildings.find(b => b.team === 1 && b.type === 'tc');
        units.filter(u => u.team === 1).forEach(u => u.dead = true); units = units.filter(u => !u.dead);
        buildings.filter(b => b.team === 1 && b !== __etc).forEach(b => { b.hp = b.maxhp; });
        checkEnd = () => {};
        __etc.hp = 520;
        window.__A = __army(0,'swords',12,42.6,18.4,4,0.75).concat(__army(0,'archer',8,41.0,19.6,4,0.75));
        __A.forEach(u => { u.order = {type:'attack', target: __etc}; u.path = null; u.nT = 0; });
        document.head.insertAdjacentHTML('beforeend', '<style>#endOv.__show{display:flex!important}</style>');
        $('endTitle').textContent = 'Victory'; $('endSub').textContent = 'The enemy Town Center lies in ruins.';
        $('nextBtn').style.display = ''; $('againBtn').textContent = 'Play Again';
        """,
        events=[(6.9, "$('endOv').style.display = 'flex'; $('endOv').classList.add('__show'); $('endOv').style.opacity = 0;")],
        cam=r"""
        __look(__lerp(43.4, 44.0, f/7), __lerp(13.4, 12.6, f/7), __lerp(1.75, 1.95, f/7));
        if (f > 6.9) $('endOv').style.opacity = __ease((f - 6.9) / 0.6);
        """),
    # PHONE (852x393 touch viewport): Select button, a box round the villagers, House (glow), drag, place
    "phone_build": dict(dur=9, warm=0.6, hud=True, phone=True, css=PHONE_CSS, setup=HAMLET + r"""
        __toastsGT(); DEFS.house.t = 4;
        window.__V = []; for (let i = 0; i < 6; i++) __V.push(mkUnit(0,'vill',22.4 + (i%3)*0.8, 32.0 + Math.floor(i/3)*0.8));
        __look(24.2, 30.6, 1.9);
        window.__dst = [23.0, 29.2];
        """,
        events=[(0.9, "$('selBtn').dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));"),
                (3.0, "box.x1 = __bx[2]; box.y1 = __bx[3]; doBox(); box = null;"),
                (4.0, "startPlace('house')"),
                (6.4, "tryPlace(__dst[0], __dst[1])")],
        cam=r"""
        if (f < 1.5 || !window.__bx) { const P = __V.map(u => __scr(u.x, u.y));
          window.__bx = [Math.min(...P.map(p => p[0])) - 22, Math.min(...P.map(p => p[1])) - 40, Math.max(...P.map(p => p[0])) + 22, Math.max(...P.map(p => p[1])) + 14]; }
        const sb = __el('#selBtn');
        if (f < 0.9) __finger(__lerp(330, sb[0], __ease(f/0.8)), __lerp(200, sb[1], __ease(f/0.8)), f > 0.78);
        else if (f < 1.5) __finger(__lerp(sb[0], __bx[0], __ease((f-0.9)/0.55)), __lerp(sb[1], __bx[1], __ease((f-0.9)/0.55)), false);
        else if (f < 3.0) { const t = __ease((f-1.5)/1.4); if (!box) box = {x0: __bx[0], y0: __bx[1], x1: __bx[0], y1: __bx[1], active: true};
          box.x1 = __lerp(__bx[0], __bx[2], t); box.y1 = __lerp(__bx[1], __bx[3], t); __finger(box.x1, box.y1, true); }
        else if (f < 4.0) { const hb = __el('#panel .abtn[title="House"]') || [__bx[2], __bx[3]];
          __finger(__lerp(__bx[2], hb[0], __ease((f-3.1)/0.7)), __lerp(__bx[3], hb[1], __ease((f-3.1)/0.7)), f > 3.85); }
        else if (f < 6.4) { const g = __scr(__dst[0], __dst[1]);
          if (placing && !placing.g0) placing.g0 = placing.ghost.slice();
          if (placing) { const st = __scr(placing.g0[0], placing.g0[1]), t = __ease((f-4.4)/1.6);
            const px = __lerp(st[0], g[0], t), py = __lerp(st[1], g[1], t); placing.ghost = scr2w(px, py); __finger(px, py, f > 4.5 && f < 6.3); } }
        else if (f < 6.8) { const g = __scr(__dst[0], __dst[1]); __finger(g[0], g[1], f < 6.55); }
        else __finger(null);
        """),
    # PHONE: an army selected and driven with the thumb stick; the camera follows
    "phone_army": dict(dur=7, warm=1, hud=True, phone=True, css=PHONE_CSS, setup=CLEAR + r"""
        __toastsGT();
        window.__A = __army(0,'swords',10,17,40,5,0.85).concat(__army(0,'archer',6,17,42,3,0.85));
        selection = __A.slice(); refreshPanel(true); followMute = 1e9;
        popCap[0] = 40;   // no houses in this staging, so the pill would read 19/5
        __look(18.5,40.5,1.9);
        joy.id = 1; joy.mode = 'units';
        window.__thumb = (vx, vy) => { const r = joyBase.getBoundingClientRect();
          const x = r.left + r.width/2 + vx * r.width * 0.42, y = r.top + r.height/2 + vy * r.width * 0.42;
          joyUpdate({clientX: x, clientY: y}); __finger(x, y, true); };
        """,
        cam="const m = __ease(f/0.5) * 0.95, ang = -0.35 + 0.55*Math.sin(f*0.7); __thumb(Math.cos(ang)*m, Math.sin(ang)*m*0.8);"
            "__track(f, __A, __lerp(1.9, 2.05, f/7), 0.6, -0.2, 0.06);"),
    # the title screen, every level unlocked
    "title": dict(dur=0.2, warm=0, title=True, init="localStorage.setItem('pe_level_unlocked','10'); localStorage.setItem('pe_level_next','1');", setup="0"),
}
