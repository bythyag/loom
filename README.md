<p align="center">
  <img src="assets/loom-logo.svg" alt="Loom logo" width="180" />
</p>

# Loom

**A macOS-first, hardware-aware runtime for efficient AI agents.**

> **Model × Harness × Hardware should be optimized as one system.**

Loom is currently being built **only for macOS**. Linux and Windows support are intentionally out of scope for the initial development phase.

The goal is to start with one tightly defined hardware and operating-system environment, optimize deeply for it, establish strong benchmarks, and only consider portability later.

AI agent harnesses usually treat compute as an implementation detail. The same model may handle everything from simple classification to complex reasoning, while local hardware state, memory pressure, model residency, cache locality, and cloud latency are largely ignored.

Loom explores a different abstraction: make **where and how an agent operation executes** part of the runtime itself.

Loom aims to decide what should run locally, what should run in the cloud, what should remain resident in memory, what context can be reused, and when constrained hardware should stop trying to do work locally.

## Platform scope

Loom is **macOS-only for the current phase of the project**.

The implementation may deliberately use macOS- and Apple-Silicon-specific APIs, system behavior, memory semantics, profiling tools, and inference runtimes. Cross-platform abstractions are not a requirement for v0.x.

**Not currently supported:**

- Linux
- Windows
- non-Apple-Silicon hardware

Those platforms may be considered later, but only after the macOS implementation and benchmark methodology are mature.

## Initial target

The first reference system is intentionally constrained:

**macOS on a MacBook Air M1 — 8 GB unified memory**

The point is not to make an 8 GB laptop run the largest possible model. The goal is to make the **complete agent workload efficient under limited compute**.

This makes several systems problems first-class:

- macOS and Apple Silicon hardware profiling
- unified-memory-aware model selection
- small quantized local models
- local vs. cloud routing
- model loading and eviction
- swap and memory-pressure avoidance
- context and KV-cache management
- agent-level latency, cost, and quality measurement

## Architecture

```text
                       ┌─────────────────────┐
                       │     Agent Harness   │
                       └──────────┬──────────┘
                                  │ operation
                                  ▼
                       ┌─────────────────────┐
                       │  Execution Planner  │
                       └──────────┬──────────┘
                                  │
               ┌──────────────────┼──────────────────┐
               ▼                  ▼                  ▼
        ┌─────────────┐     ┌─────────────┐    ┌─────────────┐
        │  Local LLM  │     │  Cloud LLM  │    │    Tools    │
        └─────────────┘     └─────────────┘    └─────────────┘
               │                  │                  │
               └──────────────────┼──────────────────┘
                                  ▼
              ┌─────────────────────────────────────┐
              │ Hardware / Memory / Cache Telemetry │
              └─────────────────────────────────────┘
```

Loom is intended to sit between an agent harness and inference runtimes such as MLX, llama.cpp, Ollama, and remote model APIs.

The first implementation is free to optimize specifically for macOS rather than maintaining portable interfaces for other operating systems.

## Scheduling model

For an agent operation, Loom can score candidate execution paths using a constrained objective such as:

```text
J(p) = αL + βC + γE + δM + εF
```

where:

- `L` — expected latency
- `C` — monetary cost
- `E` — estimated energy use
- `M` — memory pressure / resource contention
- `F` — estimated probability of task failure

subject to a minimum acceptable task quality.

The first implementation will be simple and measurement-driven rather than a learned scheduler.

## v0.1

The initial milestone is deliberately small and macOS-specific:

- profile Apple M1 CPU/GPU and macOS unified-memory pressure
- monitor swap and memory pressure using macOS-specific system information where useful
- benchmark a small set of quantized local models
- classify common agent operations
- route operations between local and cloud models using simple rules
- track model load/eviction costs and memory pressure
- record latency, throughput, local/cloud tokens, retries, and task success
- benchmark complete agent tasks rather than tokens-per-second alone

The first workload will be a coding / repository-research agent running on an 8 GB M1 MacBook Air.

## Example

A repository-navigation task might be handled by a small local model already resident in memory:

```text
"Find where authentication is implemented."
        ↓
small local model
```

A more difficult architecture task may be escalated:

```text
"Design a migration strategy for the authentication system."
        ↓
local attempt? ── memory / quality check ──► cloud model
```

The interesting problem is not merely model routing. It is routing while accounting for **task difficulty + model capability + macOS hardware state + memory residency + cache locality**.

## Planned modules

```text
src/loom/
├── hardware/      # macOS / Apple Silicon machine and memory profiling
├── planner/       # operation classification and routing
├── runtime/       # macOS local inference + cloud adapters
├── cache/         # reusable context and cache state
├── telemetry/     # latency, memory, cost and quality metrics
└── harness/       # minimal reference agent loop

benchmarks/        # reproducible macOS agent workloads and baselines
```

## Baselines

Loom will compare three execution strategies on the same macOS reference system:

1. **Cloud-only** — all model operations use a frontier cloud model.
2. **Local-only** — all model operations use a local model that fits the target Mac.
3. **Loom** — operations are dynamically scheduled based on task and macOS hardware state.

A useful result is not necessarily zero cloud usage. A useful result is **close-to-cloud task quality with materially lower cost, latency, or unnecessary computation**.

## What Loom is not

Loom is not another LLM inference engine.

Loom is not another local-model launcher.

Loom is not intended to replace agent harnesses.

Loom is also **not currently a cross-platform runtime**.

It is a **macOS-specific execution layer for making agent workloads hardware-aware** during the project's initial phase.

## Status

Very early experimental project.

The immediate goal is to establish reproducible baselines on **macOS running on an 8 GB M1 MacBook Air** and determine which parts of an agent trajectory are actually worth executing locally.

Linux and Windows support are intentionally deferred.

## Contributing

The project is still being shaped. Issues, experiments, benchmark ideas, and systems-level contributions focused on macOS and Apple Silicon are welcome as the first runtime is developed.

## License

TBD.
