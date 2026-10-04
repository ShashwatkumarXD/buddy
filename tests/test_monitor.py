from buddy.config import StressConfig
from buddy.monitor import Sample, StressMonitor


class FakeSampler:
    def __init__(self, samples):
        self.samples = list(samples)

    def __call__(self):
        sample = self.samples.pop(0)
        if isinstance(sample, Exception):
            raise sample
        return sample


def run(samples):
    monitor = StressMonitor(StressConfig(), FakeSampler(samples))
    states = [monitor.tick() for _ in samples]
    return monitor, states


def cpu(*values, ram=50.0):
    return [Sample(v, ram) for v in values]


def test_needs_a_full_window_before_stressing():
    _, states = run(cpu(100, 100, 100, 100))
    assert states == [False] * 4


def test_sustained_high_cpu_enters_stress():
    _, states = run(cpu(90, 90, 90, 90, 90))
    assert states[-1] is True


def test_single_spike_is_ignored():
    _, states = run(cpu(10, 10, 10, 10, 100))
    assert not any(states)


def test_high_ram_enters_stress():
    _, states = run([Sample(10, 95)] * 5)
    assert states[-1] is True


def test_stays_stressed_between_exit_and_enter_thresholds():
    _, states = run(cpu(90, 90, 90, 90, 90, 75, 75, 75, 75, 75, 75))
    assert all(states[4:])


def test_calms_only_after_a_full_calm_window():
    _, states = run(cpu(90, 90, 90, 90, 90, 50, 50, 50, 50, 50))
    assert states[8] is True  # four calm samples: not yet
    assert states[9] is False  # five calm samples: calm


def test_ram_above_exit_threshold_keeps_stress():
    _, states = run([Sample(90, 50)] * 5 + [Sample(10, 87)] * 6)
    assert all(states[4:])


def test_sampler_failure_means_not_stressed():
    _, states = run(cpu(90, 90, 90, 90, 90) + [OSError("boom")])
    assert states[4] is True
    assert states[5] is False


def test_latest_sample_is_exposed():
    monitor, _ = run([Sample(42, 63)])
    assert monitor.latest == Sample(42, 63)
