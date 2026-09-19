"""
JIBI GUI Kit — Theme
====================

Design tokens centralisés.
Compatible avec gui.py et les composants gui_kit.
"""

from __future__ import annotations

import sys


# ============================================================
# COULEURS
# ============================================================

def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")

    if len(value) != 6:
        raise ValueError(f"Couleur hex invalide : {value}")

    return tuple(
        int(value[i:i + 2], 16)
        for i in (0, 2, 4)
    )


def _rgb_to_hex(rgb) -> str:
    return "#" + "".join(
        f"{max(0, min(255, int(v))):02x}"
        for v in rgb
    )


def mix(c1: str, c2: str, t: float) -> str:
    t = max(0.0, min(1.0, float(t)))

    a = _hex_to_rgb(c1)
    b = _hex_to_rgb(c2)

    return _rgb_to_hex(
        tuple(
            a[i] + (b[i] - a[i]) * t
            for i in range(3)
        )
    )


def lighten(color: str, amount: float) -> str:
    return mix(color, "#ffffff", amount)


def darken(color: str, amount: float) -> str:
    return mix(color, "#000000", amount)


# ============================================================
# PALETTE JIBI
# ============================================================

BG = "#0d0d0f"
PANEL = "#1a1a1d"
ELEVATED = "#232326"

INPUT_BG = lighten(PANEL, 0.06)

BORDER = lighten(BG, 0.16)
BORDER_SOFT = lighten(BG, 0.09)


# ============================================================
# ACCENT
# ============================================================

ACCENT = "#4FB8A6"

ACCENT_DARK = darken(ACCENT, 0.28)

ACCENT_SOFT = mix(
    ACCENT,
    PANEL,
    0.80,
)

ACCENT_ON = "#0b1211"


# ============================================================
# TEXTE
# ============================================================

TEXT = "#f1efe9"

TEXT_SUB = lighten(BG, 0.52)

TEXT_DIM = lighten(BG, 0.32)

TEXT_FAINT = lighten(BG, 0.22)


# ============================================================
# ÉTATS
# ============================================================

DANGER = "#c98b7a"

OK = "#55b889"

WARNING = "#d3a85c"

INFO = "#6ea8dc"


# ============================================================
# BULLES
# ============================================================

BUBBLE_BOT = lighten(BG, 0.05)

BUBBLE_USER = lighten(BG, 0.10)


# ============================================================
# RAYONS
# ============================================================

RADIUS = 10

RADIUS_SM = 6

RADIUS_PILL = 22


# ============================================================
# ESPACEMENTS
# ============================================================

SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
SPACE_XXL = 32


# ============================================================
# ANIMATIONS
# ============================================================

MOTION_MS = 220

MOTION_FPS = 60

PULSE_PERIOD_MS = 1800


# ============================================================
# DIMENSIONS
# ============================================================

SIDEBAR_MIN = 220
SIDEBAR_MAX = 420
SIDEBAR_DEFAULT = 280

SIDEBAR_COLLAPSED_RAIL = 0

PANEL_MIN = 320
PANEL_MAX = 900
PANEL_DEFAULT = 440

RESIZE_HANDLE_W = 6


# ============================================================
# LAYOUT
# ============================================================

LAYOUT = {
    "sidebar_width": SIDEBAR_DEFAULT,
    "sidebar_min": SIDEBAR_MIN,
    "sidebar_max": SIDEBAR_MAX,

    "sidebar_collapsed": SIDEBAR_COLLAPSED_RAIL,

    "topbar_height": 58,

    "input_height": 60,

    "content_padding": SPACE_LG,

    "panel_min": PANEL_MIN,
    "panel_max": PANEL_MAX,

    "resize_handle_width": RESIZE_HANDLE_W,

    "min_width": 1020,
    "min_height": 640,
}


# ============================================================
# POLICES
# ============================================================

def _sans_family() -> str:
    if sys.platform == "win32":
        return "Segoe UI"

    if sys.platform == "darwin":
        return "Helvetica Neue"

    return "Noto Sans"


def _serif_family() -> str:
    if sys.platform == "win32":
        return "Cambria"

    if sys.platform == "darwin":
        return "Iowan Old Style"

    return "Georgia"


def _mono_family() -> str:
    if sys.platform == "win32":
        return "Consolas"

    if sys.platform == "darwin":
        return "Menlo"

    return "DejaVu Sans Mono"


def sans(
    size: int = 11,
    bold: bool = False,
):
    return (
        _sans_family(),
        size,
        "bold" if bold else "normal",
    )


def serif(
    size: int = 22,
    bold: bool = True,
):
    return (
        _serif_family(),
        size,
        "bold" if bold else "normal",
    )


def mono(
    size: int = 11,
    bold: bool = False,
):
    return (
        _mono_family(),
        size,
        "bold" if bold else "normal",
    )


# ============================================================
# DICTIONNAIRE COLORS
# ============================================================

COLORS = {
    # Fonds
    "bg": BG,
    "surface": lighten(BG, 0.04),
    "surface_alt": lighten(BG, 0.07),

    "panel": PANEL,
    "sidebar": PANEL,
    "sidebar_alt": ELEVATED,
    "elevated": ELEVATED,
    "input_bg": INPUT_BG,

    # Bordures
    "border": BORDER,
    "border_soft": BORDER_SOFT,
    "border_dark": BORDER,

    # Accent
    "accent": ACCENT,
    "accent_hover": lighten(ACCENT, 0.12),
    "accent_dark": ACCENT_DARK,
    "accent_soft": ACCENT_SOFT,
    "accent_on": ACCENT_ON,

    # Texte
    "text": TEXT,
    "text_muted": TEXT_SUB,
    "text_sub": TEXT_SUB,
    "text_dim": TEXT_DIM,
    "text_faint": TEXT_FAINT,
    "text_inverse": TEXT,

    # États
    "ok": OK,
    "ok_soft": "#18352c",

    "warning": WARNING,
    "warning_soft": "#3a301d",

    "danger": DANGER,
    "danger_soft": "#3a2522",

    "info": INFO,
    "info_soft": "#202f3d",

    # Conversation
    "bubble_bot": BUBBLE_BOT,
    "bubble_user": BUBBLE_USER,

    "user_bubble": BUBBLE_USER,
    "assistant_bubble": BUBBLE_BOT,

    # Réflexion
    "thinking": TEXT_DIM,
}


# ============================================================
# DICTIONNAIRE FONT
# ============================================================

FONT = {
    "family": _sans_family(),
    "mono": _mono_family(),

    "body": sans(10),
    "body_bold": sans(10, True),

    "small": sans(9),
    "small_bold": sans(9, True),

    "code": mono(9),
}


# ============================================================
# DICTIONNAIRE RADIUS
# ============================================================

RADIUS_MAP = {
    "xs": RADIUS_SM,
    "sm": RADIUS_SM,
    "md": RADIUS,
    "lg": RADIUS_PILL,
    "pill": RADIUS_PILL,
}


# ============================================================
# DICTIONNAIRE SPACING
# ============================================================

SPACING = {
    "xs": SPACE_XS,
    "sm": SPACE_SM,
    "md": SPACE_MD,
    "lg": SPACE_LG,
    "xl": SPACE_XL,
    "xxl": SPACE_XXL,
}