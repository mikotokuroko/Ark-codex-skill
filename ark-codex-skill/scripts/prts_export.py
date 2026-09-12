#!/usr/bin/env python3
"""Export base (基建) WebM animations for an Arknights operator from PRTS."""

import argparse
import os
import sys
import urllib.parse

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("playwright is required: run 'pip install playwright' first")

ANIMATIONS = ["Interact", "Move", "Relax", "Sit", "Sleep"]
LOAD_BTN = "\u70b9\u6b64\u8f7d\u5165\u6a21\u578b"
JIANJI = "\u57fa\u5efa"


def find_chrome():
    candidates = [
        os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def select_option(page, select, text):
    select.click()
    option = page.locator(".n-base-select-option", has_text=text).first
    option.wait_for(state="visible", timeout=120000)
    option.click()
    page.wait_for_timeout(1200)


def find_download_button(page):
    locator = page.locator("button.n-button").filter(
        has=page.locator(
            'svg path[d^="M19 9h-4V3H9v6H5l7 7l7-7z"]'
        )
    )
    if locator.count() == 0:
        raise RuntimeError("WebM download button not found")
    return locator.first


def open_operator_page(page, operator):
    url = "https://prts.wiki/w/" + urllib.parse.quote(operator)
    page.goto(url, wait_until="commit", timeout=180000)
    load_btn = page.locator("button", has_text=LOAD_BTN).first
    try:
        load_btn.wait_for(state="visible", timeout=120000)
    except PlaywrightTimeoutError:
        search_url = (
            "https://prts.wiki/index.php?search="
            + urllib.parse.quote(operator)
            + "&fulltext=1"
        )
        page.goto(search_url, wait_until="commit", timeout=180000)
        links = page.locator(".mw-search-result a[href^='/w/']")
        links.first.wait_for(state="visible", timeout=120000)
        href = links.first.get_attribute("href")
        title = urllib.parse.unquote(href.split("/w/", 1)[1])
        page.goto(
            "https://prts.wiki/w/" + urllib.parse.quote(title),
            wait_until="commit",
            timeout=180000,
        )
        load_btn = page.locator("button", has_text=LOAD_BTN).first
        load_btn.wait_for(state="visible", timeout=120000)


def run_export(operator, skin, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with sync_playwright() as p:
        chrome = find_chrome()
        if chrome:
            browser = p.chromium.launch(executable_path=chrome, headless=True)
        else:
            browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1400, "height": 1000},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        try:
            open_operator_page(page, operator)
            load_btn = page.locator("button", has_text=LOAD_BTN).first
            load_btn.scroll_into_view_if_needed()
            load_btn.click()
            page.locator(".n-select").nth(2).wait_for(
                state="visible", timeout=120000
            )

            skin_select = page.locator(".n-select").nth(0)
            select_option(page, skin_select, skin or "\u9ed8\u8ba4")
            model_select = page.locator(".n-select").nth(1)
            select_option(page, model_select, JIANJI)

            skin_label = skin or "\u9ed8\u8ba4"
            anim_select = page.locator(".n-select").nth(2)
            anim_select.click()
            options = page.locator(".n-base-select-option")
            options.first.wait_for(state="visible", timeout=30000)
            available = [name.strip() for name in options.all_text_contents()]
            page.keyboard.press("Escape")
            missing = [name for name in ANIMATIONS if name not in available]
            if missing:
                raise RuntimeError(f"Missing required animations: {missing}; available: {available}")
            animations = ANIMATIONS + (["Special"] if "Special" in available else [])
            print("ANIMATIONS", animations, flush=True)
            for anim in animations:
                anim_select = page.locator(".n-select").nth(2)
                select_option(page, anim_select, anim)
                page.wait_for_timeout(2000)
                download = find_download_button(page)
                with page.expect_download(timeout=300000) as info:
                    download.click()
                dl = info.value
                ext = os.path.splitext(dl.suggested_filename)[1] or ".webm"
                out_path = os.path.join(
                    out_dir, f"{operator}-{skin_label}-基建-{anim}-x1{ext}"
                )
                dl.save_as(out_path)
                print(
                    "EXPORTED",
                    anim,
                    "=>",
                    out_path,
                    os.path.getsize(out_path),
                )
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operator", help="Arknights operator name")
    parser.add_argument("--skin", default=None, help="skin name; default = 默认")
    parser.add_argument("--out", default="prts_webm", help="output directory")
    args = parser.parse_args()
    run_export(args.operator, args.skin, args.out)


if __name__ == "__main__":
    main()
