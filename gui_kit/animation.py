"""
JIBI GUI Kit — Animations
"""

from __future__ import annotations

import time
from typing import Callable


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, float(t)))
    return 1.0 - (1.0 - t) ** 3


class Animation:
    def __init__(
        self,
        root,
        duration: int = 180,
        update: Callable[[float], None] | None = None,
        done: Callable[[], None] | None = None,
        easing: Callable[[float], float] = ease_out_cubic,
    ) -> None:
        self.root = root
        self.duration = max(1, int(duration))
        self.update_callback = update
        self.done_callback = done
        self.easing = easing

        self.running = False
        self._after_id = None
        self._start_time = 0.0

    def start(self) -> None:
        self.stop()

        self.running = True
        self._start_time = time.perf_counter()

        self._tick()

    def _tick(self) -> None:
        if not self.running:
            return

        elapsed = (
            time.perf_counter() - self._start_time
        )

        progress = min(
            1.0,
            elapsed / (self.duration / 1000.0),
        )

        value = self.easing(progress)

        if self.update_callback:
            self.update_callback(value)

        if progress >= 1.0:
            self.running = False

            if self.done_callback:
                self.done_callback()

            return

        self._after_id = self.root.after(
            16,
            self._tick,
        )

    def stop(self) -> None:
        self.running = False

        if self._after_id is not None:
            try:
                self.root.after_cancel(
                    self._after_id
                )
            except Exception:
                pass

            self._after_id = None