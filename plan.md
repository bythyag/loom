# Loom v0.1 Release Plan

This document is the execution checklist and release contract for Loom v0.1. It
complements the project thesis in `AGENT.md`: `AGENT.md` explains why Loom exists,
while this file defines what must be built, measured, tested, and published for the
first release.

## Release Outcome

Loom v0.1 is a macOS and Apple-Silicon research prototype. It must demonstrate a
repository agent that can inspect files, edit code, run explicitly allowed tests,
and route model operations among Ollama, MLX, and a pinned OpenRouter cloud model.

The release succeeds only when all of the following are true:

- [ ] Loom achieves at least 90% of the cloud-only baseline's task success rate.
- [ ] Loom uses at least 50% fewer cloud tokens than the cloud-only baseline.
- [ ] The complete official OpenRouter benchmark campaign costs no more than US$10.
- [ ] The setup and benchmark are reproduced on the reference M1 MacBook Air with
      8 GB unified memory.
- [ ] Required tests, documentation, benchmark artifacts, and release checks pass.

The primary calculations are:

```text
quality_ratio = loom_pass_rate / cloud_only_pass_rate
cloud_token_reduction = 1 - (loom_cloud_tokens / cloud_only_cloud_tokens)
```

## Scope

### Required for v0.1

- [ ] Support macOS on Apple Silicon, with the M1/8 GB machine as the reference.
- [ ] Require Python 3.11 or newer.
- [ ] Provide a CLI for environment checks, individual agent runs, benchmarks,
      and reports.
- [ ] Support repository listing, search, file reading, patch application, and
      allowlisted test execution.
- [ ] Implement Ollama, MLX-LM, and OpenRouter runtime adapters.
- [ ] Implement deterministic operation classification and rule-based routing.
- [ ] Observe memory pressure and swap before and during model operations.
- [ ] Persist versioned JSONL traces and machine- and human-readable summaries.
- [ ] Ship a frozen, deterministic benchmark suite for repository tasks.
- [ ] License the project under Apache-2.0.

### Explicitly deferred

- Linux and Windows support.
- A stable public library API for third-party integrations.
- Learned routing policies.
- Full model-residency and eviction management.
- Persistent KV-cache, prefix-cache, and semantic-cache implementations.
- Concurrent multi-model execution.
- Mandatory energy measurement.
- Production-grade isolation, multi-user operation, or execution of untrusted
  repositories outside disposable benchmark copies.

## Milestone 0: Project and Release Foundations

### Repository setup

- [ ] Add an Apache-2.0 `LICENSE` file and replace the `TBD` license metadata in
      `pyproject.toml` and the README.
- [ ] Use `uv` to create and manage `.venv` and commit a dependency lock file.
- [ ] Keep `requires-python = ">=3.11"` and add a preflight error for older Python
      versions; the reference machine's system Python 3.9 is not supported.
- [ ] Define core dependencies for the CLI, typed configuration, HTTP requests,
      structured telemetry, and reporting.
- [ ] Put Ollama and MLX dependencies in independent optional dependency groups so
      either local adapter can be installed and tested separately.
- [ ] Keep developer tools in a development dependency group, including pytest,
      Ruff, build tooling, and coverage support.
- [ ] Add an example configuration containing no secrets.
- [ ] Document `OPENROUTER_API_KEY`; load it only from the process environment or
      an ignored local environment file.
- [ ] Ensure models, benchmark results, traces, credentials, and local environment
      files remain ignored unless deliberately published as sanitized artifacts.

### Required setup documentation

- [x] Document installing Python 3.11+, `uv`, and the project environment.
- [x] Document the Ollama macOS application/CLI installation and its default local
      API at `http://localhost:11434`.
- [x] Document MLX-LM installation and a minimal generation smoke test.
- [x] Document OpenRouter account, credit, and API-key setup.
- [x] Document expected model storage and free-disk requirements before downloads.
- [x] Document how to remove downloaded experimental models and generated results.
- [x] Keep any MLX HTTP server bound to localhost and identify it as an
      experimental development interface rather than a production service.

### Environment preflight

Implement `loom doctor` and require it to report:

- [ ] macOS version, architecture, processor identity, and physical memory.
- [ ] Python and Loom versions.
- [ ] Installed adapter and package versions.
- [ ] Free disk space and configured model/result locations.
- [ ] Ollama service reachability, server version, and required model presence.
- [ ] MLX importability and required model presence.
- [ ] OpenRouter credential presence without printing the secret.
- [ ] Availability of `memory_pressure`, `vm_stat`, `sysctl`, and optional
      `powermetrics`.
- [ ] A nonzero exit status and actionable messages when required checks fail.

Exit evidence:

- [ ] A clean setup log from the reference machine.
- [ ] `loom doctor` output with secrets and user-specific paths sanitized.
- [ ] A successful smoke inference through each installed backend.

## Milestone 1: Core Contracts and Configuration

Define typed, backend-neutral contracts before implementing the full agent loop.

### Core types

- [ ] `Operation`: operation ID, task category, context references, tool needs,
      estimated difficulty, privacy requirement, and minimum quality.
- [ ] `ModelRequest`: messages, tool schemas, generation limits, sampling settings,
      and correlation identifiers.
- [ ] `ModelResponse`: content, normalized tool calls, finish reason, token usage,
      timing, model/backend identity, and structured error information.
- [ ] `ToolCall` and `ToolResult`: validated arguments, output, exit status,
      duration, truncation metadata, and error category.
- [ ] `HardwareSnapshot`: timestamp, memory-pressure state, free/active/wired/
      compressed memory, swap counters, and CPU load.
- [ ] `RouteDecision`: selected backend/model, matched rule, candidate alternatives,
      rejection reasons, and escalation condition.
- [ ] `TraceEvent`: schema version, run/task/operation IDs, timestamps, routing,
      telemetry, usage, retries, outcome, and artifact references.

### Configuration

- [ ] Define one validated project configuration for backend endpoints, model IDs,
      routing thresholds, context/output limits, timeouts, retry limits, maximum
      agent steps, memory limits, tool allowlists, telemetry, and budget controls.
- [ ] Establish precedence: CLI flags override the selected configuration file;
      secrets come only from environment variables.
- [ ] Reject unknown or invalid safety-critical options.
- [ ] Record the resolved, sanitized configuration in every run manifest.
- [ ] Add a schema version to configuration and trace formats.

### Adapter contract

- [ ] Use one asynchronous adapter protocol for streamed text, tool calls, usage,
      timing, completion, cancellation, and errors.
- [ ] Normalize backend-specific finish reasons and usage data without discarding
      the original raw fields.
- [ ] Record whether token and timing values are measured, backend-reported, or
      estimated.
- [ ] Require explicit model identifiers; official runs must not use moving
      `latest`, automatic-model, or automatic-provider aliases.

Exit evidence:

- [ ] Contract and configuration unit tests pass.
- [ ] Example configurations validate without network access.
- [ ] Serialized events round-trip without loss of required data.

## Milestone 2: Safe Repository Agent Harness

### CLI

Provide these workflows:

```text
loom doctor
loom agent --repo PATH --task TEXT --mode cloud|ollama|mlx|loom
loom benchmark --suite v0.1 --mode MODE --repeat N
loom report RUN_DIRECTORY
```

- [ ] Commands return meaningful exit codes and concise error messages.
- [ ] `--help` documents side effects, required services, and credential use.
- [ ] Each run prints its run ID and output directory.

### Repository tools

- [ ] Implement bounded file listing.
- [ ] Implement text search with result and byte limits.
- [ ] Implement file reading with path, line, and byte limits.
- [ ] Implement patch application with a previewable diff.
- [ ] Execute tests from command arrays selected from a fixture-specific allowlist.
- [ ] Resolve and validate paths before every operation.
- [ ] Reject absolute paths, traversal outside the repository, and symlinks that
      escape the repository root.
- [ ] Apply command timeouts, output limits, and process cleanup.
- [ ] Run editing benchmarks only in fresh disposable copies of fixtures.
- [ ] Preserve the final diff and test output as task artifacts.

### Agent loop

- [ ] Convert the user task into an initial operation.
- [ ] Request a route, invoke the selected model, validate tool calls, run tools,
      and append results until completion or a hard limit.
- [ ] Enforce maximum steps, retries, context size, generated tokens, time, and
      cloud spend.
- [ ] Escalate only when a recorded routing rule permits it.
- [ ] Stop safely on malformed calls, repeated no-progress actions, budget
      exhaustion, timeout, or memory danger.
- [ ] Produce a final answer, final patch where relevant, task result, and trace.

Exit evidence:

- [ ] End-to-end read-only research task completes against a fixture.
- [ ] End-to-end edit-and-test task completes in a disposable fixture copy.
- [ ] Unsafe paths and commands are rejected in automated tests.

## Milestone 3: Runtime Adapters

### Ollama

- [ ] Call the local chat API with streaming enabled for time-to-first-token data.
- [ ] Normalize native tool calls and structured errors.
- [ ] Capture total duration, load duration, prompt evaluation count/duration, and
      generation count/duration where Ollama supplies them.
- [ ] Expose model keep-alive as an experiment-controlled option.
- [ ] Distinguish cold-load, warm, missing-model, and unavailable-service cases.

### MLX-LM

- [ ] Integrate MLX-LM through a controlled local adapter.
- [ ] Measure load, prefill, time to first token, generation, and total duration.
- [ ] Capture exact Hugging Face repository, revision, quantization, and local
      artifact identity.
- [ ] Release model memory between experiments when the run protocol requires a
      cold start.
- [ ] Normalize tool-call output or fail with a classified unsupported-output error.

### OpenRouter

- [ ] Use the OpenRouter API with one explicitly pinned model and provider route.
- [ ] Support normalized tool calling without using OpenRouter-hosted tools.
- [ ] Capture prompt, completion, reasoning, and cached token fields where present.
- [ ] Use returned cost data for budget accounting.
- [ ] Classify authentication, rate-limit, provider, timeout, malformed-response,
      and context-limit failures.
- [ ] Disable provider fallback for official benchmark reproducibility.

### Budget enforcement

- [ ] Estimate the official campaign before it starts and refuse a projection over
      US$8, leaving US$2 contingency.
- [ ] Persist cost after every cloud response.
- [ ] Warn at US$8, prevent new nonessential runs at US$9, and hard-stop before
      total official campaign spending can exceed US$10.
- [ ] Make exploratory and official campaign ledgers separate and explicit.

Exit evidence:

- [ ] Each adapter passes the common contract tests.
- [ ] Each installed backend completes the same tool-capable smoke task.
- [ ] Budget tests demonstrate warning, refusal, and hard-stop behavior.

## Milestone 4: Hardware Telemetry and Routing

### Hardware profiler

- [ ] Sample `memory_pressure`, `vm_stat`, and process metrics before, during, and
      after each operation.
- [ ] Derive memory-pressure state and swap deltas from documented raw fields.
- [ ] Preserve raw readings alongside derived values.
- [ ] Capture CPU usage and process resident memory where available.
- [ ] Make sampling frequency configurable and account for profiler overhead.
- [ ] Treat thermal and energy information as optional metadata.
- [ ] Never require passwordless `sudo`; privileged `powermetrics` collection must
      be a separate, explicitly initiated experiment.

### Operation classifier

- [ ] Classify repository navigation, retrieval, explanation, single-file edit,
      multi-file edit, and test-failure diagnosis operations.
- [ ] Start with deterministic rules based on requested action, context size,
      previous failures, and tool requirements.
- [ ] Record rule matches and classification confidence/reasoning.
- [ ] Provide an explicit unknown/high-risk category that defaults to cloud.

### Router

- [ ] Consider task class, estimated difficulty, privacy requirement, context size,
      local model capability, backend availability, model warmth, memory pressure,
      swap activity, retry history, latency, and remaining cloud budget.
- [ ] Route easy, supported operations locally when resource gates pass.
- [ ] Prefer cloud when local execution would violate memory limits or prior local
      evidence predicts inadequate quality.
- [ ] Escalate after a classified local failure or failed verification, within the
      retry and budget limits.
- [ ] Persist every route and rejected alternative for later analysis.
- [ ] Keep all v0.1 policies deterministic and configuration-driven.

Exit evidence:

- [ ] Recorded telemetry parses consistently on the reference machine.
- [ ] Synthetic state tests cover normal, unavailable-backend, high-pressure,
      swapping, and exhausted-budget routing.
- [ ] The same operation and state produce the same route decision.

## Milestone 5: Frozen Benchmark Suite

Create 18 versioned tasks, three for each category:

- [ ] Repository navigation.
- [ ] Targeted file or symbol retrieval.
- [ ] Code explanation.
- [ ] Single-file edits.
- [ ] Multi-file edits.
- [ ] Test-failure diagnosis.

Every benchmark task must include:

- [ ] A small, frozen fixture repository.
- [ ] A stable task ID, category, prompt, and fixture revision.
- [ ] Allowed tools and exact allowed test commands.
- [ ] Maximum steps, duration, context, output, and cloud budget.
- [ ] Deterministic ground truth, assertions, or required test outcome.
- [ ] A clean reset/copy procedure.
- [ ] A scoring implementation that does not require a paid model judge.
- [ ] Expected artifacts and failure classifications.

### Scoring

- [ ] Score navigation and retrieval using expected paths and symbols.
- [ ] Score explanations using required factual elements derived from the fixture,
      while ignoring prose style.
- [ ] Score edits using focused tests plus explicit diff invariants.
- [ ] Score diagnosis using required cause/location elements and, where suitable,
      a verified fix.
- [ ] Record partial diagnostic data, but calculate the primary success metric from
      pass/fail task outcomes.
- [ ] Never edit scoring criteria after viewing official model results without
      invalidating and rerunning the complete campaign.

Exit evidence:

- [ ] All fixtures reset deterministically.
- [ ] All scoring tests pass without model or network access.
- [ ] The cloud-only mode can attempt all 18 tasks within projected budget.

## Milestone 6: Model Selection and Benchmark Freeze

### Local candidates

- [ ] Screen one model at or below 2B parameters.
- [ ] Screen one 3B-4B coding or instruction model.
- [ ] Use equivalent model families across Ollama and MLX where practical.
- [ ] Record model repository/tag, immutable revision or checksum, quantization,
      artifact size, context limit, prompt template, and license.
- [ ] Treat 7B-8B testing as optional and exclude it from release requirements if
      memory pressure or swap is unacceptable.

### Cloud candidate

- [ ] Select a strong OpenRouter model that supports the required tool-calling
      interface.
- [ ] Confirm its model slug, provider route, pricing, context limit, and tool
      support immediately before benchmark freeze.
- [ ] Reject it if the full official campaign is projected to exceed US$8.
- [ ] Pin the exact slug and provider route in the benchmark manifest.

### Freeze rules

- [ ] Fix prompts, tool descriptions, inference settings, seeds where supported,
      timeouts, routing rules, scoring, task order policy, and model identities.
- [ ] Tag or checksum the fixture and configuration state used for official runs.
- [ ] Require a new campaign ID and complete rerun after any frozen input changes.

Exit evidence:

- [ ] A committed, nonsecret benchmark manifest identifies every frozen input.
- [ ] A dry run passes and its projected cloud spend is no more than US$8.

## Milestone 7: Experiments

Run all experiments on the reference machine and retain configuration, manifests,
raw traces, summaries, and failure records.

### Experiment 1: Machine characterization

- [ ] Record idle memory, compressed memory, swap, CPU load, OS version, storage,
      and background-process policy.
- [ ] Measure telemetry sampler overhead.
- [ ] Record optional thermal/energy data separately when safely available.

### Experiment 2: Backend microbenchmarks

- [ ] Measure cold model load and first request.
- [ ] Measure warm/resident requests.
- [ ] Capture time to first token, prompt throughput, generation throughput, total
      latency, peak memory, and swap delta.
- [ ] Use identical prompts, output limits, and equivalent model variants when
      comparing Ollama with MLX.

### Experiment 3: Local model screening

- [ ] Run representative tasks against the <=2B and 3B-4B candidates.
- [ ] Compare task success, latency, memory pressure, swap, and load cost.
- [ ] Choose the local models using recorded results, not model size alone.

### Experiment 4: Operation classifier

- [ ] Measure classification accuracy across all six task categories.
- [ ] Publish the confusion matrix and unknown/high-risk rate.
- [ ] Inspect how classification errors change routing and task success.

### Experiment 5: Routing comparison

- [ ] Run cloud-only mode.
- [ ] Run Ollama-only mode.
- [ ] Run MLX-only mode.
- [ ] Run Loom hybrid mode.
- [ ] Compare task success, cloud tokens, API cost, latency, local tokens, retries,
      escalations, model loads, memory pressure, and swap.

### Experiment 6: Escalation ablation

- [ ] Compare hybrid routing with escalation enabled and disabled.
- [ ] Report recovered tasks, additional cloud tokens, cost, and latency.

### Experiment 7: Memory-pressure behavior

- [ ] Repeat representative tasks under idle and controlled moderate memory
      pressure.
- [ ] Confirm that resource gates route away from unsafe local work before severe
      swap growth or an out-of-memory failure.
- [ ] Stop rather than manufacture severe or destructive system pressure.

### Experiment 8: Cold versus resident model

- [ ] Compare routes and latency when the selected local model is cold versus
      already loaded.
- [ ] Quantify when model load cost makes cloud execution preferable.

### Experiment 9: Repeatability

- [ ] Run three official repetitions of every benchmark mode.
- [ ] Fix temperature and seed where supported and record unsupported controls.
- [ ] Record task ordering and background-load deviations.
- [ ] Use medians for latency/resource summaries and aggregate pass counts for
      quality.
- [ ] Report infrastructure errors separately; do not silently discard or rerun
      failures.

## Milestone 8: Tests and Quality Gates

### Unit tests

- [ ] Configuration validation and precedence.
- [ ] Operation classification and unknown-task handling.
- [ ] Routing rules, escalation, and deterministic decisions.
- [ ] Token and cost arithmetic, including missing usage fields.
- [ ] Budget warnings and hard stops.
- [ ] Hardware-output parsing with recorded macOS fixtures.
- [ ] Trace serialization, schema versions, and report aggregation.
- [ ] Tool argument and repository-path validation.

### Adapter contract tests

- [ ] Successful streaming text.
- [ ] Single and multiple tool calls.
- [ ] Usage and timing normalization.
- [ ] Cancellation and timeout.
- [ ] Missing model or unavailable service.
- [ ] Authentication and rate limits.
- [ ] Malformed responses and unsupported tool output.
- [ ] Context-limit and generation-limit termination.

Use mocked or recorded responses for default tests. Live tests must be separately
marked and opt-in.

### Safety and failure tests

- [ ] Absolute-path and `..` traversal attempts.
- [ ] Symlink escape attempts.
- [ ] Disallowed and shell-composed commands.
- [ ] Command timeout and child-process cleanup.
- [ ] Oversized tool output and binary files.
- [ ] Repeated no-progress tool calls.
- [ ] Model service interruption during a run.
- [ ] Malformed tool arguments.
- [ ] High memory pressure and growing swap.
- [ ] Exhausted step, token, time, and money budgets.

### Integration and end-to-end tests

- [ ] Ollama smoke test when the optional dependency/service is available.
- [ ] MLX smoke test when the optional dependency/model is available.
- [ ] Explicit, budget-capped OpenRouter smoke test outside normal CI.
- [ ] Read-only repository research trajectory.
- [ ] Successful edit-and-test trajectory.
- [ ] Local failure followed by cloud escalation.
- [ ] Safe termination without a valid execution path.

### Static, packaging, and CI checks

- [ ] `ruff check` passes.
- [ ] `ruff format --check` passes.
- [ ] `pytest` passes without live models or cloud credentials.
- [ ] The source distribution and wheel build successfully.
- [ ] The wheel installs and imports in a clean Python 3.11 environment.
- [ ] CLI help and `loom doctor` run from the installed wheel.
- [ ] CI runs deterministic unit, contract, fixture, and packaging tests.
- [ ] CI does not claim to validate M1/8 GB performance; official performance
      experiments run on the named reference machine.

## Milestone 9: Telemetry and Reports

### Run artifacts

- [ ] Write append-only JSONL events with an explicit schema version.
- [ ] Write a sanitized run manifest containing environment, models, resolved
      configuration, fixture revisions, and experiment identity.
- [ ] Write per-task outcomes and an aggregate JSON/CSV summary.
- [ ] Preserve diffs, allowed test output, and benchmark transcripts.
- [ ] Hash or reference large artifacts rather than duplicating them in events.
- [ ] Clearly label measured, backend-reported, derived, and unavailable metrics.

### Privacy

- [ ] Store full prompts and fixture contents for official frozen benchmarks.
- [ ] For arbitrary user repositories, omit prompt and file contents from traces by
      default and require an explicit opt-in to retain them.
- [ ] Redact API keys, authorization headers, and environment secrets everywhere.
- [ ] Sanitize user-specific absolute paths before publishing artifacts.

### Human-readable report

- [ ] Describe the machine, software, models, configuration, and methodology.
- [ ] Compare cloud-only, Ollama-only, MLX-only, and Loom in one table.
- [ ] Report the two primary release metrics prominently.
- [ ] Include per-category success so aggregate results cannot hide weak areas.
- [ ] Include latency, model load, memory pressure, swap, tokens, cost, retries, and
      escalations.
- [ ] Publish all failures, exclusions, deviations, and unavailable measurements.
- [ ] Separate observed results from interpretations and future hypotheses.

## Final Release Gate

Loom v0.1 may be tagged only after every required item below is satisfied:

- [ ] `loom doctor` passes on the reference M1/8 GB machine.
- [ ] A clean checkout reproduces setup and a smoke benchmark.
- [ ] Required lint, test, packaging, and installation checks pass.
- [ ] All 18 frozen tasks complete in all four official modes for three repetitions,
      or every incomplete task is counted as a failure.
- [ ] `quality_ratio >= 0.90`.
- [ ] `cloud_token_reduction >= 0.50`.
- [ ] Official OpenRouter campaign spend is no more than US$10.
- [ ] Benchmark manifests, raw traces, summaries, and reports are frozen together.
- [ ] Results contain no credentials, private repository content, or identifying
      local paths.
- [ ] README setup/usage, example configuration, benchmark methodology, security
      limitations, known limitations, and changelog are complete.
- [ ] Apache-2.0 license files and package metadata are correct.
- [ ] The package version is changed from `0.1.0.dev0` to `0.1.0` only after all
      other gates pass.
- [ ] The release tag points to the exact commit identified in the benchmark
      manifest.

## Required Release Artifacts

- Source distribution and wheel.
- Apache-2.0 license.
- Setup and usage documentation.
- Sanitized example configuration.
- Frozen benchmark task and model manifest.
- Raw versioned JSONL traces.
- Per-task and aggregate machine-readable results.
- Human-readable benchmark report.
- Known limitations and unsuccessful-experiment record.
- Changelog and signed-off v0.1 release checklist.

## Plan Maintenance Rules

- Check an item only when its evidence exists and is reviewable.
- Link completed milestones to their test output, artifact, report, or commit.
- Record scope changes in this file before implementation diverges from it.
- Any change to frozen benchmark inputs invalidates the official campaign and
  requires a complete rerun under a new campaign ID.
- Model names are intentionally selected and pinned during benchmark freeze because
  availability, pricing, and tool support can change.
- Energy data is useful supporting evidence but is not a v0.1 release gate.
