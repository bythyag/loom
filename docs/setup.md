# macOS development setup

This guide prepares a macOS development machine for Loom's local Ollama and
MLX-LM experiments and optional OpenRouter calls. Loom v0.x targets Apple
Silicon macOS; Linux, Windows, and Intel Macs are not supported targets.

## Before you begin

You need:

- an Apple Silicon Mac running macOS;
- Python 3.11 or newer (`python3 --version` must report 3.11+);
- enough free disk space for a virtual environment, model weights, and results;
- an OpenRouter account only if you intend to run the cloud backend.

Model weights dominate disk use. Allow roughly 2-5 GB for a quantized 3B-4B
model and 5-10 GB for a quantized 7B-8B model. MLX model snapshots can be
larger than quantized Ollama models, and temporary download files may briefly
increase usage. Keep at least 15 GB free for one small Ollama model, one MLX
model, the Python environment, and benchmark output. Check before downloading:

```sh
df -h .
du -sh ~/.ollama/models ~/.cache/huggingface 2>/dev/null
```

The estimates vary by model and quantization. Confirm the size on the model's
Ollama or Hugging Face page before pulling it.

## 1. Install Python and uv

Install Python 3.11+ with your preferred macOS package manager. For example,
with Homebrew:

```sh
brew install python@3.11
python3.11 --version
```

Install `uv` using its official standalone installer:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
uv --version
```

Alternatively, use Homebrew (`brew install uv`). Review downloaded installation
scripts before running them if required by your security policy.

From a Loom checkout, create the project environment and install development
tools:

```sh
uv venv --python 3.11
uv pip install --python .venv/bin/python -e '.[dev]'
.venv/bin/python -c "import loom; print(loom.__version__)"
```

Activate the environment for an interactive shell with `source .venv/bin/activate`.
The explicit `.venv/bin/...` commands used in this guide also work without
activation.

## 2. Install Ollama

Download the macOS application from [ollama.com/download](https://ollama.com/download),
move it to Applications, and launch it. The application installs or exposes the
`ollama` CLI and runs the local API. Homebrew is also supported:

```sh
brew install --cask ollama
open -a Ollama
```

By default, the API is local at `http://localhost:11434`. Verify the service,
then download and test the model selected for your experiment (replace the
example model if the benchmark specifies another one):

```sh
curl --fail --silent http://localhost:11434/api/version
ollama pull qwen2.5-coder:3b
ollama run qwen2.5-coder:3b 'Reply with exactly: loom ready'
```

Do not set `OLLAMA_HOST` to a public interface for Loom experiments. Ollama's
model library shows the exact download size and available quantizations.

## 3. Install and smoke-test MLX-LM

Install MLX-LM in the project environment:

```sh
uv pip install --python .venv/bin/python mlx-lm
.venv/bin/python -m mlx_lm.generate \
  --model mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit \
  --prompt 'Reply with exactly: loom ready' \
  --max-tokens 12
```

The first generation downloads model weights from Hugging Face and can take
several minutes. Subsequent runs use the local cache.

MLX-LM also includes an **experimental development server**. It is not a
production service and must remain bound to the local machine:

```sh
.venv/bin/python -m mlx_lm.server \
  --model mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit \
  --host 127.0.0.1 \
  --port 8080
```

Never use `--host 0.0.0.0` or expose this unauthenticated development endpoint
to a LAN or the internet. Stop it with Control-C when the experiment finishes.

## 4. Configure OpenRouter (optional)

Cloud experiments require an [OpenRouter account](https://openrouter.ai/), a
positive credit balance, and an API key:

1. Sign in or create an account.
2. Add credit on the Credits page and set any desired account spending limit.
3. Create a key on the Keys page; apply a key credit limit when appropriate.
4. Export it only into the process environment:

```sh
export OPENROUTER_API_KEY='replace-with-your-key'
test -n "$OPENROUTER_API_KEY" && echo 'OpenRouter key is set'
```

Do not paste the real key into configuration, command history, logs, benchmark
results, or commits. A local `.env` file is ignored by Git, but Loom does not
yet promise automatic `.env` loading; export the variable in the shell that
starts Loom. Revoke a key immediately if it is exposed.

## 5. Remove experiment data

List Ollama models before deleting a specific downloaded model:

```sh
ollama list
ollama rm qwen2.5-coder:3b
```

MLX-LM downloads are normally stored in the Hugging Face cache. Inspect the
cache and remove only the intended model repository with Hugging Face's CLI:

```sh
uvx --from huggingface_hub hf cache ls
uvx --from huggingface_hub hf cache rm model/mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit
```

Confirm the repository ID shown by `uvx --from huggingface_hub hf cache ls`;
cache CLI syntax can vary with `huggingface_hub` versions, so use
`uvx --from huggingface_hub hf cache rm --help` before cleanup.
Avoid deleting the entire shared cache because other projects may use it.

Loom-generated local outputs belong in the ignored `benchmark-results/` and
`artifacts/` directories. Inspect them, then remove individual experiment
directories rather than broad paths:

```sh
du -sh benchmark-results/* artifacts/* 2>/dev/null
rm -r benchmark-results/EXPERIMENT_ID artifacts/EXPERIMENT_ID
```

Replace `EXPERIMENT_ID` with an exact directory name you have inspected. To
remove only the project environment, run `rm -r .venv` from the repository
root. None of these cleanup steps removes OpenRouter usage records; revoke
unused API keys on OpenRouter's Keys page.

## Troubleshooting

- `python3` reports 3.9: invoke the Homebrew interpreter explicitly through
  `uv venv --python 3.11`; macOS's system Python is unsupported.
- `ollama: command not found`: launch the Ollama app once, or reinstall the
  Homebrew cask, then open a new terminal.
- the Ollama version request fails: launch Ollama and retry the local endpoint.
- MLX reports an architecture error: confirm the machine is Apple Silicon with
  `uname -m` (expected: `arm64`).
- a model download fails: check `df -h .`, confirm the model identifier, and
  verify access to Ollama or Hugging Face.

Official references: [uv installation](https://docs.astral.sh/uv/getting-started/installation/),
[Ollama macOS documentation](https://docs.ollama.com/macos),
[MLX-LM documentation](https://github.com/ml-explore/mlx-lm), and
[OpenRouter API keys](https://openrouter.ai/docs/api_reference/authentication).
