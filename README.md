# Loom

**A hardware-aware runtime for efficient AI agents.**

> **Model × Harness × Hardware should be optimized as one system.**

AI agent harnesses usually treat compute as an implementation detail. The same model may handle everything from simple classification to complex reasoning, while local hardware state, memory pressure, model residency, cache locality, and cloud latency are largely ignored.

Loom explores a different abstraction: make **where and how an agent operation executes** part of the runtime itself.

Loom aims to decide what should run locally, what should run in the cloud, what should remain resident in memory, what context can be reused, and when constrained hardware should stop trying to do work locally.

## Initial target

The first reference platform is intentionally constrained:

**MacBook Air M1 — 8 GB unified memory**

The point is not to make an 8 GB laptop run the largest possible model. The goal is to make the **complete agent workload efficient under limited compute**.

This makes several systems problems first-class:

- memory-aware model selection
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

The initial milestone is deliberately small:

- profile Apple M1 CPU/GPU and unified-memory pressure
- benchmark a small set of quantized local models
- classify common agent operations
- route operations between local and cloud models using simple rules
- track model load/eviction costs and memory pressure
- record latency, throughput, local/cloud tokens, retries, and task success
- benchmark complete agent tasks rather than tokens-per-second alone

The first workload will be a coding / repository-research agent.

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

The interesting problem is not merely model routing. It is routing while accounting for **task difficulty + model capability + hardware state + memory residency + cache locality**.

## Planned modules

```text
src/loom/
├── hardware/      # machine and memory profiling
├── planner/       # operation classification and routing
├── runtime/       # local/cloud inference adapters
├── cache/         # reusable context and cache state
├── telemetry/     # latency, memory, cost and quality metrics
└── harness/       # minimal reference agent loop

benchmarks/        # reproducible agent workloads and baselines
```

## Baselines

Loom will compare three execution strategies:

1. **Cloud-only** — all model operations use a frontier cloud model.
2. **Local-only** — all model operations use a local model that fits the target machine.
3. **Loom** — operations are dynamically scheduled based on task and hardware state.

A useful result is not necessarily zero cloud usage. A useful result is **close-to-cloud task quality with materially lower cost, latency, or unnecessary computation**.

## What Loom is not

Loom is not another LLM inference engine.

Loom is not another local-model launcher.

Loom is not intended to replace agent harnesses.

It is an **execution layer for making agent workloads hardware-aware**.

## Status

Very early experimental project. The immediate goal is to establish reproducible baselines on an 8 GB M1 MacBook Air and determine which parts of an agent trajectory are actually worth executing locally.

## Contributing

The project is still being shaped. Issues, experiments, benchmark ideas, and systems-level contributions are welcome as the first runtime is developed.

## License

TBD.
