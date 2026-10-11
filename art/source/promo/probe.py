#!/usr/bin/env python3
"""Evaluate JS in a started game (same setup as capture.py) and print the result. Usage: probe.py 'JS'"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_init import INIT
from scenes import COMMON_JS
with sync_playwright() as p:
    b = p.webkit.launch(); ctx = b.new_context(viewport={"width": 540, "height": 960}, device_scale_factor=2)
    ctx.add_init_script(INIT); pg = ctx.new_page()
    pg.goto("file://" + os.path.expanduser("~/ma_promo/WebGame/index.html")); pg.wait_for_timeout(1500)
    pg.click("#startBtn", force=True); pg.evaluate("window.__step(2, 33.33)"); pg.evaluate(COMMON_JS)
    print(pg.evaluate(sys.argv[1])); b.close()
