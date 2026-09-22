#!/usr/bin/env python3
"""Tests for patch safety and project metadata. Does not pretend to compile UIKit."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import plistlib
import struct
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("prepare_engine",ROOT/"scripts/prepare_engine.py")
assert spec and spec.loader
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class PreparationTests(unittest.TestCase):
    def test_blob_matches_git(self):
        data=b"example\n"
        result=subprocess.run(["git","hash-object","--stdin"],input=data,check=True,capture_output=True)
        self.assertEqual(mod.git_blob(data),result.stdout.decode().strip())
    def test_single_anchor(self):
        self.assertEqual(mod.replace_once("a b","a","c"),"c b")
        for source in ("b","a a"):
            with self.assertRaises(ValueError): mod.replace_once(source,"a","c")
    def test_function_nested_body(self):
        source="int Before(void)\n{\n}\nstatic void Target(int x)\n{\n    if(x)\n    {\n        x++;\n    }\n}\nint After(void)\n{\n}\n"
        result=mod.replace_function(source,"Target","void Target(void)\n{\n    return;\n}")
        self.assertIn("Before",result); self.assertIn("After",result)
        self.assertNotIn("x++",result)
        with self.assertRaises(ValueError): mod.replace_function(source,"Absent","no")
    def test_table_boundary_fixes(self):
        self.assertIn("table_index < drs.table_count",mod.patch("Drs.c","assert(table_index <= drs.table_count);"))
        self.assertIn("file_index < table.num_files",mod.patch("Table.c","assert(file_index <= table.num_files);"))
    def test_comparator_and_count_fixes(self):
        text="    return ma > mb;\n    for(int32_t i = 0; i < SIDES; i++)"
        result=mod.patch("Units.c",text)
        self.assertIn("(ma > mb) - (ma < mb)",result)
        self.assertIn("i < count",result)
    def test_header_normalization(self):
        self.assertEqual(mod.patch("Untouched.c","#include <SDL2/SDL.h>\n"),"#include <SDL.h>\n")
    def test_refuses_unknown_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"upstream"; (source/"src").mkdir(parents=True)
            (source/"src/Video.c").write_text("unexpected")
            with self.assertRaisesRegex(ValueError,"verified"):
                mod.prepare(source,Path(tmp)/"out",ROOT)
            self.assertFalse((Path(tmp)/"out").exists())
    def test_refuses_writing_into_upstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"upstream"; (source/"src").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError,"outside"):
                mod.prepare(source,source/"src/copy",ROOT)
    def test_native_text_has_no_font_dependency(self):
        self.assertNotIn("SDL_ttf",(ROOT/"ios/Text.h").read_text())
        self.assertIn("monospacedSystemFontOfSize",(ROOT/"ios/OEText.m").read_text())
    def test_no_distributed_fonts_or_game_data(self):
        banned={".ttf",".otf",".woff",".woff2",".drs"}
        for path in ROOT.rglob("*"):
            if not any(p.startswith("build") for p in path.parts):
                self.assertNotIn(path.suffix.lower(),banned)
    def test_plists_and_landscape(self):
        info=plistlib.loads((ROOT/"ios/Info.plist.in").read_bytes())
        self.assertTrue(info["UIRequiresFullScreen"])
        self.assertTrue(all("Landscape" in x for x in info["UISupportedInterfaceOrientations"]))
        privacy=plistlib.loads((ROOT/"ios/PrivacyInfo.xcprivacy").read_bytes())
        self.assertFalse(privacy["NSPrivacyTracking"])
    def test_app_icons_match_catalog(self):
        folder=ROOT/"ios/Assets.xcassets/AppIcon.appiconset"
        images=json.loads((folder/"Contents.json").read_text())["images"]
        for entry in images:
            data=(folder/entry["filename"]).read_bytes()
            self.assertEqual(data[:8],b"\x89PNG\r\n\x1a\n")
            w,h=struct.unpack(">II",data[16:24])
            expected=round(float(entry["size"].split("x")[0])*float(entry.get("scale","1x")[:-1]))
            self.assertEqual((w,h),(expected,expected))
if __name__=="__main__": unittest.main(verbosity=2)
