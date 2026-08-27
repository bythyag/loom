<p align="center">
  <img src="assets/loom-logo.svg" alt="Loom logo" width="180" />
</p>

# Loom

**A macOS-only, hardware-aware runtime for efficient AI agents.**

> **Model × Harness × Hardware should be optimized as one system.**

Loom explores how an AI agent can choose the most efficient execution path across local models, cloud models, memory, cache, and tools.

The project is intentionally **macOS-only for now**. Linux and Windows are out of scope for v0.x so Loom can optimize deeply for one environment before considering portability.

## Initial target

**MacBook Air M1 — 8 GB unified memory**

The goal is not to run the largest possible model. It is to make the **entire agent workload efficient under tight hardware constraints**.

Loom will focus on:

- local vs. cloud routing
- quantized local models
- unified-memory and swap pressure
- model loading and eviction
- context / KV-cache reuse
- agent-level latency, cost, and task success

## Core idea

```text
Agent Harness
     ↓
Execution Planner
  ↙   ↓   ↘
Local Cloud Tools
     ↓
macOS Hardware + Memory Telemetry
```

A simple task may run on a small local model. A harder task may be escalated to a cloud model. The decision should account for **task difficulty, model capability, memory pressure, model residency, cache locality, latency, and cost**.

## v0.1

The first milestone is a small coding / repository-research agent on macOS that can:

- profile M1 CPU/GPU and unified-memory pressure
- benchmark a small set of local models
- classify agent operations
- route work between local and cloud models
- measure model load time, memory pressure, latency, cloud usage, retries, and task success

Loom may use macOS- and Apple-Silicon-specific APIs and assumptions. Cross-platform abstractions are not a requirement yet.

## Status

Very early experimental project.

The first question Loom aims to answer is:

> **How much of a useful agent workload can an 8 GB M1 Mac run locally without materially reducing task quality?**

## Development setup

Loom requires Python 3.11 or newer and uses [uv](https://docs.astral.sh/uv/)
for its environment and lock file:

```shell
uv sync
uv run pytest
uv run ruff check .
```

Install a local runtime independently when needed with `uv sync --extra ollama`
or `uv sync --extra mlx`. Copy `.env.example` to `.env` for local secrets.
`OPENROUTER_API_KEY` is read only from the process environment or that ignored
local file; it does not belong in `config.example.toml`.

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).
