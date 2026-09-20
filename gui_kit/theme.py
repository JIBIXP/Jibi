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
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))

def _rgb_to_hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, int(v))):02x}" for v in rgb)

def mix(c1: str, c2: str, t: float) -> str:
    t = max(0.0, min(1.0, float(t)))
    a = _hex_to_rgb(c1)
    b = _hex_to_rgb(c2)
    return _rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))

def lighten(color: str, amount: float) -> str:
    return mix(color, "#ffffff", amount)

def darken(color: str, amount: float) -> str:
    return mix(color, "#000000", amount)


# ============================================================
# PALETTE JIBI - PREMIUM MIDNIGHT OCEAN
# ============================================================

BG = "#030408"           # Très profond, presque noir
PANEL = "#0b0e15"        # Panneaux flottants
ELEVATED = "#131722"     # Survol / Secondaire

INPUT_BG = "#0f131d"     # Zones de texte

BORDER = "#1a2133"       # Bordures fines et élégantes
BORDER_SOFT = "#131825"


# ============================================================
# ACCENT & HIGHLIGHTS (NEON)
# ============================================================

ACCENT = "#00d2ff"       # Cyan ultra vibrant
ACCENT_CYAN = "#00f2fe"
ACCENT_PURPLE = "#8a2be2"
ACCENT_GREEN = "#00e676"

ACCENT_DARK = "#008ba8"
ACCENT_SOFT = "#082a3a"  # Fond cyan subtil
ACCENT_ON = "#011216"    # Texte sur accent


# ============================================================
# TEXTE
# ============================================================

TEXT = "#ffffff"         # Blanc pur pour fort contraste
TEXT_SUB = "#a1aab8"     # Gris bleuté clair
TEXT_DIM = "#707c91"     # Gris secondaire
TEXT_FAINT = "#424d63"   # Presque invisible


# ============================================================
# ÉTATS
# ============================================================

DANGER = "#ff1744"
OK = "#00e676"
WARNING = "#ff9100"
INFO = "#2979ff"


# ============================================================
# BULLES
# ============================================================

BUBBLE_BOT = "#111827"   # Gris très foncé, distinct du fond
BUBBLE_USER = "#1e293b"  # Gris-bleu élégant


# ============================================================
# RAYONS (ARRONDIS PLUS DOUS ET MODERNES)
# ============================================================

RADIUS = 16
RADIUS_SM = 10
RADIUS_PILL = 28


# ============================================================
# ESPACEMENTS (PLUS DE RESPIRATION)
# ============================================================

SPACE_XS = 6
SPACE_SM = 12
SPACE_MD = 16
SPACE_LG = 24
SPACE_XL = 32
SPACE_XXL = 48


# ============================================================
# ANIMATIONS
# ============================================================

MOTION_MS = 220
MOTION_FPS = 60
PULSE_PERIOD_MS = 1800


# ============================================================
# DIMENSIONS
# ============================================================

SIDEBAR_MIN = 240
SIDEBAR_MAX = 420
SIDEBAR_DEFAULT = 300

SIDEBAR_COLLAPSED_RAIL = 0

PANEL_MIN = 340
PANEL_MAX = 900
PANEL_DEFAULT = 460

RESIZE_HANDLE_W = 6


# ============================================================
# LAYOUT
# ============================================================

LAYOUT = {
    "sidebar_width": SIDEBAR_DEFAULT,
    "sidebar_min": SIDEBAR_MIN,
    "sidebar_max": SIDEBAR_MAX,
    "sidebar_collapsed": SIDEBAR_COLLAPSED_RAIL,
    "topbar_height": 72,      # Plus de hauteur pour le header
    "input_height": 72,       # Barre d'input plus spacieuse
    "content_padding": SPACE_LG,
    "panel_min": PANEL_MIN,
    "panel_max": PANEL_MAX,
    "resize_handle_width": RESIZE_HANDLE_W,
    "min_width": 1080,
    "min_height": 720,
}


# ============================================================
# POLICES
# ============================================================

def _sans_family() -> str:
    if sys.platform == "win32":
        return "Segoe UI"
    if sys.platform == "darwin":
        return "SF Pro Text"
    return "Inter"

def _serif_family() -> str:
    if sys.platform == "win32":
        return "Georgia"
    if sys.platform == "darwin":
        return "New York"
    return "Georgia"

def _mono_family() -> str:
    if sys.platform == "win32":
        return "Consolas"
    if sys.platform == "darwin":
        return "SF Mono"
    return "Fira Code"

def sans(size: int = 13, bold: bool = False):
    return (_sans_family(), size, "bold" if bold else "normal")

def serif(size: int = 24, bold: bool = True):
    return (_serif_family(), size, "bold" if bold else "normal")

def mono(size: int = 12, bold: bool = False):
    return (_mono_family(), size, "bold" if bold else "normal")


# ============================================================
# DICTIONNAIRE COLORS
# ============================================================

COLORS = {
    "bg": BG,
    "surface": PANEL,
    "surface_alt": ELEVATED,
    "panel": PANEL,
    "sidebar": PANEL,
    "sidebar_alt": ELEVATED,
    "elevated": ELEVATED,
    "input_bg": INPUT_BG,
    "border": BORDER,
    "border_soft": BORDER_SOFT,
    "border_dark": BORDER,
    "accent": ACCENT,
    "accent_hover": lighten(ACCENT, 0.15),
    "accent_dark": ACCENT_DARK,
    "accent_soft": ACCENT_SOFT,
    "accent_on": ACCENT_ON,
    "text": TEXT,
    "text_muted": TEXT_SUB,
    "text_sub": TEXT_SUB,
    "text_dim": TEXT_DIM,
    "text_faint": TEXT_FAINT,
    "text_inverse": TEXT,
    "ok": OK,
    "ok_soft": "#0f2e1d",
    "warning": WARNING,
    "warning_soft": "#331f05",
    "danger": DANGER,
    "danger_soft": "#330b13",
    "info": INFO,
    "info_soft": "#0c1b33",
    "bubble_bot": BUBBLE_BOT,
    "bubble_user": BUBBLE_USER,
    "user_bubble": BUBBLE_USER,
    "assistant_bubble": BUBBLE_BOT,
    "thinking": TEXT_DIM,
}

# ============================================================
# DICTIONNAIRE FONT
# ============================================================

FONT = {
    "family": _sans_family(),
    "mono": _mono_family(),
    "body": sans(13),
    "body_bold": sans(13, True),
    "small": sans(11),
    "small_bold": sans(11, True),
    "code": mono(12),
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