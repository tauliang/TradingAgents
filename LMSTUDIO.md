# LM Studio Support

This document describes the LM Studio provider integration in TradingAgents, including setup, configuration, dynamic model discovery, and how to run the tests.

## What was changed

LM Studio is a first-class provider alongside Ollama, using the same OpenAI-compatible chat completions path. This branch also makes the interactive CLI discover the models currently hosted by LM Studio and add them to the model picker at runtime.

The key implementation changes are:

| File | Change |
|---|---|
| `tradingagents/llm_clients/factory.py` | Added `"lmstudio"` to the OpenAI-compatible provider tuple |
| `tradingagents/llm_clients/openai_client.py` | Added `http://localhost:1234/v1` default URL; `LMSTUDIO_BASE_URL` env-var override |
| `tradingagents/llm_clients/api_key_env.py` | Registered `"lmstudio"` as a no-auth local runtime (`None`) |
| `tradingagents/llm_clients/model_catalog.py` | Added quick and deep model lists with a "Custom model ID" escape hatch |
| `tradingagents/llm_clients/validators.py` | LM Studio accepts any model ID — no catalog validation |
| `cli/utils.py` | Added LM Studio to the provider dropdown; added `confirm_lmstudio_endpoint()`; fetches live model IDs from LM Studio's `/models` endpoint; merges live and static choices without duplicates |
| `cli/main.py` | Calls `confirm_lmstudio_endpoint()` after provider selection; passes the resolved backend URL into quick/deep model selection |
| `tests/test_lmstudio_base_url.py` | Covers endpoint resolution, no-auth behavior, dynamic model fetching, merged model-list de-duplication, and CLI selection behavior |
| `tests/test_api_key_env.py` | Added `"lmstudio"` to the provider coverage assertion |

## Prerequisites

1. Download and install [LM Studio](https://lmstudio.ai).
2. Load a model inside LM Studio.
3. Start the local server: **LM Studio → Local Server → Start Server** (default port: `1234`).

## Configuration

### Default endpoint

LM Studio's server runs at `http://localhost:1234/v1` by default. No configuration is required when using the default.

### Custom endpoint (`LMSTUDIO_BASE_URL`)

To point TradingAgents at a different host or port — for example a remote LM Studio instance or a local proxy — set `LMSTUDIO_BASE_URL` in your environment or `.env` file:

```bash
LMSTUDIO_BASE_URL=http://192.168.1.50:1234/v1
```

The value is read at call time (not import time), so changes take effect without restarting the process.

### No API key required

LM Studio's built-in server does not enforce authentication by default. TradingAgents does not prompt for or require an API key when `lmstudio` is selected.

## Usage

### Interactive CLI

Run the TradingAgents CLI and select **LM Studio** from the provider dropdown:

```bash
python main.py
# Step 6: select "LM Studio"
# The resolved endpoint is printed before model selection
```

The CLI will show the resolved endpoint (and its source — default vs `LMSTUDIO_BASE_URL`) before asking you to pick a model.

### Python API

```python
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = DEFAULT_CONFIG.copy()
config["llm_provider"]   = "lmstudio"
config["quick_think_llm"] = "meta-llama-3.2-3b-instruct"  # model ID from LM Studio
config["deep_think_llm"]  = "meta-llama-3.3-70b-instruct"
# config["backend_url"]  = "http://192.168.1.50:1234/v1"  # optional override

ta = TradingAgentsGraph(config=config)
```

The `backend_url` key in the config overrides `LMSTUDIO_BASE_URL` and the compiled-in default, in that order of precedence.

### Model IDs

When LM Studio is selected in the interactive CLI, TradingAgents now asks the configured LM Studio server for its current model list:

```text
GET <LMSTUDIO_BASE_URL>/models
```

For the default local server, this means:

```text
GET http://localhost:1234/v1/models
```

The CLI reads the OpenAI-compatible response shape:

```json
{
  "data": [
    {"id": "model-id-from-lm-studio"}
  ]
}
```

Those live model IDs are inserted at the top of both the quick-thinking and deep-thinking model dropdowns. The static curated choices remain available as fallbacks, and "Custom model ID" stays at the end.

The merge is intentionally conservative:

- Live model IDs are shown first because they are the models LM Studio can actually serve right now.
- Static model IDs are appended after live IDs so users still have helpful examples if LM Studio is not running or the endpoint cannot be reached.
- Duplicate values are removed across the combined live and static lists.
- Duplicate live IDs returned by the server are ignored.
- Empty or malformed model entries are ignored.
- Results are cached per LM Studio base URL for the current CLI process, so selecting quick and deep models does not make redundant `/models` requests.
- If the fetch fails, the CLI prints a yellow warning and falls back to the static catalog plus "Custom model ID".

LM Studio does not label models as "quick" or "deep", so the same live model IDs are offered in both dropdowns. The user still decides which hosted model should fill each TradingAgents role.

**The selected model ID must match exactly what LM Studio reports in its server tab** — check the "Model identifier" shown there, pick it from the dynamic dropdown, or use "Custom model ID" to type it directly.

Typical format: `meta-llama-3.3-70b-instruct`, `qwen2.5-7b-instruct`, `phi-4-mini-instruct`.

### Example CLI flow

```text
Step 6: LLM Provider
  Select "LM Studio"

TradingAgents prints:
  Using LM Studio at http://localhost:1234/v1

Step 7: Thinking Agents
  Quick-thinking dropdown:
    model-id-currently-hosted-by-lm-studio
    ...curated fallback choices...
    Custom model ID

  Deep-thinking dropdown:
    model-id-currently-hosted-by-lm-studio
    ...curated fallback choices...
    Custom model ID
```

## Running the tests

### Install dependencies

```bash
# With uv (recommended — installs the project + all deps including questionary)
uv sync

# Or with pip
pip install -e ".[dev]"
# If there is no [dev] extra, install from requirements directly:
pip install -r requirements.txt
```

### Run the LM Studio tests

```bash
# All LM Studio tests
uv run pytest tests/test_lmstudio_base_url.py -v

# Or without uv
python -m pytest tests/test_lmstudio_base_url.py -v
```

### Run all provider-related tests together

```bash
uv run pytest tests/test_lmstudio_base_url.py \
              tests/test_ollama_base_url.py \
              tests/test_api_key_env.py \
              tests/test_model_validation.py -v
```

### Run the full test suite

```bash
uv run pytest
```

### Expected results

`tests/test_lmstudio_base_url.py` contains 24 tests. They do not require a live LM Studio server; dynamic model discovery is tested with mocked HTTP responses.

## Test coverage

`tests/test_lmstudio_base_url.py` covers:

| Area | Tests |
|---|---|
| `_resolve_provider_base_url` | Default URL, env-var override, call-time evaluation, no cross-provider leakage, Ollama env does not affect LM Studio |
| `OpenAIClient.get_llm()` | Picks up `LMSTUDIO_BASE_URL`; explicit `base_url` wins over env |
| CLI dropdown | Reflects `LMSTUDIO_BASE_URL`; falls back to default when unset |
| `confirm_lmstudio_endpoint` | Shows default, marks env origin, warns on missing scheme, warns on non-default remote port, quiet for localhost |
| Model catalog | No `(local)` labels; `"custom"` option present and last |
| Dynamic model discovery | Calls `<base_url>/models`; parses OpenAI-compatible responses; filters empty or malformed entries; removes duplicate live IDs |
| Merged model choices | Prepends live models to static choices; removes duplicate live/static values; keeps `"custom"` last and unique for quick and deep lists |
| `api_key_env` | `get_api_key_env("lmstudio")` returns `None` |
| `validators` | Any model ID accepted |
| Factory routing | `create_llm_client(provider="lmstudio")` returns an `OpenAIClient` |
