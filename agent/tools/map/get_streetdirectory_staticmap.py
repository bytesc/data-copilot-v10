# Dependency: playwright + a browser. Manual install:
#
#   pip install playwright
#   # Windows, install bundled Chromium:
#   python -m playwright install chromium
#   # Linux (Ubuntu/Debian), install bundled Chromium + system libs:
#   python3 -m playwright install --with-deps chromium
#   # Linux, optional: install system Google Chrome instead (auto-detected):
#   wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
#   sudo apt install -y /tmp/chrome.deb
#
#
# In Docker this is handled by docker/Dockerfile.backend automatically.
import io
from typing import List, Optional

from PIL import Image

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except Exception:
    HAS_PLAYWRIGHT = False

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _launch_browser(p):
    try:
        return p.chromium.launch(channel="chrome", headless=True)
    except Exception:
        return p.chromium.launch(headless=True, args=["--no-sandbox"])


def get_streetdirectory_static_map_func(
        urls: Optional[List[str]] = None,
        width: int = 800,
        height: int = 600,
) -> List[bytes]:
    """Render StreetDirectory location pages into PNG images with a headless browser.

    Opens each location page URL in headless Chrome (Playwright, system Chrome),
    waits for the map tiles inside #drag_map to load, and screenshots just the
    map element. Returns one PNG byte string per URL.
    """
    if not HAS_PLAYWRIGHT:
        raise RuntimeError(
            "playwright is not installed, please install it with: pip install playwright"
        )
    if not urls:
        urls = []
    urls = [u.strip() for u in urls if isinstance(u, str) and u.strip()]

    results: List[bytes] = []
    with sync_playwright() as p:
        browser = _launch_browser(p)
        try:
            context = browser.new_context(
                viewport={"width": max(width, 400), "height": max(height, 300)},
                device_scale_factor=1,
                user_agent=USER_AGENT,
            )
            for url in urls:
                page = context.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(4000)
                    try:
                        page.wait_for_function(
                            """() => {
                                const map = document.getElementById('drag_map');
                                if (!map) return false;
                                const imgs = Array.from(map.querySelectorAll('img'));
                                return imgs.length > 0 &&
                                       imgs.some(i => i.complete && i.naturalWidth > 0);
                            }""",
                            timeout=20000,
                        )
                    except Exception:
                        pass
                    page.wait_for_timeout(2500)
                    el = page.query_selector("#drag_map")
                    if el is None:
                        continue
                    png = el.screenshot()
                    img = Image.open(io.BytesIO(png)).convert("RGB")
                    if img.size[0] > width or img.size[1] > height:
                        left = (img.size[0] - width) // 2
                        top = (img.size[1] - height) // 2
                        img = img.crop((left, top, left + width, top + height))
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    results.append(buf.getvalue())
                finally:
                    page.close()
        finally:
            browser.close()
    return results
