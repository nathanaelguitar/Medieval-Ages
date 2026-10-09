#!/usr/bin/env python
"""Prepare reference crops for Hunyuan3D: upscale (Real-ESRGAN x4, LANCZOS fallback), remove the
studio background (bria-rmbg via hy3dgen's BackgroundRemover), tight-crop, pad to a square.

Runs on the DGX with ~/hunyuan3d/.venv/bin/python:

    python prep_images.py --in ~/hunyuan3d/inputs/man_at_arms --out ~/hunyuan3d/work/man_at_arms/prep \
        blue_apose_front blue_apose_back red_apose_front red_apose_back blue_shield blue_sword ...

Writes <name>.png (RGBA, square, transparent background) plus <name>_up.png (upscaled, no alpha)
so the upscale can be inspected on its own.

Real-ESRGAN is loaded without the `basicsr`/`realesrgan` packages: `basicsr` imports a torchvision
symbol removed in 0.17, so the RRDBNet generator is vendored here (it is ~60 lines) and the
official RealESRGAN_x4plus.pth weights are loaded straight into it.
"""
import argparse, os, sys, time
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image

WEIGHTS = os.path.expanduser("~/hunyuan3d/weights/RealESRGAN_x4plus.pth")


# ---- vendored RRDBNet (Real-ESRGAN x4plus generator) ------------------------------------------
class ResidualDenseBlock(nn.Module):
    def __init__(self, nf=64, gc=32):
        super().__init__()
        self.conv1 = nn.Conv2d(nf, gc, 3, 1, 1)
        self.conv2 = nn.Conv2d(nf + gc, gc, 3, 1, 1)
        self.conv3 = nn.Conv2d(nf + 2 * gc, gc, 3, 1, 1)
        self.conv4 = nn.Conv2d(nf + 3 * gc, gc, 3, 1, 1)
        self.conv5 = nn.Conv2d(nf + 4 * gc, nf, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(0.2, inplace=True)

    def forward(self, x):
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
        return x5 * 0.2 + x


class RRDB(nn.Module):
    def __init__(self, nf, gc=32):
        super().__init__()
        self.rdb1 = ResidualDenseBlock(nf, gc)
        self.rdb2 = ResidualDenseBlock(nf, gc)
        self.rdb3 = ResidualDenseBlock(nf, gc)

    def forward(self, x):
        out = self.rdb3(self.rdb2(self.rdb1(x)))
        return out * 0.2 + x


class RRDBNet(nn.Module):
    def __init__(self, in_ch=3, out_ch=3, nf=64, nb=23, gc=32):
        super().__init__()
        self.conv_first = nn.Conv2d(in_ch, nf, 3, 1, 1)
        self.body = nn.Sequential(*[RRDB(nf, gc) for _ in range(nb)])
        self.conv_body = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_up1 = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_up2 = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_hr = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_last = nn.Conv2d(nf, out_ch, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(0.2, inplace=True)

    def forward(self, x):
        feat = self.conv_first(x)
        feat = feat + self.conv_body(self.body(feat))
        feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
        feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
        return self.conv_last(self.lrelu(self.conv_hr(feat)))


def load_esrgan(device):
    if not os.path.exists(WEIGHTS):
        print(f"no Real-ESRGAN weights at {WEIGHTS}; using LANCZOS", file=sys.stderr)
        return None
    net = RRDBNet()
    sd = torch.load(WEIGHTS, map_location="cpu")
    sd = sd.get("params_ema", sd.get("params", sd))
    net.load_state_dict(sd, strict=True)
    return net.eval().to(device)


@torch.no_grad()
def upscale(im, net, device, tile=256, pad=16):
    """x4 upscale; tiled so a 1200px side still fits comfortably."""
    if net is None:
        return im.resize((im.width * 4, im.height * 4), Image.LANCZOS)
    x = torch.from_numpy(np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0).permute(2, 0, 1)[None].to(device)
    _, _, h, w = x.shape
    out = torch.zeros((1, 3, h * 4, w * 4), device=device)
    for y0 in range(0, h, tile):
        for x0 in range(0, w, tile):
            y1, x1 = min(h, y0 + tile), min(w, x0 + tile)
            py0, px0 = max(0, y0 - pad), max(0, x0 - pad)
            py1, px1 = min(h, y1 + pad), min(w, x1 + pad)
            o = net(x[:, :, py0:py1, px0:px1])
            out[:, :, y0 * 4:y1 * 4, x0 * 4:x1 * 4] = o[:, :, (y0 - py0) * 4:(y1 - py0) * 4, (x0 - px0) * 4:(x1 - px0) * 4]
    arr = (out[0].clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).round().astype(np.uint8)
    return Image.fromarray(arr)


def square_pad(rgba, margin=0.06, size=1024):
    bbox = rgba.getchannel("A").point(lambda a: 255 if a > 16 else 0).getbbox()
    if bbox:
        rgba = rgba.crop(bbox)
    side = int(max(rgba.size) * (1 + 2 * margin))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(rgba, ((side - rgba.width) // 2, (side - rgba.height) // 2))
    return canvas.resize((size, size), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-upscale", action="store_true")
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("names", nargs="+")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    net = None if a.no_upscale else load_esrgan(device)
    from hy3dgen.rembg import BackgroundRemover
    rembg = BackgroundRemover()
    for name in a.names:
        t0 = time.time()
        im = Image.open(os.path.join(a.inp, name + ".png")).convert("RGB")
        up = im if a.no_upscale else upscale(im, net, device)
        up.save(os.path.join(a.out, name + "_up.png"))
        rgba = rembg(up)
        sq = square_pad(rgba, size=a.size)
        sq.save(os.path.join(a.out, name + ".png"))
        cov = np.asarray(sq.getchannel("A")).mean() / 255
        print(f"{name}: {im.size} -> {up.size} -> {sq.size} alpha coverage {cov:.2f}  {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
