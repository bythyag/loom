"""Unprivileged macOS hardware sampling with fixture-friendly parsers."""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import psutil

from loom.contracts import HardwareSnapshot, MemoryPressure

Phase = Literal["before", "during", "after"]
Runner = Callable[[tuple[str, ...]], str]


def _number(line: str) -> int:
    match = re.search(r"(-?[\d.]+)", line.rsplit(":", 1)[-1])
    return int(float(match.group(1))) if match else 0


def parse_vm_stat(output: str) -> dict[str, int]:
    """Parse vm_stat output into byte counts, retaining documented field names."""
    page_match = re.search(r"page size of (\d+) bytes", output)
    page_size = int(page_match.group(1)) if page_match else 4096
    pages: dict[str, int] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        name = line.split(":", 1)[0].strip().lower().replace(" ", "_")
        pages[name] = max(0, _number(line))
    result = {f"{name}_bytes": count * page_size for name, count in pages.items()}
    result["page_size_bytes"] = page_size
    return result


def parse_memory_pressure(output: str) -> tuple[MemoryPressure, dict[str, int]]:
    """Parse memory_pressure's percentage and swap fields without locale assumptions."""
    values: dict[str, int] = {}
    for line in output.splitlines():
        key = line.split(":", 1)[0].strip().lower().replace(" ", "_")
        if ":" in line:
            values[key] = max(0, _number(line))
    free = values.get("system-wide_memory_free_percentage")
    if free is None:
        pressure = MemoryPressure.UNKNOWN
    elif free <= 5:
        pressure = MemoryPressure.CRITICAL
    elif free <= 15:
        pressure = MemoryPressure.WARN
    else:
        pressure = MemoryPressure.NORMAL
    return pressure, values


def parse_thermal_state(output: str) -> str | None:
    match = re.search(r"thermal level:\s*(\d+)", output, re.IGNORECASE)
    if not match:
        return None
    return {0: "nominal", 1: "fair", 2: "serious", 3: "critical"}.get(
        int(match.group(1)), "unknown"
    )


@dataclass(frozen=True, slots=True)
class ProfilerSample:
    phase: Phase
    snapshot: HardwareSnapshot
    process_rss_bytes: int | None
    process_cpu_load: float | None
    overhead_ms: float
    thermal_state: str | None = None
    energy_joules: float | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProfileRun:
    samples: tuple[ProfilerSample, ...]
    interval_seconds: float

    @property
    def profiler_overhead_ms(self) -> float:
        return sum(sample.overhead_ms for sample in self.samples)

    @property
    def swap_in_delta_bytes(self) -> int:
        return max(0, self.samples[-1].snapshot.swap_in_bytes - self.samples[0].snapshot.swap_in_bytes)

    @property
    def swap_out_delta_bytes(self) -> int:
        return max(0, self.samples[-1].snapshot.swap_out_bytes - self.samples[0].snapshot.swap_out_bytes)


def _run(command: tuple[str, ...]) -> str:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout if completed.returncode == 0 else ""


class MacOSHardwareProfiler:
    """Collect before/during/after samples; never invokes sudo or powermetrics."""

    def __init__(
        self,
        *,
        interval_seconds: float = 1.0,
        collect_thermal: bool = True,
        energy_reader: Callable[[], float | None] | None = None,
        runner: Runner = _run,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero")
        self.interval_seconds = interval_seconds
        self.collect_thermal = collect_thermal
        self._energy_reader = energy_reader
        self._runner = runner
        self._clock = clock

    def sample(self, phase: Phase) -> ProfilerSample:
        started = self._clock()
        vm_raw = self._runner(("vm_stat",))
        pressure_raw = self._runner(("memory_pressure",))
        thermal_raw = self._runner(("pmset", "-g", "therm")) if self.collect_thermal else ""
        vm = parse_vm_stat(vm_raw)
        pressure, pressure_values = parse_memory_pressure(pressure_raw)
        process = psutil.Process(os.getpid())
        cpu = min(max(psutil.cpu_percent(interval=None) / 100, 0.0), 1.0)
        rss = process.memory_info().rss
        snapshot = HardwareSnapshot(
            timestamp=datetime.now(UTC).isoformat(),
            memory_pressure=pressure,
            free_memory_bytes=vm.get("pages_free_bytes", 0),
            active_memory_bytes=vm.get("pages_active_bytes", 0),
            wired_memory_bytes=vm.get("pages_wired_down_bytes", 0),
            compressed_memory_bytes=vm.get("pages_occupied_by_compressor_bytes", 0),
            swap_in_bytes=vm.get("swapins_bytes", 0),
            swap_out_bytes=vm.get("swapouts_bytes", 0),
            cpu_load=cpu,
        )
        overhead_ms = (self._clock() - started) * 1000
        return ProfilerSample(
            phase=phase,
            snapshot=snapshot,
            process_rss_bytes=rss,
            process_cpu_load=min(max(process.cpu_percent(interval=None) / 100, 0.0), 1.0),
            overhead_ms=overhead_ms,
            thermal_state=parse_thermal_state(thermal_raw),
            energy_joules=self._energy_reader() if self._energy_reader else None,
            raw={
                "vm_stat": vm_raw,
                "memory_pressure": pressure_raw,
                "pmset_thermal": thermal_raw,
                "vm_stat_fields": vm,
                "memory_pressure_fields": pressure_values,
            },
        )

    def profile(self, operation: Callable[[], Any]) -> tuple[Any, ProfileRun]:
        samples = [self.sample("before")]
        stop = threading.Event()

        def sample_during() -> None:
            while not stop.wait(self.interval_seconds):
                samples.append(self.sample("during"))

        worker = threading.Thread(target=sample_during, daemon=True)
        worker.start()
        try:
            result = operation()
        finally:
            stop.set()
            worker.join()
            samples.append(self.sample("after"))
        return result, ProfileRun(tuple(samples), self.interval_seconds)
