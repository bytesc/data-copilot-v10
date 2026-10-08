import logging
from pathlib import Path
import shutil
import subprocess
import sys

import matplotlib
from matplotlib import font_manager

logger = logging.getLogger(__name__)

# Fallback candidates, only consulted when the bundled font is unavailable.
CJK_FONT_CANDIDATES = (
    "Noto Sans CJK SC", "Noto Sans SC", "Noto Serif CJK SC",
    "WenQuanYi Zen Hei", "WenQuanYi Micro Hei",
    "AR PL UMing CN", "AR PL UKai CN",
    "PingFang SC", "Hiragino Sans GB", "STHeiti", "Arial Unicode MS",
    "Microsoft YaHei", "SimHei", "SimSun", "KaiTi",
)

# Bundled font shipped with the project so charts can render Chinese on
# servers that have no CJK font installed (zero system installation needed).
BUNDLED_FONT = (
    Path(__file__).resolve().parents[4]
    / "assets" / "fonts" / "NotoSansSC-Regular.otf"
)

_configured = False


def _register_linux_cjk_fonts():
    if not (sys.platform.startswith("linux") and shutil.which("fc-list")):
        return
    try:
        out = subprocess.run(
            ["fc-list", ":lang=zh", "file"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return
    for line in out.splitlines():
        path = line.split(":", 1)[0].strip()
        if not path:
            continue
        try:
            font_manager.fontManager.addfont(path)
        except Exception:
            continue


def _register_bundled_font():
    try:
        if not BUNDLED_FONT.is_file():
            return None
        font_manager.fontManager.addfont(str(BUNDLED_FONT))
        return font_manager.FontProperties(fname=str(BUNDLED_FONT)).get_name()
    except Exception as e:
        logger.warning("Failed to load bundled CJK font %s: %s", BUNDLED_FONT, e)
        return None


def _apply(family):
    matplotlib.rcParams["font.family"] = family
    matplotlib.rcParams["axes.unicode_minus"] = False
    logger.info("Matplotlib Chinese font: %s", family)


def setup_chinese_font():
    """Configure matplotlib to render Chinese text using the bundled font.

    The bundled Noto Sans SC font (assets/fonts/NotoSansSC-Regular.otf) is
    used directly so charts render identically on every OS, with zero system
    font installation. System CJK fonts are only consulted as a fallback when
    the bundled font file is missing from the deployment.

    Returns the chosen font family name, or None when no CJK font is found.
    """
    global _configured
    if _configured:
        return None

    chosen = _register_bundled_font()
    if chosen is None:
        _register_linux_cjk_fonts()
        available = {f.name for f in font_manager.fontManager.ttflist}
        chosen = next((name for name in CJK_FONT_CANDIDATES if name in available), None)

    if chosen:
        _apply(chosen)
        _configured = True
        return chosen

    logger.warning(
        "No CJK font found; Chinese text may render as boxes. "
        "Ensure %s exists in the project, or install a CJK font "
        "(e.g. on Ubuntu: sudo apt install fonts-noto-cjk).",
        BUNDLED_FONT,
    )
    return None


setup_chinese_font()
