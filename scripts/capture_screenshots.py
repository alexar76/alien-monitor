#!/usr/bin/env python3
"""Capture Alien Monitor screenshots using Playwright (Python)."""

import os
import sys
import time
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = ROOT / "docs" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

BACKEND_PORT = 9100
FRONTEND_PORT = 5173
BASE_URL = f"http://localhost:{FRONTEND_PORT}"
WAIT = 6  # seconds to wait for WebGL + WebSocket + bloom to fully render

#: Switching TEST/LIVE/UNI remounts the whole 3D scene — the graph is keyed on the mode so a
#: stale WebGL context is never reused — so the canvas is empty for far longer than a theme
#: change takes. Shot 8 waited one second after clicking LIVE and shipped a 4K frame of pure
#: black into the README, where it sat until somebody looked at the gallery.
MODE_SWITCH_WAIT = 10

#: A fully black 4K PNG compresses to about 30 KB; a real frame of this map is 2–3 MB. The
#: exact threshold does not matter, only that an empty capture can never again be written
#: and forgotten. Cheap enough to need no image library.
MIN_FRAME_BYTES = 250_000


def shoot(page, name: str) -> Path:
    """Screenshot, then refuse to accept an empty frame.

    Every capture here is a WebGL scene that takes seconds to appear. Without this the
    failure mode is silent: the file is written, the script prints success, and the blank
    image is discovered later by a reader of the README.
    """
    path = SCREENSHOTS_DIR / name
    page.screenshot(path=str(path))
    size = path.stat().st_size
    if size < MIN_FRAME_BYTES:
        raise SystemExit(
            f"\n{name} came out empty ({size // 1024} KB) — the scene had not rendered.\n"
            f"Nothing was published; re-run once the map is actually on screen."
        )
    print(f"  -> {name} ({size // 1024} KB)")
    return path


def main():
    from playwright.sync_api import sync_playwright

    print("=" * 60)
    print("  Alien Monitor — Screenshot Capture")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--use-gl=swiftshader',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--enable-webgl',
                '--ignore-gpu-blocklist',
            ],
        )
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            device_scale_factor=2,
        )
        page = context.new_page()

        # ── 1. Full ecosystem overview ────────────────────────────
        print("[1/8] Full ecosystem overview...")
        page.goto(BASE_URL, wait_until='domcontentloaded', timeout=30000)
        time.sleep(WAIT)
        shoot(page, "01-full-ecosystem.png")

        # ── 2. Zoom into center by scrolling ──────────────────────
        print("[2/8] Hub close-up...")
        canvas = page.locator('canvas')
        canvas.first.hover()
        for _ in range(10):
            page.mouse.wheel(0, -120)
            time.sleep(0.08)
        time.sleep(2)
        shoot(page, "02-hub-closeup.png")

        # ── 3. Reload & click node for detail ─────────────────────
        print("[3/8] Node detail panel...")
        page.goto(BASE_URL, wait_until='domcontentloaded', timeout=15000)
        time.sleep(WAIT)
        # Click near center where hub should be
        page.mouse.click(960, 460)
        time.sleep(1.5)
        shoot(page, "03-node-detail.png")

        # ── 4. AI Assistant open ──────────────────────────────────
        print("[4/8] AI Assistant panel...")
        page.keyboard.press('Escape')
        time.sleep(0.5)
        # Look for AI button
        ai_btn = page.locator('button', has_text='AI')
        if ai_btn.count() > 0:
            ai_btn.first.click()
            time.sleep(0.5)
        shoot(page, "04-ai-assistant.png")

        # ── 5. AI answering question ──────────────────────────────
        print("[5/8] AI answering...")
        inp = page.locator('input[placeholder*="Ask"]')
        if inp.count() > 0:
            inp.first.fill("How do payment channels work?")
            time.sleep(0.3)
            page.keyboard.press('Enter')
            time.sleep(2)
        shoot(page, "05-ai-answering.png")

        # ── 6. Transaction flow ───────────────────────────────────
        print("[6/8] Transaction activity...")
        page.keyboard.press('Escape')
        time.sleep(0.3)
        shoot(page, "06-transaction-flow.png")

        # ── 7. Magenta theme ──────────────────────────────────────
        print("[7/8] Magenta theme...")
        mg = page.locator('button', has_text='MG')
        if mg.count() > 0:
            mg.first.click()
            time.sleep(0.8)
        shoot(page, "07-magenta-theme.png")

        # ── 8. Green theme, LIVE mode ─────────────────────────────
        print("[8/8] Green theme, LIVE...")
        gr = page.locator('button', has_text='GR')
        if gr.count() > 0:
            gr.first.click()
            time.sleep(0.3)
        live = page.locator('button', has_text='LIVE')
        if live.count() > 0:
            live.first.click()
            # Not a theme swap: the scene is torn down and rebuilt. See MODE_SWITCH_WAIT.
            time.sleep(MODE_SWITCH_WAIT)
        shoot(page, "08-live-green.png")

        browser.close()

    print(f"\nDone! {len(list(SCREENSHOTS_DIR.glob('*.png')))} screenshots in {SCREENSHOTS_DIR}")


if __name__ == "__main__":
    main()
