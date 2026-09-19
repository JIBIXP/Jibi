"""
JIBI GUI Kit — Rounded primitives
=================================

API graphique bas niveau.
"""

from __future__ import annotations

import tkinter as tk


def rounded_rect_points(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
) -> list[float]:
    radius = max(
        0,
        min(
            radius,
            abs(x2 - x1) / 2,
            abs(y2 - y1) / 2,
        ),
    )

    return [
        x1 + radius,
        y1,
        x2 - radius,
        y1,

        x2,
        y1,
        x2,
        y1 + radius,

        x2,
        y2 - radius,
        x2,
        y2,

        x2 - radius,
        y2,
        x1 + radius,
        y2,

        x1,
        y2,
        x1,
        y2 - radius,

        x1,
        y1 + radius,
        x1,
        y1,
    ]


def draw_rounded_rect(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float = 12,
    fill: str = "",
    outline: str = "",
    width: int = 1,
    tags=None,
):
    points = rounded_rect_points(
        x1,
        y1,
        x2,
        y2,
        radius,
    )

    return canvas.create_polygon(
        points,
        smooth=True,
        splinesteps=20,
        fill=fill,
        outline=outline,
        width=width,
        tags=tags,
    )


class RoundedFrame(tk.Canvas):
    """
    Canvas utilisé comme frame arrondi.

    Le widget fournit un conteneur .body dans lequel
    les composants peuvent être placés.
    """

    def __init__(
        self,
        master,
        radius: int = 14,
        fill: str = "#ffffff",
        outline: str = "",
        border_width: int = 0,
        **kwargs,
    ):
        super().__init__(
            master,
            highlightthickness=0,
            bd=0,
            bg=kwargs.pop(
                "bg",
                master.cget("bg")
                if hasattr(master, "cget")
                else "#ffffff",
            ),
            **kwargs,
        )

        self.radius = radius
        self.fill = fill
        self.outline = outline
        self.border_width = border_width

        self.body = tk.Frame(
            self,
            bg=self.fill,
        )

        self._window = self.create_window(
            0,
            0,
            window=self.body,
            anchor="nw",
        )

        self.bind(
            "<Configure>",
            self._on_configure,
        )

    def _on_configure(self, event=None) -> None:
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())

        self.delete("background")

        draw_rounded_rect(
            self,
            1,
            1,
            width - 1,
            height - 1,
            self.radius,
            fill=self.fill,
            outline=self.outline,
            width=self.border_width,
            tags="background",
        )

        self.tag_lower("background")

        self.coords(
            self._window,
            0,
            0,
        )

        self.itemconfigure(
            self._window,
            width=width,
            height=height,
        )