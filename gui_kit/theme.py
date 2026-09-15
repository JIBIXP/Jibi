# =========================================================
# gui_kit/theme.py — Design tokens de JIBI (Aurora Studio)
# =========================================================
# Ce module ne contient AUCUNE logique de fenêtre : uniquement
# des constantes et de petites fonctions pures (calcul de couleur,
# choix de police). Les widgets importent ce module, jamais l'inverse.
# =========================================================
from __future__ import annotations
import sys


# ---------------------------------------------------------
# Couleurs de base — plusieurs nuances de sombre pour créer
# de la profondeur (pas un noir plat uniforme), + un seul accent.
# ---------------------------------------------------------
def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#" + "".join(f"{max(0, min(255, int(v))):02x}" for v in rgb)


def mix(c1: str, c2: str, t: float) -> str:
    """Mélange linéaire entre deux couleurs hex, t dans [0, 1]."""
    a, b = _hex_to_rgb(c1), _hex_to_rgb(c2)
    return _rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


def lighten(hexcolor: str, amount: float) -> str:
    """Nuance neutre : mélange vers le blanc, sans changer la teinte dominante."""
    return mix(hexcolor, "#ffffff", amount)


def darken(hexcolor: str, amount: float) -> str:
    return mix(hexcolor, "#000000", amount)


# Fond quasi-noir, décliné en 3 profondeurs + 1 accent unique.
BG = "#0d0d0f"          # fond principal (zone de conversation)
PANEL = "#1a1a1d"       # panneaux (sidebar, artifact panel)
ELEVATED = "#232326"    # éléments actifs / survolés / sélectionnés
INPUT_BG = lighten(PANEL, 0.06)
BORDER = lighten(BG, 0.16)
BORDER_SOFT = lighten(BG, 0.09)

# Accent unique : un teal désaturé, plus "sophistiqué" que le teal vif
# d'origine — utilisé avec parcimonie (boutons primaires, statut, focus).
ACCENT = "#4FB8A6"
ACCENT_DARK = darken(ACCENT, 0.28)
ACCENT_SOFT = mix(ACCENT, PANEL, 0.80)   # teinte d'accent très diluée (fonds de sélection)
ACCENT_ON = "#0b1211"                     # texte sur fond accent plein

TEXT = "#f1efe9"          # blanc cassé, plus doux qu'un blanc pur
TEXT_SUB = lighten(BG, 0.52)
TEXT_DIM = lighten(BG, 0.32)
TEXT_FAINT = lighten(BG, 0.22)

# Pas de rouge criard : un neutre chaud suffit pour signaler une erreur,
# le mot "Erreur" porte le sens (cohérent avec la philosophie "un seul accent").
DANGER = "#c98b7a"

# Bulles de conversation — dérivées du fond, pas une couleur à part.
BUBBLE_BOT = lighten(BG, 0.05)
BUBBLE_USER = lighten(BG, 0.10)

# ---------------------------------------------------------
# Rayon de coin unique, réutilisé partout (8-12px demandés).
# ---------------------------------------------------------
RADIUS = 10
RADIUS_SM = 6
RADIUS_PILL = 22  # barre de saisie, avatars

# ---------------------------------------------------------
# Espacements (échelle cohérente)
# ---------------------------------------------------------
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
SPACE_XXL = 32

# ---------------------------------------------------------
# Durées / easing des micro-animations
# ---------------------------------------------------------
MOTION_MS = 220          # slide sidebar / panel
MOTION_FPS = 60
PULSE_PERIOD_MS = 1800   # respiration du statut

# ---------------------------------------------------------
# Dimensions de layout
# ---------------------------------------------------------
SIDEBAR_MIN = 220
SIDEBAR_MAX = 420
SIDEBAR_DEFAULT = 280
SIDEBAR_COLLAPSED_RAIL = 0   # 0 = totalement masquée (pas de rail résiduel)

PANEL_MIN = 320
PANEL_MAX = 900
PANEL_DEFAULT = 440

RESIZE_HANDLE_W = 6


# ---------------------------------------------------------
# Polices — sans-serif système pour le corps, serif éditorial
# pour les titres, avec repli propre multi-plateforme.
# ---------------------------------------------------------
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


def sans(size: int = 11, bold: bool = False):
    return (_sans_family(), size, "bold" if bold else "normal")


def serif(size: int = 22, bold: bool = True):
    return (_serif_family(), size, "bold" if bold else "normal")


def mono(size: int = 11, bold: bool = False):
    return (_mono_family(), size, "bold" if bold else "normal")
