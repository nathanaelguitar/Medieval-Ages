#!/usr/bin/env python3
"""Render the promo's text as 1080x1920 RGBA overlays (Palatino, the game's title gold) and the
end-card background. Everything sits inside TikTok/Reels' safe zone: x 70..900 (the right rail of
buttons starts near x 930) and y 220..1500 (the caption/username block covers the bottom ~20%).
Usage: make_text.py OUTDIR      (importable: text_layer/caption/font are reused by make_text_b2.py)"""
import os, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT = None
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "../../.."))
W, H = 1080, 1920
CX = 485                     # optical centre, nudged left of 540 to clear the right-hand button rail
PAL = "/System/Library/Fonts/Palatino.ttc"
REG, ITAL, BOLD = 0, 1, 2
GOLD, GOLD_D, CREAM = (227, 194, 122), (201, 156, 79), (228, 220, 198)

def font(sz, face=BOLD): return ImageFont.truetype(PAL, sz, index=face)

def text_layer(lines, scrim=0):
    """lines: [(text, size, face, colour, y, tracking)] -> RGBA with a soft drop shadow."""
    fg = Image.new("RGBA", (W, H)); d = ImageDraw.Draw(fg)
    for text, sz, face, col, y, tr in lines:
        f = font(sz, face)
        widths = [d.textlength(ch, font=f) for ch in text]; tw = sum(widths) + tr * (len(text) - 1)
        assert tw < 830, (text, tw)
        x = CX - tw / 2
        for ch, w in zip(text, widths):
            d.text((x, y), ch, font=f, fill=col + (255,)); x += w + tr
    a = fg.split()[3]
    sh = Image.new("RGBA", (W, H), (8, 6, 2, 0)); sh.putalpha(a.filter(ImageFilter.GaussianBlur(10)).point(lambda v: min(255, int(v * 1.6))))
    hard = Image.new("RGBA", (W, H), (62, 46, 14, 0)); hard.putalpha(a)
    out = Image.new("RGBA", (W, H))
    if scrim:   # a soft dark pool behind the words so they read over busy gameplay
        bb = a.getbbox(); sc = Image.new("L", (W, H), 0)
        ImageDraw.Draw(sc).ellipse([bb[0] - 140, bb[1] - 90, bb[2] + 140, bb[3] + 90], fill=scrim)
        pool = Image.new("RGBA", (W, H), (10, 8, 4, 0)); pool.putalpha(sc.filter(ImageFilter.GaussianBlur(60))); out.alpha_composite(pool)
    out.alpha_composite(sh); out.alpha_composite(hard, (0, 3)); out.alpha_composite(fg)
    return out

def caption(name, text, size=86, y=300):
    lines = text.split("|")
    text_layer([(t, size, BOLD, GOLD, y + i * int(size * 1.12), 2) for i, t in enumerate(lines)], scrim=120).save(os.path.join(OUT, f"cap_{name}.png"))

def main():
  global OUT
  OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)

  # one-word beats for the hook cut
  for w in ["BUILD.", "GATHER.", "MARCH.", "CONQUER."]:
      caption("w_" + w.strip(".").lower(), w, 112, 290)
  # how-it-plays captions
  for n, t in [("village", "Build your|village"), ("army", "Raise an army"), ("thumb", "Command it|with a thumb"), ("realm", "Hold the realm")]:
      caption(n, t, 88, 290)
  # a small "real gameplay" tag for gameplay beats that follow AI-film shots
  text_layer([("GAMEPLAY", 34, REG, CREAM, 236, 9)], scrim=90).save(os.path.join(OUT, "tag_gameplay.png"))

  # end card text
  title = text_layer([
      ("MEDIEVAL", 132, BOLD, GOLD, 1010, 6),
      ("AGES", 132, BOLD, GOLD_D, 1150, 40),
      ("Build a village. Raise an army.", 46, ITAL, CREAM, 1318, 1),
      ("Hold the realm.", 46, ITAL, CREAM, 1374, 1),
  ])
  dl = ImageDraw.Draw(title); dl.line([(CX - 150, 1300), (CX + 150, 1300)], fill=GOLD_D + (200,), width=2)
  title.save(os.path.join(OUT, "title_text.png"))
  text_layer([("FREE ON MOBILE  ·  SOON", 38, REG, GOLD, 1458, 5)]).save(os.path.join(OUT, "title_soon.png"))

  # end card background: the crowned king flanked by a man-at-arms and an archer, fading into dark
  bg = Image.new("RGB", (W, H), (9, 9, 7))
  king = Image.open(os.path.join(ROOT, "art/source/icon/icon_b_king.png")).convert("RGB").resize((1240, 1240), Image.LANCZOS)
  top = 40; bg.paste(king, ((W - 1240) // 2 - 40, top))
  grad = Image.new("L", (W, H), 0); gd = ImageDraw.Draw(grad)
  for y in range(H):
      t = (y - (top + 560)) / 560.0          # fade from mid-portrait to fully dark by ~y 1160
      gd.line([(0, y), (W, y)], fill=int(255 * max(0.0, min(1.0, t))))
  dark = Image.new("RGB", (W, H), (9, 9, 7)); bg = Image.composite(dark, bg, grad)
  vig = Image.new("L", (W, H), 0); ImageDraw.Draw(vig).rectangle([0, 0, W, 140], fill=150); vig = vig.filter(ImageFilter.GaussianBlur(80))
  bg = Image.composite(dark, bg, vig)
  bg.save(os.path.join(OUT, "title_bg.jpg"), quality=92)
  print("ok")

if __name__ == "__main__":
    main()
