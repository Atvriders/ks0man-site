#!/usr/bin/env python3
"""Upload the maars theme and the maars-core plugin to a live WordPress.

WordPress has no REST endpoint for installing a theme or a plugin from a zip, so
this signs in to wp-admin in a headless browser and uses the upload forms, the
way a person would. It handles the screen WordPress shows when the theme or
plugin is already installed ("Replace current with uploaded"), it paces itself
because the production host throttles bursts of requests, and it builds the
zips from the repository so what is deployed is exactly what is committed.

It lives in the repository because the copy in /tmp did not survive: a tmp
cleaner took it, and the packages it had built, between one session and the
next.

The admin password never touches the disk. It comes from the environment:

    WPU=<user> WPP='<password>' python3 tools/deploy_wp.py --site https://ks0man.org
    … --only theme      or      … --only plugin      or      … --check-login

Needs: playwright and its Chromium.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = os.path.expanduser("~/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/143.0.0.0 Safari/537.36")


def build_zip(src_parent: str, folder: str, out: str) -> int:
    count = 0
    base = os.path.join(src_parent, folder)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in sorted(dirs) if d not in ("__pycache__", ".git")]
            for name in sorted(files):
                if name == ".DS_Store" or name.endswith(".pyc"):
                    continue
                full = os.path.join(root, name)
                zf.write(full, os.path.relpath(full, src_parent))
                count += 1
    return count


def challenged(page) -> bool:
    try:
        return "window.location.reload" in page.content()[:2000]
    except Exception:  # noqa: BLE001
        return False


def goto(page, url: str, tries: int = 3) -> bool:
    for attempt in range(tries):
        page.goto(url, wait_until="load", timeout=120000)
        if not challenged(page):
            return True
        wait = 30 * (attempt + 1)
        print(f"    challenged by the host, backing off {wait}s")
        time.sleep(wait)
    return False


def upload(page, site: str, kind: str, zip_path: str, pace: float) -> bool:
    url = f"{site}/wp-admin/{kind}-install.php?tab=upload"
    field = "#pluginzip" if kind == "plugin" else "#themezip"
    submit = "#install-plugin-submit" if kind == "plugin" else "#install-theme-submit"
    print(f"  {kind}: opening the upload form")
    if not goto(page, url):
        return False
    time.sleep(pace)
    if not page.locator(submit).is_visible():
        # theme-install.php keeps its form collapsed behind "Upload Theme".
        toggle = page.locator(".upload-view-toggle, button:has-text('Upload Theme')")
        if toggle.count():
            toggle.first.click()
            time.sleep(1.5)
    page.set_input_files(field, zip_path)
    time.sleep(pace)
    page.click(submit)
    page.wait_for_load_state("load", timeout=300000)
    time.sleep(pace)
    body = page.inner_text("body")
    if "already installed" in body.lower() or "destination folder already exists" in body.lower():
        print(f"  {kind}: already installed, replacing")
        button = page.locator("a.update-from-upload-overwrite, a:has-text('Replace current with uploaded')")
        if not button.count():
            print(f"  {kind}: no replace button on the page")
            return False
        time.sleep(pace)
        button.first.click()
        page.wait_for_load_state("load", timeout=300000)
        time.sleep(pace)
        body = page.inner_text("body")
    ok = any(k in body.lower() for k in ("successfully", "replaced with", "installed"))
    for line in body.splitlines():
        line = line.strip()
        if line and any(k in line.lower() for k in ("success", "replaced", "error", "failed")):
            print("     ", line[:140])
    print(f"  {kind}: {'OK' if ok else 'CHECK THE SCREEN'}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", required=True)
    ap.add_argument("--only", choices=("theme", "plugin"))
    ap.add_argument("--check-login", action="store_true")
    ap.add_argument("--pace", type=float, default=3.0)
    args = ap.parse_args()

    user, password = os.environ.get("WPU"), os.environ.get("WPP")
    if not user or not password:
        print("set WPU and WPP in the environment")
        return 2

    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME,
                                    args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_context(viewport={"width": 1440, "height": 1000},
                                   user_agent=UA).new_page()
        if not goto(page, args.site + "/wp-login.php"):
            print("  the login page stayed challenged")
            return 1
        time.sleep(args.pace)
        if page.locator("#user_login").count():
            page.fill("#user_login", user)
            page.fill("#user_pass", password)
            page.click("#wp-submit")
            page.wait_for_load_state("load", timeout=120000)
        time.sleep(args.pace)
        if "/wp-admin" not in page.url:
            print("  NOT signed in; WordPress said:",
                  " | ".join(l.strip() for l in page.inner_text("body").splitlines() if l.strip())[:200])
            return 1
        print("  signed in")
        if args.check_login:
            return 0

        ok = True
        if args.only in (None, "plugin"):
            zp = os.path.join(tmp, "maars-core.zip")
            n = build_zip(os.path.join(ROOT, "wp", "plugins"), "maars-core", zp)
            print(f"  plugin zip: {n} files")
            ok = upload(page, args.site, "plugin", zp, args.pace) and ok
            time.sleep(args.pace * 2)
        if args.only in (None, "theme"):
            zt = os.path.join(tmp, "maars.zip")
            n = build_zip(os.path.join(ROOT, "wp", "themes"), "maars", zt)
            print(f"  theme zip: {n} files")
            ok = upload(page, args.site, "theme", zt, args.pace) and ok
        browser.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
