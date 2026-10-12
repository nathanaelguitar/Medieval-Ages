#!/usr/bin/env python3
"""Text overlays for the batch-2 promos (ten daily posts), in the same gold Palatino style as
make_text.py and inside the same TikTok/Shorts safe zone (x 70..900, y 220..1500).
Usage: make_text_b2.py OUTDIR        -> OUTDIR/cap_<key>.png, tag_*.png, title_text_b2.png, title_soon_b2.png
Long captions shrink until every line fits 800 px."""
import os, sys
from PIL import ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_text as mt
from make_text import text_layer, font, REG, ITAL, BOLD, GOLD, GOLD_D, CREAM, CX

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
MAXW = 800

def width(text, sz, face, tr):
    d = ImageDraw.Draw(mt.Image.new("RGBA", (10, 10))); f = font(sz, face)
    return sum(d.textlength(ch, font=f) for ch in text) + tr * (len(text) - 1)

def cap(key, text, size=86, y=290, face=BOLD, col=GOLD):
    lines = text.split("|")
    while max(width(t, size, face, 2) for t in lines) > MAXW: size -= 2
    text_layer([(t, size, face, col, y + i * int(size * 1.12), 2) for i, t in enumerate(lines)], scrim=120).save(os.path.join(OUT, f"cap_{key}.png"))
    return size

# key: text ("|" = line break). Grouped by promo; a key is reused wherever the same words appear.
CAPS = {
    # 01 hold the gate (question hook)
    "gate_q": "Could you|hold the gate?", "walls": "Raise the walls", "towers": "Man the towers", "hold": "Hold.",
    # 02 POV
    "pov": "POV: your villagers|just saw the red army", "bell": "Ring the bell", "banners": "Raise the banners", "realm": "Hold the realm",
    # 03 village in 15 s
    "v15": "Building a medieval|village in 15 seconds", "defend": "Now defend it.",
    # 04 cold open
    "coming": "The red army|is coming",
    # 05 mobile reveal
    "mobile_q": "This is a|mobile game?", "thumb": "One thumb|to command", "dbl": "Double-tap:|the whole army", "phone": "Yes. On your phone.",
    # 06 devlog
    "dev": "I'm making a medieval|RTS for mobile", "selbox": "Tap Select,|drag a box", "dbl_dev": "Double-tap a soldier:|whole army",
    "wall_dev": "Draw a wall|with one finger", "garr": "Garrison a tower:|+1 arrow per archer", "follow": "Follow the build",
    # 07 mills
    "mill_q": "How medieval mills|worked", "sails": "Wind turns the sails", "stones": "Millstones grind|grain into flour",
    "fields": "Farms feed the mill", "mill_game": "In my game, farmers|bring grain to the mill",
    # 08 longbows
    "longbow": "Longbows won|medieval battles", "crecy": "Crécy, 1346|Agincourt, 1415", "volley": "Volley after volley",
    "my_archers": "My archers|do the same",
    # 09 food
    "eat_q": "What did a medieval|village eat?", "bread": "Bread from the fields", "mutton": "Mutton from the flock",
    "lords": "Boar? Mostly|for the lords", "hunt_game": "In my game,|everyone hunts", "herd": "Herd the sheep home",
    # 10 king
    "king": "Every king|needs a plan", "march": "March", "conquer": "Conquer",
}
for k, t in CAPS.items():
    sz = cap(k, t)
    if sz < 86: print(f"  {k}: shrunk to {sz}")

# small honest tags for gameplay beats
text_layer([("GAMEPLAY", 34, REG, CREAM, 236, 9)], scrim=90).save(os.path.join(OUT, "tag_gameplay.png"))
text_layer([("GAMEPLAY  ·  6× SPEED", 34, REG, CREAM, 236, 7)], scrim=90).save(os.path.join(OUT, "tag_timelapse.png"))
text_layer([("REAL GAMEPLAY", 34, REG, CREAM, 236, 9)], scrim=90).save(os.path.join(OUT, "tag_real.png"))
text_layer([("GAMEPLAY  ·  4× SPEED", 34, REG, CREAM, 236, 7)], scrim=90).save(os.path.join(OUT, "tag_speed4.png"))

# end card: the batch-1 layout lifted 60 px so the channel handle also clears the caption block
title = text_layer([
    ("MEDIEVAL", 132, BOLD, GOLD, 950, 6),
    ("AGES", 132, BOLD, GOLD_D, 1090, 40),
    ("Build a village. Raise an army.", 46, ITAL, CREAM, 1258, 1),
    ("Hold the realm.", 46, ITAL, CREAM, 1314, 1),
])
ImageDraw.Draw(title).line([(CX - 150, 1240), (CX + 150, 1240)], fill=GOLD_D + (200,), width=2)
title.save(os.path.join(OUT, "title_text_b2.png"))
text_layer([("FREE ON MOBILE  ·  SOON", 38, REG, GOLD, 1398, 5),
            ("@nathanael_medieval", 30, ITAL, CREAM, 1452, 1)]).save(os.path.join(OUT, "title_soon_b2.png"))
print("ok", len(CAPS), "captions")
