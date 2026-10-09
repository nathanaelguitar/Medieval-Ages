#!/usr/bin/env python
"""TRELLIS.2 (MIT) driver for the v2 sprite pipeline: reference views -> PBR-textured body GLBs.

Runs on the DGX Spark inside the `trellis2` Docker image (art/pipeline/docker/trellis2/Dockerfile)
through ~/trellis2/run.sh, which mounts ~/trellis2 at /trellis2 and the HF cache, e.g.

    ~/trellis2/run.sh python /trellis2/trellis_body.py shape \
        --image /trellis2/work/man_at_arms/prep/blue_apose_front_hr.png --out /trellis2/work/man_at_arms/shape

Model config: TRELLIS.2 is loaded from ~/trellis2/model (env TRELLIS2_MODEL), a copy of the HF
snapshot's pipeline json files pointing at licence-clean helpers: the DINOv3 image encoder is
read from a checksum-identical ungated mirror of facebook/dinov3-vitl16-pretrain-lvd1689m
(sha256 dcb2e451...; accept the gate on HF and sed the name back to use the official repo), and
the background remover is ZhengPeng7/BiRefNet (MIT) instead of bria RMBG-2.0 (non-commercial).
Inputs are RGBA cut-outs from prep_views.py, so the remover is only constructed, never used.
The directory was made with (in ~/hunyuan3d/.venv or the trellis2 image):

    python -c "from huggingface_hub import snapshot_download; print(snapshot_download('microsoft/TRELLIS.2-4B'))"
    snap=$(ls -d ~/.cache/huggingface/hub/models--microsoft--TRELLIS.2-4B/snapshots/*)
    mkdir -p ~/trellis2/model && ln -sfn $snap/ckpts ~/trellis2/model/ckpts
    for f in pipeline.json texturing_pipeline.json; do
        sed -e "s#facebook/dinov3-vitl16-pretrain-lvd1689m#camenduru/dinov3-vitl16-pretrain-lvd1689m#" \
            -e "s#briaai/RMBG-2.0#ZhengPeng7/BiRefNet#" $snap/$f > ~/trellis2/model/$f; done

Attention: TRELLIS.2's sparse attention supports only flash_attn/xformers (no SDPA fallback), so
the NGC image's prebuilt flash-attn 2.7.4 for sm_121 is load-bearing. Licences on the code path:
TRELLIS.2, o-voxel, CuMesh, FlexGEMM are MIT; nvdiffrast/nvdiffrec (non-commercial) are installed
by the image for TRELLIS's own renderer but this script never calls them: UV rasterisation is the
numpy `raster_uv` below and mesh post-processing is CuMesh only (`postprocess_geometry`).

TRELLIS.2 is single-image. Stages, each re-runnable on its own:

  shape    one image -> generated mesh (+ its own front-view PBR voxels). Writes raw.pt (full-res
           mesh in TRELLIS's internal z-up frame), body_gen.glb (quick preview, decimated, 2K
           texture) and uvmesh.pt: the decimated, UV-unwrapped mesh that every later texture pass
           is baked onto, so both teams share one geometry and one UV layout.
  texture  uvmesh + N reference views -> one PBR voxel set per view (tex_<view>.pt), all on the
           same voxel coordinates because the shape is encoded once. The texturing flow model
           infers the view direction from the image itself, so the mirrored back view paints the
           back of the mesh. --bake-each also bakes every view alone (view_<name>.glb) for checks.
  project  planar-project a flat reference crop onto a GLB's facing side (used for the shield:
           TRELLIS's emblem is blurry, the crop is crisp) and tint its far side neutral.
  merge    bake every pass onto the shared UV layout and blend them per texel by the surface
           normal (weight max(0, n.d_view)^power; --front-axis says which internal axis the
           character faces) -> final GLB with base colour, metallic and roughness maps.

Example (blue team, then red on the same geometry):

    trellis_body.py shape   --image prep/blue_apose_front_hr.png --out work/shape --faces 40000
    trellis_body.py texture --mesh work/shape/uvmesh.pt --gen-slat work/shape/shape_slat.pt --raw work/shape/raw.pt \
        --out work/tex_blue --view front=prep/blue_apose_front_hr.png --view back=prep/blue_apose_back_hr.png
    trellis_body.py merge   --mesh work/shape/uvmesh.pt --tex work/tex_blue --raw work/shape/raw.pt \
        --out models/man_at_arms_blue.glb --view front=0 --view back=180 --front-axis=-y
"""
import argparse
import json
import os
import sys
import time

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("ATTN_BACKEND", "flash_attn")
os.environ.setdefault("SPARSE_CONV_BACKEND", "flex_gemm")

import numpy as np
import torch
import trimesh
from PIL import Image

MODEL = os.environ.get("TRELLIS2_MODEL", "/trellis2/model")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_rgba(path):
    im = Image.open(path)
    if im.mode != "RGBA":
        sys.exit(f"{path}: expected an RGBA cut-out from prep_views.py, got {im.mode}")
    return im


def glb_to_internal(mesh):
    """Undo o_voxel's export swap: GLB (y-up) -> TRELLIS internal (z-up) frame."""
    v = np.asarray(mesh.vertices, dtype=np.float64).copy()
    v[:, 1], v[:, 2] = -v[:, 2].copy(), v[:, 1].copy()
    return v


def internal_to_glb(v):
    v = np.asarray(v, dtype=np.float64).copy()
    v[:, 1], v[:, 2] = v[:, 2].copy(), -v[:, 1].copy()
    return v


def postprocess_geometry(vertices, faces, target_faces, resolution):
    """The geometry half of o_voxel.postprocess.to_glb (remesh branch), CuMesh (MIT) only: fill
    holes, narrow-band dual-contouring remesh, simplify to ~target_faces, UV-unwrap. Returns
    numpy (verts, faces, uv, normals) in TRELLIS's internal z-up frame. Done here instead of
    calling to_glb because to_glb also bakes with nvdiffrast, whose licence is non-commercial."""
    import cumesh
    v, f = vertices.float().cuda(), faces.int().cuda()
    m = cumesh.CuMesh()
    m.init(v, f)
    m.fill_holes(max_hole_perimeter=3e-2)
    v, f = m.read()
    bvh = cumesh.cuBVH(v, f)
    aabb = torch.tensor([[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]], device="cuda")
    m.init(*cumesh.remeshing.remesh_narrow_band_dc(
        v, f, center=aabb.mean(dim=0), scale=(resolution + 3 * 1) / resolution * 1.0,
        resolution=resolution, band=1, project_back=0, verbose=False, bvh=bvh))
    log(f"   remeshed: {m.num_vertices} verts {m.num_faces} faces")
    m.simplify(target_faces, verbose=False)
    log(f"   simplified: {m.num_vertices} verts {m.num_faces} faces")
    ov, of, ouv, vmaps = m.uv_unwrap(
        compute_charts_kwargs={"threshold_cone_half_angle_rad": np.radians(90.0), "refine_iterations": 0,
                               "global_iterations": 1, "smooth_strength": 1},
        return_vmaps=True, verbose=False)
    m.compute_vertex_normals()
    on = m.read_vertex_normals()[vmaps.to(m.read_vertex_normals().device)]
    return (ov.cpu().numpy().astype(np.float64), of.cpu().numpy().astype(np.int64),
            ouv.cpu().numpy().astype(np.float64), on.cpu().numpy().astype(np.float64))


# ----------------------------------------------------------------------------------------------
@torch.no_grad()
def cmd_shape(a):
    from trellis2.pipelines import Trellis2ImageTo3DPipeline
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    pipe = Trellis2ImageTo3DPipeline.from_pretrained(MODEL)
    pipe.cuda()
    log(f"pipeline loaded in {time.time()-t0:.0f}s")
    image = load_rgba(a.image)
    ts = time.time()
    meshes, (shape_slat, tex_slat, res) = pipe.run(
        image, seed=a.seed, pipeline_type=a.pipeline, return_latent=True, max_num_tokens=a.max_tokens,
        sparse_structure_sampler_params={"steps": a.ss_steps, "guidance_strength": a.ss_guidance},
        shape_slat_sampler_params={"steps": a.slat_steps, "guidance_strength": a.slat_guidance})
    mesh = meshes[0]
    log(f"generated in {time.time()-ts:.1f}s at resolution {res}: {mesh.vertices.shape[0]} verts, "
        f"{mesh.faces.shape[0]} faces, {mesh.coords.shape[0]} attr voxels; "
        f"peak {torch.cuda.max_memory_allocated()/2**30:.1f}GiB")
    torch.save({"vertices": mesh.vertices.cpu(), "faces": mesh.faces.cpu(), "coords": mesh.coords.cpu(),
                "attrs": mesh.attrs.cpu(), "voxel_size": mesh.voxel_size, "layout": mesh.layout,
                "voxel_shape": tuple(mesh.voxel_shape), "resolution": res},
               os.path.join(a.out, "raw.pt"))
    torch.save({"feats": shape_slat.feats.cpu(), "coords": shape_slat.coords.cpu(), "resolution": res},
               os.path.join(a.out, "shape_slat.pt"))     # for `texture --gen-slat`
    del pipe
    torch.cuda.empty_cache()

    ts = time.time()
    verts, faces, uv, normals = postprocess_geometry(mesh.vertices, mesh.faces, a.faces, res)
    log(f"geometry {time.time()-ts:.1f}s: {len(verts)} verts {len(faces)} faces (UV-unwrapped)")
    uv_glb = uv.copy()
    uv_glb[:, 1] = 1 - uv_glb[:, 1]                    # glTF layout, as to_glb exports it
    torch.save({"vertices": torch.from_numpy(verts).float(), "faces": torch.from_numpy(faces).int(),
                "uv": torch.from_numpy(uv_glb).float(), "resolution": res},
               os.path.join(a.out, "uvmesh.pt"))
    # quick preview GLB with the generation's own (front-view) texture
    uvm = MeshLike(verts, faces, uv_glb)
    coords4 = torch.cat([torch.zeros_like(mesh.coords[:, :1]), mesh.coords], 1)
    bake_glb(uvm, os.path.join(a.out, "raw.pt"), mesh.attrs.float(), coords4, res, a.texture,
             os.path.join(a.out, "body_gen.glb"))
    glb = uvm
    with open(os.path.join(a.out, "shape.json"), "w") as fh:
        json.dump({"image": a.image, "seed": a.seed, "pipeline": a.pipeline, "resolution": res,
                   "raw_faces": int(mesh.faces.shape[0]), "faces": int(len(glb.faces)),
                   "verts": int(len(glb.vertices)), "seconds": round(time.time() - t0, 1)}, fh, indent=1)
    log("wrote uvmesh.pt (internal frame + glTF-layout UVs), shape_slat.pt, raw.pt, body_gen.glb")


# ----------------------------------------------------------------------------------------------
class MeshLike:
    """What Trellis2TexturingPipeline.postprocess_mesh reads from a mesh (vertices, faces,
    vertex_normals, visual.uv) as plain writable numpy arrays: trimesh 5 hands out read-only
    vertex arrays, and postprocess_mesh swaps axes in place."""
    class _Visual:
        def __init__(self, uv):
            self.uv = uv

    def __init__(self, vertices, faces, uv):
        self.vertices = np.ascontiguousarray(vertices, dtype=np.float64)
        self.faces = np.ascontiguousarray(faces, dtype=np.int64)
        tm = trimesh.Trimesh(vertices=self.vertices, faces=self.faces, process=False)
        self.vertex_normals = np.array(tm.vertex_normals, dtype=np.float64)
        self.face_normals = np.array(tm.face_normals, dtype=np.float64)
        self.triangles_center = np.array(tm.triangles_center, dtype=np.float64)
        self.visual = MeshLike._Visual(np.ascontiguousarray(uv, dtype=np.float64))

    def copy(self):
        return MeshLike(self.vertices.copy(), self.faces.copy(), self.visual.uv.copy())


def uvmesh_trimesh(path):
    d = torch.load(path, weights_only=False)
    m = MeshLike(d["vertices"].numpy(), d["faces"].numpy(), d["uv"].numpy())
    return m, d


def load_tex_pipeline():
    from trellis2.pipelines import Trellis2TexturingPipeline
    t0 = time.time()
    pipe = Trellis2TexturingPipeline.from_pretrained(MODEL, config_file="texturing_pipeline.json")
    pipe.cuda()
    log(f"texturing pipeline loaded in {time.time()-t0:.0f}s")
    return pipe


@torch.no_grad()
def cmd_texture(a):
    os.makedirs(a.out, exist_ok=True)
    mesh, d = uvmesh_trimesh(a.mesh)
    res = a.res or d["resolution"]
    if a.gen_slat:
        return texture_gen_path(a, mesh, res)
    pipe = load_tex_pipeline()
    ts = time.time()
    enc_mesh = mesh
    if a.encode_mesh:        # encode the full-resolution generated mesh (raw.pt) instead of the
        r = torch.load(a.encode_mesh, weights_only=False)   # decimated one: the texture model sees finer geometry
        enc_mesh = MeshLike(r["vertices"].numpy(), r["faces"].numpy(), np.zeros((len(r["vertices"]), 2)))
        log(f"encoding {a.encode_mesh}: {len(enc_mesh.faces)} faces")
    shape_slat = pipe.encode_shape_slat(enc_mesh, res)
    log(f"shape encoded at {res} in {time.time()-ts:.1f}s: {shape_slat.coords.shape[0]} latent tokens")
    for spec in a.view:
        name, path = spec.split("=", 1)
        # same conditioning prep as the generation pipeline: crop to the alpha bbox and multiply
        # RGB by alpha (black background); without it the cut-out's hidden background colour
        # leaks into the DINOv3 features and the texture comes out dark and muddy
        image = pipe.preprocess_image(load_rgba(path))
        torch.manual_seed(a.seed)
        ts = time.time()
        cond = pipe.get_cond([image], 512 if res == 512 else 1024)
        model = pipe.models["tex_slat_flow_model_512" if res == 512 else "tex_slat_flow_model_1024"]
        tex_slat = pipe.sample_tex_slat(cond, model, shape_slat, {"steps": a.steps, "guidance_strength": a.guidance})
        vox = pipe.decode_tex_slat(tex_slat)
        torch.save({"feats": vox.feats.detach().cpu(), "coords": vox.coords.cpu(), "resolution": res,
                    "spatial_shape": tuple(vox.spatial_shape), "image": path},
                   os.path.join(a.out, f"tex_{name}.pt"))
        log(f"view {name}: {vox.coords.shape[0]} voxels in {time.time()-ts:.1f}s "
            f"peak {torch.cuda.max_memory_allocated()/2**30:.1f}GiB")
        if a.bake_each:
            out = pipe.postprocess_mesh(mesh.copy(), vox, res, a.bake_texture)
            out.export(os.path.join(a.out, f"view_{name}.glb"))
            log(f"   baked view_{name}.glb")
        del tex_slat, vox
        torch.cuda.empty_cache()


def texture_gen_path(a, mesh, res):
    """Texture passes through the generation pipeline's own path: the GENERATED shape slat from
    `shape` conditions the texture flow model and the texture voxels are decoded with the shape
    decoder's subdivision guide, exactly as `Trellis2ImageTo3DPipeline.run` does, only with a
    different conditioning image per pass. The texturing pipeline (encoded slat, unguided decode)
    gave markedly darker, muddier textures on this body; this path matches the generation's look.
    Every pass lands on the same voxel coordinates (fixed by the shape slat), as merge needs."""
    from trellis2.modules.sparse import SparseTensor
    from trellis2.pipelines import Trellis2ImageTo3DPipeline
    t0 = time.time()
    pipe = Trellis2ImageTo3DPipeline.from_pretrained(MODEL)
    pipe.cuda()
    log(f"generation pipeline loaded in {time.time()-t0:.0f}s")
    g = torch.load(a.gen_slat, weights_only=False)
    res = g["resolution"]
    slat = SparseTensor(feats=g["feats"].cuda(), coords=g["coords"].cuda())
    ts = time.time()
    _, subs = pipe.decode_shape_slat(slat, res)
    log(f"shape slat decoded at {res} in {time.time()-ts:.1f}s: {slat.coords.shape[0]} tokens, {len(subs)} guide levels")
    model = pipe.models["tex_slat_flow_model_512" if res == 512 else "tex_slat_flow_model_1024"]
    for spec in a.view:
        name, path = spec.split("=", 1)
        image = pipe.preprocess_image(load_rgba(path))
        torch.manual_seed(a.seed)
        ts = time.time()
        cond = pipe.get_cond([image], 512 if res == 512 else 1024)
        tex_slat = pipe.sample_tex_slat(cond, model, slat, {"steps": a.steps, "guidance_strength": a.guidance})
        vox = pipe.decode_tex_slat(tex_slat, subs)[0]
        torch.save({"feats": vox.feats.detach().cpu(), "coords": vox.coords.cpu(), "resolution": res,
                    "spatial_shape": tuple(vox.spatial_shape), "image": path},
                   os.path.join(a.out, f"tex_{name}.pt"))
        log(f"view {name}: {vox.coords.shape[0]} voxels in {time.time()-ts:.1f}s "
            f"peak {torch.cuda.max_memory_allocated()/2**30:.1f}GiB")
        if a.bake_each:
            if not a.raw:
                sys.exit("--bake-each needs --raw raw.pt")
            bake_glb(mesh, a.raw, vox.feats.float(), vox.coords, res, a.bake_texture,
                     os.path.join(a.out, f"view_{name}.glb"))
        del tex_slat, vox
        torch.cuda.empty_cache()


def raster_uv(uv, faces, T):
    """Rasterise UV triangles into a T x T texel grid (numpy, no nvdiffrast: that library's
    licence is non-commercial). uv is (N, 2) with v already flipped so that row 0 is the TOP of
    the texture image (glTF convention); texel (r, c) is sampled at its centre. Returns the face
    index per texel (-1 where empty) and the barycentric weights (T, T, 3)."""
    fid = np.full((T, T), -1, dtype=np.int64)
    bary = np.zeros((T, T, 3), dtype=np.float32)
    P = uv * T                                   # pixel space, x = u*T, y = v'*T
    tri = P[faces]                               # (F, 3, 2)
    lo = np.floor(tri.min(axis=1)).astype(int).clip(0, T - 1)
    hi = np.ceil(tri.max(axis=1)).astype(int).clip(0, T - 1)
    for f in range(len(faces)):
        (x0, y0), (x1, y1) = lo[f], hi[f]
        if x1 < x0 or y1 < y0:
            continue
        a, b, c = tri[f]
        det = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
        if abs(det) < 1e-12:
            continue
        xs = np.arange(x0, x1 + 1) + 0.5
        ys = np.arange(y0, y1 + 1) + 0.5
        X, Y = np.meshgrid(xs, ys)
        w1 = ((X - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (Y - a[1])) / det
        w2 = ((b[0] - a[0]) * (Y - a[1]) - (X - a[0]) * (b[1] - a[1])) / det
        w0 = 1 - w1 - w2
        inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
        if not inside.any():
            continue
        sub = fid[y0:y1 + 1, x0:x1 + 1]
        write = inside & (sub < 0)
        sub[write] = f
        bsub = bary[y0:y1 + 1, x0:x1 + 1]
        bsub[write] = np.stack([w0[write], w1[write], w2[write]], -1)
    return fid, bary


def bake_setup(mesh, raw_path, texture_size):
    """Everything about the UV layout that every bake shares, the way o_voxel.postprocess.to_glb
    does it (but with the numpy rasteriser): rasterise the UV triangles, get each texel's
    position on the decimated mesh, project it onto the full-resolution generated mesh (CuMesh
    BVH) so the sparse volume is sampled on the true surface (sampling from the low-poly surface
    gives black speckles), plus the texel's surface normal (interpolated vertex normal of the UV
    mesh, well defined on both sides of thin cloth)."""
    import cumesh
    raw = torch.load(raw_path, weights_only=False)
    rv, rf = raw["vertices"].float().cuda(), raw["faces"].int().cuda()
    T = texture_size
    uv = mesh.visual.uv.copy()
    uv[:, 1] = 1 - uv[:, 1]
    t0 = time.time()
    fid, bary = raster_uv(uv, mesh.faces, T)
    mask_np = fid >= 0
    f = mesh.faces[fid[mask_np]]                       # (M, 3) vertex ids
    w = bary[mask_np][..., None]                       # (M, 3, 1)
    pos = (mesh.vertices[f] * w).sum(1).astype(np.float32)
    nrm = (mesh.vertex_normals[f] * w).sum(1).astype(np.float32)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True) + 1e-9
    log(f"   uv raster {T}px: {mask_np.sum()} texels in {time.time()-t0:.1f}s")
    pos = torch.from_numpy(pos).cuda()
    bvh = cumesh.cuBVH(rv, rf)
    _, face_id, uvw = bvh.unsigned_distance(pos, return_uvw=True)
    tri = rv[rf[face_id.long()].long()]
    p = (tri * uvw.unsqueeze(-1)).sum(1)
    return {"T": T, "mask": torch.from_numpy(mask_np).cuda(), "p": p, "nrm": torch.from_numpy(nrm).cuda()}


def bake_sample(setup, feats, coords4, res):
    """Sample one voxel attribute set at the prepared texel positions -> (T, T, C) tensor."""
    from flex_gemm.ops.grid_sample import grid_sample_3d
    T, mask = setup["T"], setup["mask"]
    C = feats.shape[1]
    attrs = torch.zeros(T, T, C, device="cuda")
    attrs[mask] = grid_sample_3d(feats.float().cuda(), coords4.int().cuda(),
                                 shape=torch.Size([1, C, res, res, res]),
                                 grid=((setup["p"] + 0.5) * res).reshape(1, -1, 3), mode="trilinear")
    return attrs


def boost_colour(rgb, saturation=1.0, value=1.0, min_sat=0.12):
    """Push the saturation (and brightness) of coloured pixels only: HSV S *= saturation and
    V *= value where S > min_sat, with a soft ramp, so team cloth and emblems read at 72 px while
    neutral steel, leather and skin are left alone. rgb: float array in 0..1."""
    if saturation == 1.0 and value == 1.0:
        return rgb
    import cv2
    hsv = cv2.cvtColor(np.clip(rgb, 0, 1).astype(np.float32), cv2.COLOR_RGB2HSV)
    sat = hsv[..., 1]
    t = np.clip((sat - min_sat) / max(1e-6, 2 * min_sat), 0, 1)
    hsv[..., 1] = np.clip(sat * (1 + (saturation - 1) * t), 0, 1)
    hsv[..., 2] = np.clip(hsv[..., 2] * (1 + (value - 1) * t), 0, 1)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)


def write_glb(mesh, attrs, mask, out_path, saturation=1.0, value=1.0):
    """Attribute image (base colour, metallic, roughness, alpha) -> PBR GLB on the UV mesh."""
    import cv2
    m = mask.cpu().numpy()
    a8 = lambda x: np.clip(x.cpu().numpy() * 255, 0, 255).astype(np.uint8)
    base, metal, rough, alpha = a8(attrs[..., 0:3]), a8(attrs[..., 3:4]), a8(attrs[..., 4:5]), a8(attrs[..., 5:6])
    if saturation != 1.0 or value != 1.0:
        base = (boost_colour(base.astype(np.float32) / 255, saturation, value) * 255).round().astype(np.uint8)
    inv = (~m).astype(np.uint8)
    base = cv2.inpaint(base, inv, 3, cv2.INPAINT_TELEA)
    metal = cv2.inpaint(metal, inv, 1, cv2.INPAINT_TELEA)[..., None]
    rough = cv2.inpaint(rough, inv, 1, cv2.INPAINT_TELEA)[..., None]
    alpha = cv2.inpaint(alpha, inv, 1, cv2.INPAINT_TELEA)[..., None]
    material = trimesh.visual.material.PBRMaterial(
        baseColorTexture=Image.fromarray(np.concatenate([base, alpha], -1)),
        baseColorFactor=np.array([255, 255, 255, 255], dtype=np.uint8),
        metallicRoughnessTexture=Image.fromarray(np.concatenate([np.zeros_like(metal), rough, metal], -1)),
        metallicFactor=1.0, roughnessFactor=1.0, alphaMode="OPAQUE", doubleSided=True)
    # smooth vertex normals must be exported explicitly: without a NORMAL attribute Blender's
    # glTF importer shades every face flat and the armour turns into a milky scatter of facets
    tm = trimesh.Trimesh(vertices=internal_to_glb(mesh.vertices), faces=mesh.faces, process=False,
                         vertex_normals=internal_to_glb(mesh.vertex_normals),
                         visual=trimesh.visual.TextureVisuals(uv=mesh.visual.uv.copy(), material=material))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tm.export(out_path)
    log(f"   baked {os.path.basename(out_path)}: {len(mesh.faces)} faces, {attrs.shape[0]}px, "
        f"metallic mean {metal.mean()/255:.2f} roughness mean {rough.mean()/255:.2f}, {os.path.getsize(out_path)/1e6:.1f}MB")


def bake_glb(mesh, raw_path, feats, coords4, res, texture_size, out_path):
    setup = bake_setup(mesh, raw_path, texture_size)
    write_glb(mesh, bake_sample(setup, feats, coords4, res), setup["mask"], out_path)


@torch.no_grad()
def cmd_bake(a):
    mesh, d = uvmesh_trimesh(a.mesh)
    v = torch.load(a.voxels, weights_only=False)
    if "attrs" in v:            # raw.pt from `shape`: coords without the batch column
        feats, coords = v["attrs"].float(), torch.cat([torch.zeros_like(v["coords"][:, :1]), v["coords"]], 1)
    else:
        feats, coords = v["feats"].float(), v["coords"]
    res = v.get("resolution") or d["resolution"]
    bake_glb(mesh, a.raw, feats, coords, res, a.texture, a.out)


@torch.no_grad()
def cmd_merge(a):
    """Blend the per-view passes in TEXTURE space: each pass is baked onto the shared UV layout,
    then per texel the passes are weighted by max(0, n.d_view)^power with n the texel's surface
    normal. (Blending per voxel does not work: the tabard is a thin shell, so trilinear sampling
    mixes outer- and inner-side voxels whose nearest-face normals point opposite ways and the two
    passes mottle.)"""
    mesh, d = uvmesh_trimesh(a.mesh)
    fa = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+y": (0, 1, 0), "-y": (0, -1, 0)}[a.front_axis]
    views = []
    for spec in a.view:
        name, yaw = spec.split("=")
        t = np.radians(float(yaw))
        dv = np.array([fa[0] * np.cos(t) - fa[1] * np.sin(t), fa[0] * np.sin(t) + fa[1] * np.cos(t), 0.0])
        views.append((name, dv))
    sets = [torch.load(os.path.join(a.tex, f"tex_{n}.pt"), weights_only=False) for n, _ in views]
    res = sets[0]["resolution"]
    setup = bake_setup(mesh, a.raw, a.texture)
    nrm = setup["nrm"]
    W, A = [], []
    for (name, dv), s in zip(views, sets):
        w = torch.clamp(nrm @ torch.tensor(dv, dtype=torch.float32, device="cuda"), min=0) ** a.power + a.floor
        W.append(w)
        A.append(bake_sample(setup, s["feats"], s["coords"], res)[setup["mask"]])
        log(f"view {name}: dir {np.round(dv, 2).tolist()}")
    W = torch.stack(W, 1)
    W = W / W.sum(1, keepdim=True)
    dom = torch.argmax(W, dim=1)
    for i, (name, _) in enumerate(views):
        log(f"   {name} dominates {float((dom == i).float().mean().item()) * 100:.0f}% of texels")
    blended = sum(W[:, i:i + 1] * A[i] for i in range(len(A)))
    if a.metallic_from or a.roughness_from:
        by = {n: i for i, (n, _) in enumerate(views)}
        if a.metallic_from:
            blended[:, 3:4] = A[by[a.metallic_from]][:, 3:4]
        if a.roughness_from:
            blended[:, 4:5] = A[by[a.roughness_from]][:, 4:5]
    attrs = torch.zeros(a.texture, a.texture, blended.shape[1], device="cuda")
    attrs[setup["mask"]] = blended
    write_glb(mesh, attrs, setup["mask"], a.out, a.saturation, a.value)


# ----------------------------------------------------------------------------------------------
@torch.no_grad()
def cmd_project(a):
    """Planar-project a flat reference image onto the face of a textured GLB (the shield): the
    generated base colour is replaced by the crop on texels whose normal faces --axis, blended
    by facing angle, so the emblem is as crisp as the reference instead of TRELLIS's blurry
    version. Texels facing the other way are tinted to a neutral wood/leather so the back of the
    shield is never the other team's colour. Metallic/roughness maps are kept."""
    from scipy.ndimage import map_coordinates
    scene = trimesh.load(a.glb, force="scene")
    geom = next(iter(scene.geometry.values()))
    V = np.asarray(geom.vertices, dtype=np.float32)
    F = np.asarray(geom.faces, dtype=np.int32)
    UV = np.asarray(geom.visual.uv, dtype=np.float32)
    mat = geom.visual.material
    base = np.asarray(mat.baseColorTexture.convert("RGBA")).astype(np.float32) / 255
    T = base.shape[0]
    tm = trimesh.Trimesh(vertices=V, faces=F, process=False)
    N = np.asarray(tm.vertex_normals, dtype=np.float32)
    d = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+y": (0, 1, 0), "-y": (0, -1, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}[a.axis]
    d = np.array(d, dtype=np.float32)
    # texel -> position/normal (UV-space rasterisation, image row 0 at v=0 of the glTF layout)
    uvf = UV.copy()
    uvf[:, 1] = 1 - uvf[:, 1]
    fid, bary = raster_uv(uvf, F.astype(np.int64), T)
    mask = fid >= 0
    pos = np.zeros((T, T, 3), np.float32)
    nrm = np.zeros((T, T, 3), np.float32)
    fm = F[fid[mask]]
    pos[mask] = (V[fm] * bary[mask][..., None]).sum(1)
    nrm[mask] = (N[fm] * bary[mask][..., None]).sum(1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True) + 1e-9
    facing = nrm @ d
    # image plane axes: right = d x up, with "up" the world axis most orthogonal to d
    up = np.array([0, 1, 0], np.float32) if abs(d[1]) < 0.9 else np.array([0, 0, 1], np.float32)
    right = np.cross(up, d); right /= np.linalg.norm(right)
    up = np.cross(d, right)
    front = mask & (facing > 0.25)
    px, py = pos[front] @ right, pos[front] @ up
    im = load_rgba(a.image)
    arr = np.asarray(im).astype(np.float32) / 255
    al = arr[..., 3]
    ys, xs = np.where(al > 0.5)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    # mesh silhouette extent (front-facing texels) -> crop's alpha bbox
    fx = (px - px.min()) / (px.max() - px.min() + 1e-9) * (x1 - x0) + x0
    fy = (py.max() - py) / (py.max() - py.min() + 1e-9) * (y1 - y0) + y0
    samp = np.stack([map_coordinates(arr[..., c], [fy, fx], order=1, mode="nearest") for c in range(4)], -1)
    t = np.clip((facing[front] - 0.25) / 0.35, 0, 1)
    w = (t * t * (3 - 2 * t)) * (samp[..., 3] > 0.5)
    out = base.copy()
    out[front, :3] = (w[:, None] * samp[:, :3] + (1 - w[:, None]) * base[front, :3])
    out[..., :3] = boost_colour(out[..., :3], a.saturation, a.value)
    back = mask & (facing < -0.3)
    if a.back_tint:
        tint = np.array([float(x) for x in a.back_tint.split(",")], np.float32)
        grey = base[back, :3].mean(axis=-1, keepdims=True)
        out[back, :3] = np.clip(grey * tint / tint.mean(), 0, 1)
    log(f"projected {a.image} on {front.sum()} texels (facing {a.axis}); back-tinted {back.sum()}")
    new_mat = trimesh.visual.material.PBRMaterial(
        baseColorTexture=Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)),
        baseColorFactor=np.array([255, 255, 255, 255], dtype=np.uint8),
        metallicRoughnessTexture=mat.metallicRoughnessTexture, metallicFactor=1.0, roughnessFactor=1.0,
        alphaMode="OPAQUE", doubleSided=True)
    res = trimesh.Trimesh(vertices=V, faces=F, process=False, vertex_normals=N,
                          visual=trimesh.visual.TextureVisuals(uv=UV, material=new_mat))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    res.export(a.out)
    log(f"-> {a.out}: {len(F)} faces, {os.path.getsize(a.out)/1e6:.1f}MB")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("shape")
    s.add_argument("--image", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--pipeline", default="1024_cascade", choices=("512", "1024", "1024_cascade", "1536_cascade"))
    s.add_argument("--max-tokens", type=int, default=49152)
    s.add_argument("--ss-steps", type=int, default=12)
    s.add_argument("--ss-guidance", type=float, default=7.5)
    s.add_argument("--slat-steps", type=int, default=12)
    s.add_argument("--slat-guidance", type=float, default=3.0)
    s.add_argument("--faces", type=int, default=40000, help="target face count of the UV'd mesh")
    s.add_argument("--texture", type=int, default=2048)
    t = sub.add_parser("texture")
    t.add_argument("--mesh", required=True, help="uvmesh.pt from `shape`")
    t.add_argument("--out", required=True)
    t.add_argument("--view", action="append", required=True, help="name=image.png")
    t.add_argument("--res", type=int, default=None, help="voxel resolution (default: the shape's)")
    t.add_argument("--seed", type=int, default=42)
    t.add_argument("--steps", type=int, default=12)
    t.add_argument("--guidance", type=float, default=1.0)
    t.add_argument("--bake-each", action="store_true")
    t.add_argument("--bake-texture", type=int, default=1024)
    t.add_argument("--encode-mesh", default=None, help="raw.pt to encode instead of the UV mesh")
    t.add_argument("--gen-slat", default=None, help="shape_slat.pt from `shape`: use the generation path (recommended)")
    t.add_argument("--raw", default=None, help="raw.pt from `shape` (needed by --bake-each with --gen-slat)")
    b = sub.add_parser("bake", help="bake one saved voxel set (raw.pt or tex_<view>.pt) onto the UV mesh")
    b.add_argument("--mesh", required=True)
    b.add_argument("--voxels", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--texture", type=int, default=1024)
    b.add_argument("--raw", required=True)
    m = sub.add_parser("merge")
    m.add_argument("--mesh", required=True)
    m.add_argument("--tex", required=True, help="directory with tex_<view>.pt")
    m.add_argument("--out", required=True)
    m.add_argument("--view", action="append", required=True, help="name=yaw_degrees (0 = front, 180 = back)")
    m.add_argument("--front-axis", default="-y", choices=("+x", "-x", "+y", "-y"),
                   help="internal-frame axis the character's face points along")
    m.add_argument("--power", type=float, default=8.0, help="normal-weight sharpness; soft blends mottle the hallucinated sides")
    m.add_argument("--floor", type=float, default=1e-3)
    m.add_argument("--metallic-from", default=None)
    m.add_argument("--roughness-from", default=None)
    m.add_argument("--texture", type=int, default=2048)
    m.add_argument("--raw", required=True, help="raw.pt from `shape` (texels are projected onto it before sampling)")
    m.add_argument("--saturation", type=float, default=1.0, help="boost for coloured texels (team cloth); steel untouched")
    m.add_argument("--value", type=float, default=1.0, help="brightness boost for coloured texels")
    pj = sub.add_parser("project")
    pj.add_argument("--glb", required=True)
    pj.add_argument("--image", required=True, help="RGBA front-on reference (prep_images.py / prep_views.py)")
    pj.add_argument("--axis", default="+z", help="GLB-frame direction the projected face points")
    pj.add_argument("--back-tint", default="0.42,0.30,0.20", help="r,g,b wood/leather for the far side; '' keeps")
    pj.add_argument("--saturation", type=float, default=1.0)
    pj.add_argument("--value", type=float, default=1.0)
    pj.add_argument("--out", required=True)
    a = ap.parse_args()
    {"shape": cmd_shape, "texture": cmd_texture, "merge": cmd_merge, "project": cmd_project, "bake": cmd_bake}[a.cmd](a)


if __name__ == "__main__":
    main()
