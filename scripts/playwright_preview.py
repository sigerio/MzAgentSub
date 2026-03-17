#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import math
from pathlib import Path

from playwright.sync_api import sync_playwright


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="使用 Playwright 截取 Web 页面预览图。")
    parser.add_argument("--url", required=True, help="要访问的页面地址。")
    parser.add_argument("--out", required=True, help="截图输出路径。")
    parser.add_argument("--width", type=int, default=1440, help="视口宽度。")
    parser.add_argument("--height", type=int, default=1200, help="视口高度。")
    parser.add_argument("--delay-ms", type=int, default=1500, help="页面加载后额外等待毫秒数。")
    parser.add_argument("--full-page", action="store_true", help="是否截取整页。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--disable-software-rasterizer",
            ],
        )
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        page.goto(args.url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_load_state("networkidle", timeout=15000)
        page.wait_for_timeout(args.delay_ms)
        page.add_style_tag(content="*{animation:none !important;transition:none !important;caret-color:transparent !important;}")
        client = page.context.new_cdp_session(page)
        client.send("Page.enable")
        params = {
            "format": "png",
            "fromSurface": True,
        }
        if args.full_page:
            metrics = client.send("Page.getLayoutMetrics")
            css_size = metrics["cssContentSize"]
            params["captureBeyondViewport"] = True
            params["clip"] = {
                "x": 0,
                "y": 0,
                "width": math.ceil(css_size["width"]),
                "height": math.ceil(css_size["height"]),
                "scale": 1,
            }
        result = client.send("Page.captureScreenshot", params)
        out_path.write_bytes(base64.b64decode(result["data"]))
        browser.close()

    print(f"预览截图已生成：{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
