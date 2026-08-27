import time
from pathlib import Path

import pytest

from loom.contracts import MemoryPressure
from loom.hardware.macos import (
    MacOSHardwareProfiler,
    parse_memory_pressure,
    parse_thermal_state,
    parse_vm_stat,
)

FIXTURES = Path(__file__).parent / "fixtures" / "macos"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_parses_recorded_vm_stat_output_as_bytes() -> None:
    values = parse_vm_stat(fixture("vm_stat.txt"))
    assert values["page_size_bytes"] == 16_384
    assert values["pages_free_bytes"] == 100 * 16_384
    assert values["pages_occupied_by_compressor_bytes"] == 25 * 16_384
    assert values["swapouts_bytes"] == 5 * 16_384


def test_parses_pressure_and_optional_thermal_metadata() -> None:
    pressure, raw = parse_memory_pressure(fixture("memory_pressure.txt"))
    assert pressure is MemoryPressure.WARN
    assert raw["system-wide_memory_free_percentage"] == 12
    assert parse_thermal_state(fixture("thermal.txt")) == "fair"
    assert parse_thermal_state("") is None


def test_profiler_preserves_raw_and_records_before_during_after() -> None:
    outputs = {
        ("vm_stat",): fixture("vm_stat.txt"),
        ("memory_pressure",): fixture("memory_pressure.txt"),
        ("pmset", "-g", "therm"): fixture("thermal.txt"),
    }
    profiler = MacOSHardwareProfiler(
        interval_seconds=0.01,
        runner=lambda command: outputs[command],
    )
    result, run = profiler.profile(lambda: (time.sleep(0.035), "done")[1])
    assert result == "done"
    assert run.samples[0].phase == "before"
    assert run.samples[-1].phase == "after"
    assert any(sample.phase == "during" for sample in run.samples)
    assert run.samples[0].raw["vm_stat"] == fixture("vm_stat.txt")
    assert run.samples[0].thermal_state == "fair"
    assert run.profiler_overhead_ms >= 0
    assert run.swap_in_delta_bytes == 0
    assert run.swap_out_delta_bytes == 0


def test_profiler_never_uses_privileged_commands() -> None:
    commands: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]) -> str:
        commands.append(command)
        return ""

    sample = MacOSHardwareProfiler(runner=runner).sample("before")
    assert sample.snapshot.memory_pressure is MemoryPressure.UNKNOWN
    assert all(command[0] not in {"sudo", "powermetrics"} for command in commands)
    assert sample.energy_joules is None


def test_energy_is_only_read_from_an_explicit_unprivileged_source() -> None:
    profiler = MacOSHardwareProfiler(runner=lambda command: "", energy_reader=lambda: 1.25)
    assert profiler.sample("after").energy_joules == 1.25


def test_rejects_nonpositive_sampling_interval() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        MacOSHardwareProfiler(interval_seconds=0)
