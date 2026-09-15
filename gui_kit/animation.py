# =========================================================
# gui_kit/animation.py — Moteur d'animation minimal pour Tk
# =========================================================
# Tkinter n'a pas d'animations natives : on anime en rappelant
# `after()` à ~60fps et en interpolant une valeur avec un easing
# "ease-out" (démarre vite, ralentit en fin de course — plus
# naturel qu'une interpolation linéaire pour un slide de panneau).
# =========================================================
from __future__ import annotations
from typing import Callable, Optional


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


class Animation:
    """Anime une valeur numérique de `start` à `end` sur `duration_ms`.

    `on_step(value)` est appelé à chaque frame, `on_done()` une fois
    l'animation terminée. Peut être annulée via `.cancel()` — utile
    quand l'utilisateur redéclenche un toggle avant la fin du slide.
    """

    def __init__(
        self,
        widget,
        start: float,
        end: float,
        duration_ms: int,
        on_step: Callable[[float], None],
        on_done: Optional[Callable[[], None]] = None,
        fps: int = 60,
    ):
        self._widget = widget
        self._start = start
        self._end = end
        self._duration = max(1, duration_ms)
        self._on_step = on_step
        self._on_done = on_done
        self._interval = max(1, int(1000 / fps))
        self._t0 = None
        self._after_id = None
        self._cancelled = False

    def start_run(self) -> "Animation":
        import time
        self._t0 = time.monotonic()
        self._tick()
        return self

    def cancel(self) -> None:
        self._cancelled = True
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _tick(self) -> None:
        if self._cancelled:
            return
        import time
        elapsed = (time.monotonic() - self._t0) * 1000.0
        t = min(1.0, elapsed / self._duration)
        value = self._start + (self._end - self._start) * ease_out_cubic(t)
        try:
            self._on_step(value)
        except Exception:
            pass
        if t >= 1.0:
            if self._on_done:
                try:
                    self._on_done()
                except Exception:
                    pass
            return
        self._after_id = self._widget.after(self._interval, self._tick)


def animate(widget, start, end, duration_ms, on_step, on_done=None, fps=60) -> Animation:
    return Animation(widget, start, end, duration_ms, on_step, on_done, fps).start_run()
