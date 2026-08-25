# Loom Benchmarks

Loom will evaluate complete agent workloads rather than model throughput in isolation.

The initial reference machine is a MacBook Air M1 with 8 GB unified memory.

Planned baselines:

- cloud-only execution
- local-only execution
- Loom hardware-aware routing

Initial measurements should include total wall-clock time, time to first token, generation throughput, model load time, memory pressure, swap activity where measurable, local/cloud token counts, API cost, retries or escalations, and final task success.

The first benchmark suite will focus on coding and repository-research operations.
