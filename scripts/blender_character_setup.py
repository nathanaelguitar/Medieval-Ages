#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare a bundled 0 A.D. character for animation in Blender.

This runs *inside* Blender, not as a standalone script:

    blender --background --python scripts/blender_character_setup.py -- --character villager

It writes a .blend you can open and animate. Why it is needed at all:

* **Blender 5.2 no longer bundles the COLLADA importer.** The legacy importers moved out of core,
  so `bpy.ops.wm.collada_import` does not exist on a stock install. The route taken here is
  assimp -> glTF -> Blender, which uses Blender's core glTF importer instead.
* **The 0 A.D. materials point at an unresolvable absolute Windows path** (`C:/Users/micha/...`),
  so assimp drops the texture and the character arrives untextured. The image is re-attached here
  from the texture set bundled alongside the meshes.

The character meshes are already rigged and skinned -- a 24-bone biped using 0 A.D.'s standard
`Biped_*` bone names -- so there is nothing to re-rig. Animating that armature and exporting an
animated .glb is what feeds the sprite bake.

Original artwork is CC BY-SA 3.0, (C) Wildfire Games; see ios/ZeroADArt/LICENSE.txt.
"""

import argparse
import os
import subprocess
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ART = os.path.join(ROOT, "ios", "ZeroADArt")
SKINS = os.path.join(ART, "textures", "skins")

# character key -> (mesh under ios/ZeroADArt/meshes, base colour map under textures/skins)
CHARACTERS = {
    "villager": ("skeletal/new/f_dress.dae", "skeletal/hele/dress_female_01.png"),
    "soldier": ("skeletal/new/m_armor_tunic_short.dae", "skeletal/athen/linothorax_lamellar_01_03.png"),
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--character", default="villager", choices=sorted(CHARACTERS))
    ap.add_argument("--out", help="output .blend path (default: <character>.blend in the repo root)")
    ap.add_argument("--keep-cache", action="store_true", help="leave the intermediate .glb in place")
    return ap.parse_args(argv)


def to_gltf(dae, glb):
    """assimp carries the skin and the joint hierarchy across; Blender can read glTF natively."""
    try:
        r = subprocess.run(["assimp", "export", dae, glb],
                           capture_output=True, text=True, check=False)
    except FileNotFoundError:
        sys.exit("assimp not found on PATH -- install it with: brew install assimp")
    if r.returncode != 0 or not os.path.exists(glb):
        sys.exit(f"assimp failed to convert {dae}:\n{r.stderr}")


def wire_texture(image_path):
    """Attach the bundled base colour map to whichever materials came across."""
    img = bpy.data.images.load(image_path)
    wired = []
    for mat in bpy.data.materials:
        if mat.node_tree is None:   # use_nodes is deprecated in 5.2 and removed in 6.0
            continue
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None:
            continue
        tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.location = (-400, 200)
        mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        wired.append(mat.name)
    return img, wired


def main():
    args = parse_args()
    mesh_rel, skin_rel = CHARACTERS[args.character]
    dae = os.path.join(ART, "meshes", mesh_rel)
    skin = os.path.join(SKINS, skin_rel)
    if not os.path.exists(dae):
        sys.exit(f"missing mesh: {dae}")
    if not os.path.exists(skin):
        sys.exit(f"missing texture: {skin}")

    out = args.out or os.path.join(ROOT, f"{args.character}.blend")
    glb = os.path.join(os.path.dirname(out) or ".", f".{args.character}.glb")

    print(f"== {args.character}")
    to_gltf(dae, glb)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=glb)

    # assimp's conversion leaves a stray primitive behind; it carries no skin and no material, so
    # it would only get in the way while animating.
    for obj in [o for o in bpy.data.objects if o.type == "MESH" and not o.vertex_groups]:
        print(f"   dropping unskinned artifact: {obj.name}")
        bpy.data.objects.remove(obj, do_unlink=True)

    img, wired = wire_texture(skin)
    print(f"   texture: {os.path.basename(skin)} -> {wired or 'NO MATERIALS FOUND'}")

    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    skinned = [o for o in bpy.data.objects if o.type == "MESH" and o.vertex_groups]
    for a in arms:
        names = [b.name for b in a.data.bones]
        print(f"   armature '{a.name}': {len(names)} bones, "
              f"Biped_ naming={any(n.startswith('Biped') for n in names)}")
    for m in skinned:
        print(f"   mesh '{m.name}': {len(m.data.vertices)} verts, "
              f"{len(m.vertex_groups)} vertex groups, skinned="
              f"{any(md.type == 'ARMATURE' for md in m.modifiers)}")
    if not arms or not skinned:
        sys.exit("import did not produce a skinned armature+mesh pair; refusing to write a bad .blend")

    bpy.ops.wm.save_as_mainfile(filepath=out)
    print(f"   wrote {os.path.relpath(out, ROOT)}")
    if not args.keep_cache and os.path.exists(glb):
        os.remove(glb)
    print(f"\nOpen it with:  blender {os.path.relpath(out, ROOT)}")


main()
