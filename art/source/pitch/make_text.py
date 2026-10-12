#!/usr/bin/env python3
"""Text, cards and icons for the Poki pitch kit (runs on the Mac: needs Palatino.ttc).

Writes to OUT (default art/out/pitch/text):
  title_bg.png    1920x1080 key art, darkened to the left like the game's title screen
  title_text.png  RGBA "MEDIEVAL AGES" + tagline, in the game's gold Palatino title style
  end_text.png    RGBA title + "Play free on web & mobile"
  cap_*.png       RGBA one-word captions, small, lower left
  phone_label.png RGBA line under the phone frame
  phone_bezel.png RGBA generic landscape phone (no brand, punch-hole camera) whose screen hole is
                  PHONE_SCREEN; make_phone.sh lays the 852x393 phone capture under it
and the committed small deliverables to art/source/pitch/:
  icons/icon_512.png, icons/icon_256.png   (from art/source/icon/icon_b_king.png)
  thumbnail_1280x720.jpg                   (key art + title, for portal listings)
Usage: make_text.py [OUT]
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "../../.."))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "art/out/pitch/text")
os.makedirs(OUT, exist_ok=True)
PAL = "/System/Library/Fonts/Palatino.ttc"
REG, ITAL, BOLD = 0, 1, 2
# index.html #startOv .title: #e3c27a, the "AGES" line #c99c4f, hard shadow #3e2e0e, cream tag #e4dcc6
GOLD, GOLD_D, CREAM, SHADOW = (227, 194, 122), (201, 156, 79), (228, 220, 198), (62, 46, 14)
KEYART = os.path.join(ROOT, "art/source/keyart/keyart_v1.png")
ICON = os.path.join(ROOT, "art/source/icon/icon_b_king.png")

def font(sz, face=BOLD): return ImageFont.truetype(PAL, sz, index=face)

def tracked(d, xy, text, f, fill, tr):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill); x += d.textlength(ch, font=f) + tr
    return x

def twidth(text, f, tr):
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    return sum(d.textlength(ch, font=f) for ch in text) + tr * (len(text) - 1)

def layer(size, lines, glow=28, hard=None, scrim=0):
    """lines: [(text, px, face, rgb, x, y, tracking, align)] -> RGBA with the title's two shadows
    (a hard 1/36-size drop in dark brown and a wide soft black glow); align 'l' or 'c' (x = centre)."""
    W, H = size
    fg = Image.new("RGBA", size); d = ImageDraw.Draw(fg)
    for text, px, face, col, x, y, tr, al in lines:
        f = font(px, face); w = twidth(text, f, tr)
        tracked(d, (x - w / 2 if al == "c" else x, y), text, f, col + (255,), tr)
    a = fg.split()[3]
    out = Image.new("RGBA", size)
    if scrim:
        bb = a.getbbox(); sc = Image.new("L", size, 0)
        ImageDraw.Draw(sc).rounded_rectangle([bb[0] - 60, bb[1] - 40, bb[2] + 60, bb[3] + 40], 60, fill=scrim)
        pool = Image.new("RGBA", size, (8, 6, 3, 0)); pool.putalpha(sc.filter(ImageFilter.GaussianBlur(34))); out.alpha_composite(pool)
    sh = Image.new("RGBA", size, (0, 0, 0, 0)); sh.putalpha(a.filter(ImageFilter.GaussianBlur(glow)).point(lambda v: min(255, int(v * 0.75 * 1.5))))
    out.alpha_composite(sh, (0, int(glow * 0.3)))
    if hard:
        hd = Image.new("RGBA", size, SHADOW + (0,)); hd.putalpha(a); out.alpha_composite(hd, (0, hard))
    out.alpha_composite(fg)
    return out

def cover(im, W, H, ax=0.5, ay=0.5):
    s = max(W / im.width, H / im.height); im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x, y = round((im.width - W) * ax), round((im.height - H) * ay)
    return im.crop((x, y, x + W, y + H))

def keyart_bg(W, H):
    """The title screen's treatment: key art at 62% x, a dark wash from the left edge."""
    bg = cover(Image.open(KEYART).convert("RGB"), W, H, 0.62, 0.5).convert("RGBA")
    g = Image.new("L", (W, 1))
    stops = [(0, .92), (.30, .72), (.62, .15), (.80, 0), (1, 0)]
    for x in range(W):
        t = x / (W - 1)
        for (t0, a0), (t1, a1) in zip(stops, stops[1:]):
            if t0 <= t <= t1: g.putpixel((x, 0), int(255 * (a0 + (a1 - a0) * (t - t0) / (t1 - t0)))); break
    wash = Image.new("RGBA", (W, H), (7, 9, 5, 0)); wash.putalpha(g.resize((W, H)))
    bg.alpha_composite(wash)
    return bg

def title_lines(W, H, x, y, px, tag=None, tagpx=None):
    """MEDIEVAL / AGES stacked, left-aligned at x, top y, as #startOv .title draws it."""
    lines = [("MEDIEVAL", px, BOLD, GOLD, x, y, px * 0.05, "l"),
             ("AGES", px, BOLD, GOLD_D, x, y + px * 0.92, px * 0.32, "l")]
    if tag: lines.append((tag, tagpx, ITAL, CREAM, x + 4, y + px * 0.92 * 2 + tagpx * 0.6, 0, "l"))
    return lines

PHONE_SCREEN = (180, 170, 1560, 720)    # x, y, w, h of the screen in the 1920x1080 frame (852x393 scaled by 1.831)

def phone_bezel(W=1920, H=1080):
    x, y, w, h = PHONE_SCREEN; m, rs, rb = 26, 50, 74
    out = Image.new("RGBA", (W, H))
    # soft shadow under the device
    sh = Image.new("L", (W, H), 0); ImageDraw.Draw(sh).rounded_rectangle([x - m, y - m + 18, x + w + m, y + h + m + 18], rb, fill=170)
    # only outside the device: this layer sits over the video, so a shadow inside it would dim the screen
    outside = Image.new("L", (W, H), 255); ImageDraw.Draw(outside).rounded_rectangle([x - m, y - m, x + w + m, y + h + m], rb, fill=0)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0)); shadow.putalpha(Image.composite(sh.filter(ImageFilter.GaussianBlur(26)), Image.new("L", (W, H), 0), outside))
    out.alpha_composite(shadow)
    body = Image.new("RGBA", (W, H)); d = ImageDraw.Draw(body)
    # side keys on the top edge (landscape), then the body, a lighter rim, and the black glass border
    for k0, k1 in ((x + 260, x + 380), (x + 420, x + 500)):
        d.rounded_rectangle([k0, y - m - 6, k1, y - m + 8], 4, fill=(52, 55, 60, 255))
    d.rounded_rectangle([x - m, y - m, x + w + m, y + h + m], rb, fill=(30, 32, 36, 255), outline=(92, 96, 104, 255), width=3)
    d.rounded_rectangle([x - m + 7, y - m + 7, x + w + m - 7, y + h + m - 7], rb - 7, fill=(8, 8, 10, 255))
    # punch-hole camera in the left bezel
    cy = y + h // 2; d.ellipse([x - 17, cy - 7, x - 3, cy + 7], fill=(22, 26, 34, 255), outline=(44, 48, 58, 255))
    hole = Image.new("L", (W, H), 255); ImageDraw.Draw(hole).rounded_rectangle([x, y, x + w - 1, y + h - 1], rs, fill=0)
    body.putalpha(Image.composite(body.split()[3], Image.new("L", (W, H), 0), hole))
    out.alpha_composite(body)
    # a faint glass sheen across the top-left of the screen
    sheen = Image.new("L", (W, H), 0); ImageDraw.Draw(sheen).polygon([(x, y), (x + 520, y), (x + 140, y + h), (x, y + h)], fill=10)
    hole_in = Image.new("L", (W, H), 0); ImageDraw.Draw(hole_in).rounded_rectangle([x, y, x + w - 1, y + h - 1], rs, fill=255)
    gl = Image.new("RGBA", (W, H), (255, 255, 255, 0)); gl.putalpha(Image.composite(sheen, Image.new("L", (W, H), 0), hole_in).filter(ImageFilter.GaussianBlur(30)))
    out.alpha_composite(gl)
    return out

def main():
    W, H = 1920, 1080
    keyart_bg(W, H).convert("RGB").save(os.path.join(OUT, "title_bg.png"))
    px = 136; x = 140; y = H / 2 - px * 1.25
    layer((W, H), title_lines(W, H, x, y, px, "Build a village. Raise an army. Hold the realm.", 40), glow=26, hard=5).save(os.path.join(OUT, "title_text.png"))
    layer((W, H), title_lines(W, H, x, y, px, "Play free on web & mobile", 46), glow=26, hard=5).save(os.path.join(OUT, "end_text.png"))
    # small captions, lower left, clear of every HUD element we keep on screen in those beats
    for n, t in [("gather", "Gather"), ("build", "Build"), ("defend", "Defend"), ("army", "Raise an army"),
                 ("conquer", "Conquer"), ("hunt", "Hunt & herd")]:
        layer((W, H), [(t, 58, BOLD, GOLD, 96, 940, 3, "l")], glow=12, hard=3, scrim=110).save(os.path.join(OUT, f"cap_{n}.png"))
    layer((W, H), [("Built for touch", 52, BOLD, GOLD, W / 2, 965, 3, "c")], glow=12, hard=3).save(os.path.join(OUT, "phone_label.png"))
    layer((W, H), [("Plays on a phone", 52, BOLD, GOLD, W / 2, 965, 3, "c")], glow=12, hard=3).save(os.path.join(OUT, "phone_label2.png"))

    phone_bezel().save(os.path.join(OUT, "phone_bezel.png"))
    # thumbnail 1280x720: key art with the title
    tw, th = 1280, 720
    t = keyart_bg(tw, th); tp = 98
    t.alpha_composite(layer((tw, th), title_lines(tw, th, 92, th / 2 - tp * 1.2, tp, "A real-time strategy game", 30), glow=18, hard=4))
    t.convert("RGB").save(os.path.join(HERE, "thumbnail_1280x720.jpg"), quality=90)
    # icons
    os.makedirs(os.path.join(HERE, "icons"), exist_ok=True)
    ic = Image.open(ICON).convert("RGB")
    for s in (512, 256):
        ic.resize((s, s), Image.LANCZOS).save(os.path.join(HERE, "icons", f"icon_{s}.png"), optimize=True)
    print("wrote", OUT, "and", HERE)

if __name__ == "__main__":
    main()
