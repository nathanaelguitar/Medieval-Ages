#!/usr/bin/env python
"""Hunyuan3D-2 driver for the sprite pipeline: image(s) -> white mesh -> UV-pinned textured GLBs.

Runs on the DGX with ~/hunyuan3d/.venv/bin/python (hy3dgen is installed there in editable mode).
Inputs are the RGBA squares written by prep_images.py (already background-removed).

Three sub-commands so each stage can be re-run on its own:

  shape   images -> reduced white mesh (.obj) + raw mesh (.ply)
          --mode mv      tencent/Hunyuan3D-2mv, dict of views (front, back, left, right)
          --mode single  tencent/Hunyuan3D-2 single-image DiT (front only)
  uv      white mesh -> same mesh with one xatlas UV layout baked in (.obj). Done ONCE, so every
          texture painted afterwards shares vertices, faces and UVs: the two teams can then be the
          same rigged mesh with the image swapped.
  paint   UV'd mesh + one reference image -> textured GLB. The paint pipeline's own xatlas call is
          bypassed when the mesh already carries UVs, otherwise it would re-wrap (and re-order
          vertices) per run.

Examples:
  hy3d_body.py shape --mode mv --front prep/blue_apose_front.png --back prep/blue_apose_back.png \
      --out work/body_mv --faces 36000
  hy3d_body.py uv --mesh work/body_mv/white.obj --out work/body_uv.obj
  hy3d_body.py paint --mesh work/body_uv.obj --image prep/blue_apose_front.png --out work/blue.glb
"""
import argparse, os, sys, time, json
import numpy as np
import torch, trimesh
from PIL import Image


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_rgba(path):
    im = Image.open(path)
    if im.mode != "RGBA":
        sys.exit(f"{path}: expected RGBA from prep_images.py, got {im.mode}")
    return im


def cmd_shape(a):
    from hy3dgen.shapegen import (Hunyuan3DDiTFlowMatchingPipeline, FaceReducer, FloaterRemover,
                                  DegenerateFaceRemover)
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    if a.mode == "single":
        pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
            "tencent/Hunyuan3D-2", subfolder="hunyuan3d-dit-v2-0", variant="fp16")
        inp = load_rgba(a.front)
    else:
        pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
            "tencent/Hunyuan3D-2mv", subfolder="hunyuan3d-dit-v2-mv", variant="fp16")
        inp = {k: load_rgba(v) for k, v in (("front", a.front), ("back", a.back),
                                             ("left", a.left), ("right", a.right)) if v}
    log(f"model loaded in {time.time()-t0:.0f}s; views={list(inp) if isinstance(inp, dict) else 'single'}")
    ts = time.time()
    mesh = pipe(image=inp, num_inference_steps=a.steps, octree_resolution=a.octree,
                guidance_scale=a.guidance, num_chunks=20000,
                generator=torch.manual_seed(a.seed), output_type="trimesh")[0]
    t_shape = time.time() - ts
    log(f"shape {t_shape:.1f}s raw faces {len(mesh.faces)} peak {torch.cuda.max_memory_allocated()/2**30:.1f}GiB")
    del pipe; torch.cuda.empty_cache()
    mesh.export(os.path.join(a.out, "raw.ply"))
    mesh = FloaterRemover()(mesh)
    mesh = DegenerateFaceRemover()(mesh)
    mesh = FaceReducer()(mesh, max_facenum=a.faces)
    mesh.export(os.path.join(a.out, "white.obj"))
    ext = mesh.bounds[1] - mesh.bounds[0]
    log(f"reduced faces {len(mesh.faces)} verts {len(mesh.vertices)} extent {np.round(ext, 3).tolist()} "
        f"watertight={mesh.is_watertight}")
    with open(os.path.join(a.out, "shape.json"), "w") as fh:
        json.dump({"mode": a.mode, "steps": a.steps, "octree": a.octree, "seed": a.seed,
                   "guidance": a.guidance, "faces": len(mesh.faces), "shape_seconds": round(t_shape, 1),
                   "views": list(inp) if isinstance(inp, dict) else ["front"]}, fh, indent=1)


def cmd_uv(a):
    import xatlas
    mesh = trimesh.load(a.mesh, force="mesh")
    t0 = time.time()
    vmapping, indices, uvs = xatlas.parametrize(mesh.vertices, mesh.faces)
    out = trimesh.Trimesh(vertices=mesh.vertices[vmapping], faces=indices, process=False)
    out.visual = trimesh.visual.TextureVisuals(uv=uvs)
    out.export(a.out)
    log(f"uv: {len(mesh.vertices)} -> {len(out.vertices)} verts, {len(out.faces)} faces, {time.time()-t0:.1f}s -> {a.out}")


def cmd_paint(a):
    import hy3dgen.texgen.pipelines as P
    from hy3dgen.texgen import Hunyuan3DPaintPipeline
    mesh = trimesh.load(a.mesh, force="mesh", process=False)
    has_uv = getattr(mesh.visual, "uv", None) is not None and len(mesh.visual.uv) == len(mesh.vertices)
    if has_uv:
        P.mesh_uv_wrap = lambda m: m        # keep the pinned layout
        log(f"mesh has UVs ({len(mesh.vertices)} verts); paint pipeline's xatlas bypassed")
    else:
        log("mesh has no UVs; the paint pipeline will wrap it (layout NOT pinned)")
    t0 = time.time()
    paint = Hunyuan3DPaintPipeline.from_pretrained("tencent/Hunyuan3D-2")
    log(f"paint model loaded in {time.time()-t0:.0f}s")
    ts = time.time()
    textured = paint(mesh, image=load_rgba(a.image))
    log(f"paint {time.time()-ts:.1f}s peak {torch.cuda.max_memory_allocated()/2**30:.1f}GiB")
    textured.export(a.out)
    tex = getattr(getattr(textured.visual, "material", None), "image", None)
    log(f"-> {a.out} faces={len(textured.faces)} verts={len(textured.vertices)} "
        f"texture={tex.size if tex is not None else None} size={os.path.getsize(a.out)/1e6:.1f}MB")
    if has_uv:
        same = (np.allclose(textured.vertices, mesh.vertices) and np.array_equal(textured.faces, mesh.faces))
        log(f"geometry identical to input: {same}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("shape")
    s.add_argument("--mode", choices=("mv", "single"), default="mv")
    s.add_argument("--front", required=True)
    for k in ("back", "left", "right"):
        s.add_argument("--" + k)
    s.add_argument("--out", required=True)
    s.add_argument("--faces", type=int, default=36000)
    s.add_argument("--steps", type=int, default=50)
    s.add_argument("--octree", type=int, default=384)
    s.add_argument("--guidance", type=float, default=7.5)
    s.add_argument("--seed", type=int, default=12345)
    u = sub.add_parser("uv"); u.add_argument("--mesh", required=True); u.add_argument("--out", required=True)
    p = sub.add_parser("paint")
    p.add_argument("--mesh", required=True); p.add_argument("--image", required=True); p.add_argument("--out", required=True)
    a = ap.parse_args()
    {"shape": cmd_shape, "uv": cmd_uv, "paint": cmd_paint}[a.cmd](a)


if __name__ == "__main__":
    main()
