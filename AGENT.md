# Loom — Project Plan

## Project Thesis

AI agents are usually optimized at the model or prompt level, while the underlying compute environment is treated as a passive execution target. This creates waste. A single agent run may use a frontier cloud model for trivial classification, repeatedly recompute the same long context, load and unload local models unnecessarily, leave CPUs or accelerators idle, and ignore whether a suitable model is already resident in memory.

Loom proposes a different abstraction: treat model choice, hardware choice, context placement, caching, and tool execution as one scheduling problem.

Loom is an open-source hardware-aware execution runtime for AI agents. It dynamically schedules agent operations across local language models, CPUs, GPUs, and cloud models in order to minimize latency, monetary cost, energy use, and memory pressure while maintaining a required level of task quality.

The core research question is:

> How much of a high-quality agent workload can be executed locally, without materially reducing task success, while reducing wall-clock latency, API cost, energy use, and unnecessary computation?

---

## Why This Project

Current agent harnesses generally follow a simple loop:

```text
Model → Tool → Model → Tool → Model
```

The same expensive model is often responsible for planning, search interpretation, summarization, code generation, error diagnosis, and final reasoning. This is convenient, but computationally inefficient.

At the same time, modern personal computers increasingly contain heterogeneous compute: multi-core CPUs, integrated GPUs, unified memory, fast SSDs, and increasingly capable local inference runtimes. Local language models are becoming capable enough to perform a meaningful fraction of routine agent operations. Yet most agent frameworks do not reason about this hardware.

Inference frameworks optimize model execution. Agent frameworks optimize orchestration. Loom aims to connect these layers.

The project should not attempt to replace llama.cpp, MLX, Ollama, or similar inference engines. Instead, it should sit above them and decide what should run, where it should run, and when it should run.

---

## Core Idea

An agent task is decomposed into operations. Each operation is characterized by properties such as task type, estimated difficulty, expected context requirement, latency sensitivity, privacy requirement, required tools, and quality threshold.

The runtime then evaluates candidate execution paths.

For example, a coding agent may execute repository search interpretation using a small local model, repository summarization using a medium local model, embeddings on the GPU, shell commands on the CPU, architectural reasoning using a frontier cloud model, patch generation using a local coding model, and test-failure diagnosis locally before escalating difficult failures to the cloud.

The runtime therefore optimizes the complete agent trajectory rather than optimizing isolated LLM requests.

---

## System Architecture

The proposed system contains six major layers.

### Agent Harness

The harness owns the agent loop, tools, context, state, and task decomposition. It exposes operations to the execution planner instead of binding every operation to one model.

### Execution Planner

The planner decides which execution path should be used for a given operation. Initially, this can be rule-based and benchmark-driven. Later versions can learn policies from previous agent trajectories.

### Hardware Profiler

The profiler continuously exposes macOS and Apple Silicon machine state such as CPU load, GPU utilization, unified-memory availability and pressure, swap activity, current model residency, thermal state where available, and inference throughput.

The initial profiler may use macOS-specific system interfaces rather than cross-platform abstractions.

### Model Runtime Adapters

Adapters provide a unified interface over local and remote inference backends on macOS.

Initial targets should include:

- MLX or llama.cpp optimized for Apple Silicon
- Ollama as a convenient local interface
- one cloud inference provider

Linux- and Windows-specific runtimes are not part of the initial scope.

### Cache and Context Manager

This layer tracks reusable prompt prefixes, agent instructions, repository context, tool definitions, embeddings, model KV cache where supported, and previously computed intermediate representations.

It should expose cache locality to the scheduler.

### Telemetry and Evaluation

Every operation should produce measurements such as:

- time to first token
- tokens per second
- total latency
- peak memory usage
- model load time
- local versus cloud token count
- API cost
- energy estimate where available
- cache hit rate
- task success

---

## Scheduling Objective

The scheduler can be formulated as a constrained optimization problem.

For a candidate execution path `p`:

```text
J(p) = αL + βC + γE + δM + εF
```

where:

- `L` = expected latency
- `C` = monetary cost
- `E` = estimated energy consumption
- `M` = memory pressure or hardware contention
- `F` = probability of task failure

The scheduler minimizes `J` subject to a minimum quality requirement:

```text
Quality(p) ≥ Q_min
```

The first implementation does not need a sophisticated learned optimizer. A practical rule-based scheduler backed by measured profiles is enough to validate whether this abstraction is useful.

---

## Example Execution

Consider the task:

> Find where authentication is implemented in this repository.

The runtime may have three available paths.

**Local 4B model** — very low latency, zero API cost, already resident in memory, high expected success for repository-navigation tasks.

**Local 7B/8B quantized model** — slower and substantially more memory intensive, but potentially higher quality when it fits within the machine's memory budget.

**Cloud frontier model** — highest expected quality but additional network latency and monetary cost.

If the small model has historically achieved sufficient accuracy for repository-location tasks, the planner selects it.

Now consider:

> Design a migration strategy for replacing the current authentication architecture.

The planner may choose the larger local model or immediately route to a frontier model because the task has higher reasoning complexity and the cost of a failed answer is larger.

This distinction is the foundation of Loom.

---

## Agent-Aware Context and KV Caching

Long-running agents repeatedly reuse large portions of their context:

- system prompts
- AGENT.md / CLAUDE.md-style project instructions
- tool definitions
- repository maps
- project instructions
- frequently accessed files
- conversation history

Agent workloads are therefore strong candidates for persistent prefix and KV-cache optimization.

A future Loom context store could model reusable context as segments:

```text
System instructions        → Segment A
Agent/tool specification   → Segment B
Repository map             → Segment C
Frequently used file       → Segment D
Current task context       → Fresh computation
```

When supported by the inference backend, the scheduler should prefer an execution target with relevant cached prefixes rather than selecting models using raw benchmark speed alone.

This introduces the concept of cache locality into agent scheduling.

---

## Model Residency Management

Loading a model can be expensive. On unified-memory machines, repeatedly swapping models may eliminate the latency savings gained by choosing a smaller model.

Loom should therefore eventually manage model residency explicitly.

On the 8 GB M1 target, keeping several substantial models resident simultaneously is usually unrealistic. The scheduler must instead decide which small quantized model, embedding model, and cache state deserve scarce unified memory, when a model should be evicted, and when local execution would create enough memory pressure or swap activity that cloud execution is preferable.

The 8 GB constraint therefore makes residency and memory budgeting first-class scheduling problems.

This begins to make the runtime resemble an operating-system scheduler:

```text
Traditional OS:
Process → Scheduler → CPU

Loom:
Agent operation → Execution planner → Model + CPU/GPU/Cloud
```

---

## Initial Scope: v0.1

The first version should be intentionally narrow.

Loom is **macOS-only** during the initial development phase. Linux and Windows support are explicitly out of scope for v0.x so the project can optimize deeply for one hardware and operating-system environment before considering portability.

### Target Platform

**macOS on a MacBook Air M1 with 8 GB unified memory.**

This constrained machine is the reference hardware for v0.1.

The runtime, profiling layer, scheduling assumptions, local inference integrations, and benchmarks may rely on macOS- and Apple-Silicon-specific behavior. Cross-platform abstractions are not a requirement at this stage.

### Target Agent

A coding or repository-research agent.

### Inference Backends

- MLX or llama.cpp
- Ollama
- one cloud model provider

### Candidate Models

- one small local model
- one 3B–4B local model suitable for routine agent operations
- optionally one 7B–8B quantized coding model for experiments where memory pressure remains acceptable
- one frontier cloud model

### Core Capabilities

- hardware profiling
- model benchmarking
- operation classification
- rule-based local/cloud routing
- 8 GB memory-budget and model-residency awareness
- persistent telemetry
- agent-level benchmark runner

The v0.1 goal is not to build a new inference engine. It is to prove that a useful hybrid agent can operate efficiently on an 8 GB MacBook Air M1 by aggressively choosing what should run locally, what should be cached, what should be evicted, and what should be escalated to the cloud.

---

## Benchmark Design

The project should benchmark complete agent tasks rather than only tokens per second.

Candidate workloads include:

- repository navigation
- file retrieval
- code explanation
- small code edits
- test-failure diagnosis
- multi-file changes
- architecture questions

For each run, capture:

- total wall-clock time
- time to first token
- generation throughput
- model loading time
- peak memory usage
- CPU/GPU utilization
- local tokens generated
- cloud tokens generated
- API cost
- cache hit rate
- number of retries or escalations
- final task success

Three baselines should be compared.

### Cloud-only Agent

Every reasoning step uses the frontier model.

Expected characteristics:

- high success
- high API usage
- moderate latency

### Local-only Agent

Every reasoning step uses the selected local model.

Expected characteristics:

- zero API cost
- lower quality on difficult tasks
- potentially high latency for larger models

### Loom

Each operation is dynamically routed.

A successful early result would be success close to the cloud-only baseline while substantially reducing cloud tokens, cost, or total runtime.

---

## Repository Structure

```text
src/loom/
├── planner/
│   ├── task_classifier.py
│   ├── model_router.py
│   └── execution_optimizer.py
├── hardware/
│   ├── cpu.py
│   ├── gpu.py
│   ├── memory.py
│   └── macos.py
├── runtime/
│   ├── llama_cpp.py
│   ├── mlx.py
│   ├── ollama.py
│   └── cloud.py
├── cache/
│   ├── prefix_cache.py
│   ├── semantic_cache.py
│   └── agent_context.py
├── scheduler/
│   ├── residency.py
│   ├── queue.py
│   └── offload.py
├── harness/
│   ├── tools.py
│   ├── context.py
│   └── agent_loop.py
└── telemetry/
    ├── latency.py
    ├── energy.py
    ├── memory.py
    └── quality.py

benchmarks/
├── tasks/
├── baselines/
├── profiles/
└── results/
```

This structure is directional, not a requirement to create empty modules before functionality exists.

---

## Development Roadmap

### v0.1

macOS/M1 hardware profiling and local/cloud task routing.

### v0.2

Model residency manager and model load/eviction cost awareness.

### v0.3

Persistent prefix and agent-context caching.

### v0.4

Concurrent CPU/GPU execution and improved scheduling.

### v0.5

Backend-aware speculative or accelerated inference experiments.

### v0.6

Multi-device or multi-machine scheduling.

### v0.7

Learned execution planner trained from historical agent trajectories.

Linux and Windows support are not part of the v0.x roadmap unless explicitly reconsidered later.

---

## Longer-Term Learning System

Over time, the runtime should learn from agent execution history.

Examples of useful learned observations:

- Repository search and classification operations almost never require a model larger than 4B.
- A medium local coding model solves most Python traceback diagnosis tasks without escalation.
- Architecture questions have a high retry rate locally and should be routed to a stronger model immediately.
- A particular repository prefix is already cached on one model, making that model faster despite lower raw tokens-per-second throughput.
- A larger local model is worthwhile when it is already resident but not when it must be loaded for a single operation.

The scheduler could eventually become an adaptive policy over model capability, task type, hardware state, and trajectory history.

---

## Open-Source Positioning

Loom should position itself as infrastructure between agent frameworks and inference runtimes.

It is not another agent framework.

It is not another local-model launcher.

It is not another inference engine.

It is a hardware-aware execution layer for agents.

Existing agent frameworks could integrate Loom as an execution backend. Existing inference engines remain responsible for efficient token generation. Loom is responsible for deciding which engine, model, hardware resource, context representation, and execution strategy should be used for each part of an agent workflow.

For the current phase, this execution layer is specifically optimized for macOS and Apple Silicon rather than designed as a portable runtime.

---

## Project Success Criteria

The project becomes valuable if it can demonstrate at least one of the following without materially reducing task success:

- significantly fewer cloud tokens for an agent workload
- lower total wall-clock time than cloud-only or naive local execution
- better utilization of local CPU/GPU resources
- lower model loading and context-recomputation overhead
- higher cache reuse across long-running agent sessions
- a reproducible benchmark showing when local execution is beneficial and when cloud escalation is justified

---

## Working Project Statement

Loom is an open-source hardware-aware execution runtime for AI agents. It dynamically schedules models, context, tools, and computation across local hardware and cloud inference based on task difficulty, hardware state, model residency, cache locality, latency, cost, and expected quality.

The broader hypothesis is simple:

> **Model × Harness × Hardware should be optimized as one system.**

The first milestone is to prove this approach on macOS, specifically an 8 GB M1 MacBook Air: make a real coding agent faster and cheaper while preserving most of the task quality of a frontier-model-only agent.

Portability to Linux or Windows should only be considered after the macOS implementation and benchmarks are mature.
