"""CPU/RAM sampling and the 'is the laptop stressed?' decision."""
from collections import deque
from dataclasses import dataclass
from typing import Callable

from buddy.config import StressConfig


@dataclass(frozen=True)
class Sample:
    cpu: float
    ram: float


def psutil_sampler() -> Sample:
    import psutil

    return Sample(cpu=psutil.cpu_percent(interval=None), ram=psutil.virtual_memory().percent)


class StressMonitor:
    """Hysteresis: enter on a high window average, leave only after a fully calm window."""

    def __init__(self, cfg: StressConfig, sampler: Callable[[], Sample] = psutil_sampler):
        self.cfg = cfg
        self._sampler = sampler
        self._window: deque[Sample] = deque(maxlen=cfg.window_seconds)
        self.stressed = False
        self.latest = Sample(0.0, 0.0)

    def tick(self) -> bool:
        try:
            sample = self._sampler()
        except Exception:
            self._window.clear()
            self.stressed = False
            return False
        self.latest = sample
        self._window.append(sample)
        if len(self._window) < self._window.maxlen:
            return self.stressed
        c = self.cfg
        if self.stressed:
            if all(s.cpu < c.cpu_exit and s.ram < c.ram_exit for s in self._window):
                self.stressed = False
        else:
            n = len(self._window)
            cpu = sum(s.cpu for s in self._window) / n
            ram = sum(s.ram for s in self._window) / n
            self.stressed = cpu >= c.cpu_enter or ram >= c.ram_enter
        return self.stressed
