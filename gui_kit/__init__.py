"""
JIBI GUI Kit
============

Composants graphiques réutilisables pour l'interface JIBI.

La logique métier reste dans :
    core/
    self_improvement/
"""

from .theme import *
from .state import UIState
from .animation import Animation, ease_out_cubic
from .rounded import rounded_rect_points, draw_rounded_rect, RoundedFrame

from .controls import (
    round_rect,
    RoundedButton,
    RoundedFrame as ControlsRoundedFrame,
    IconButton,
    Divider,
)

from .scrollbar import ScrollArea, ThinScrollbar
from .status import StatusIndicator, StatusPill
from .chat_view import ChatView
from .input_bar import InputBar
from .sidebar import Sidebar
from .artifact_panel import ArtifactPanel


__all__ = [
    "COLORS",
    "RADIUS",
    "SPACING",
    "MOTION",
    "LAYOUT",
    "FONT",

    "UIState",

    "Animation",
    "ease_out_cubic",

    "rounded_rect_points",
    "draw_rounded_rect",
    "RoundedFrame",

    "round_rect",
    "RoundedButton",
    "ControlsRoundedFrame",
    "IconButton",
    "Divider",

    "ScrollArea",
    "ThinScrollbar",

    "StatusIndicator",
    "StatusPill",

    "ChatView",
    "InputBar",
    "Sidebar",
    "ArtifactPanel",
]