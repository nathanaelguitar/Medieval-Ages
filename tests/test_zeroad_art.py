"""Regression checks for the selected 0 A.D. sprite sources and bake manifest."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bake_zeroad_art", ROOT / "scripts/bake_zeroad_art.py")
assert spec and spec.loader
bake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bake)


class ZeroADArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = bake.ActorIndex()

    def test_biped_skeleton_has_static_prop_bones(self):
        dae = ROOT / "ios/ZeroADArt/meshes/skeletal/new/m_armor_tunic_short.dae"
        bones, parents = bake.parse_skeleton(dae, with_parents=True)
        for name in ("Biped_helmet", "Biped_weapon_R", "Biped_sheath_01_R",
                     "Biped_leg_R", "Biped_leg_L"):
            self.assertIn(name, bones)
            self.assertEqual(len(bones[name]), 16)
        self.assertIsNotNone(parents["Biped_helmet"])

    def test_fauna_actor_meshes_and_textures_resolve(self):
        expected = {
            "fauna/boar.xml": ("skeletal/animal_boar.dae", "skeletal/animal_boar_01.png"),
            "fauna/sheep1.xml": ("skeletal/sheep.dae", "skeletal/animal_sheep_a.dds"),
        }
        for actor, (mesh, texture) in expected.items():
            with self.subTest(actor=actor):
                parts = list(self.index.expand(actor, props=False))
                self.assertEqual(len(parts), 1)
                self.assertEqual(parts[0][:2], (mesh, texture))
                self.assertTrue((ROOT / "ios/ZeroADArt/meshes" / mesh).is_file())
                self.assertTrue((ROOT / "ios/ZeroADArt/textures/skins" / texture).is_file())

    def test_spearman_props_keep_their_named_attachpoints(self):
        parts = list(self.index.expand("units/athenians/hero_infantry_spearman_pericles.xml"))
        attachpoints = {part[2] for part in parts}
        self.assertTrue({"helmet", "weapon_R", "sheath_01_R", "leg_R", "leg_L"}
                        <= attachpoints)

    def test_sprite_manifests_are_complete_and_webkit_loadable(self):
        """The shipping sprite set (ios/WebGame/sprites/manifest_*.js, written by the art pipeline)
        names only files that exist, and every animal has idle, walk and dead clips in 8 facings.
        The 0 A.D. manifest.js/.json and their sprites are gone from the game."""
        sprite_dir = ROOT / "ios/WebGame/sprites"
        self.assertFalse((sprite_dir / "manifest.js").exists())
        self.assertFalse((sprite_dir / "manifest.json").exists())
        prefix = "window.POCKET_EMPIRES_SPRITES = Object.assign(window.POCKET_EMPIRES_SPRITES || {}, "
        manifest = {}
        for path in sorted(sprite_dir.glob("manifest_*.js")):
            body = path.read_text().split("\n", 1)[1]
            self.assertTrue(body.startswith(prefix), path.name)
            manifest.update(json.loads(body[len(prefix):].rstrip().removesuffix(");")))
        for kind in ("boar", "sheep"):
            for clip in ("idle", "walk", "dead"):
                for d in range(8):
                    group = manifest[f"animal_{kind}_{clip}_d{d}"]
                    self.assertEqual(group["group"], "animation")
                    self.assertGreaterEqual(len(group["files"]), 1 if clip == "dead" else 2)
        for name, entry in manifest.items():
            files = [entry["file"]] if "file" in entry else entry.get("files", [])
            for filename in files:
                with self.subTest(sprite=name, file=filename):
                    self.assertTrue((sprite_dir / filename).is_file())

if __name__ == "__main__":
    unittest.main(verbosity=2)
