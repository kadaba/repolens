# app-classifier

**Point it at a repo, get back what it is and how it works — deterministically, with optional LLM lift.**

```python
from app_classifier import classify_smart
result = classify_smart("./my-repo")
print(result.app_category, result.app_category_confidence)
print(result.functional_description)
```

```
e-commerce 0.95
ShopMax is an e-commerce application. Primary functionality: online shopping, internal admin.
The app routes traffic across 12 HTTP endpoints, including authentication and checkout.
```

---

## Why it wins

| Concern | app-classifier | Manual review | ChatGPT paste | GitHub Copilot Chat |
|---|---|---|---|---|
| Deterministic baseline | ✅ pattern-based fingerprints | — | ❌ | ❌ |
| Works offline | ✅ no network needed | ✅ | ❌ | ❌ |
| Zero runtime deps | ✅ stdlib only | ✅ | n/a | n/a |
| Multi-language | ✅ Python, JS/TS, Java, Go, Ruby, PHP, others | ⚠️ | ⚠️ | ⚠️ |
| Structured output | ✅ dataclasses, JSON-serializable | ❌ | ⚠️ free text | ⚠️ free text |
| Programmatic API | ✅ `classify()` / `classify_smart()` / `classify_agentic()` / `map_code()` | ❌ | ❌ | ❌ |
| LLM-pluggable | ✅ 5 adapters (OpenAI / Anthropic / OpenRouter / Ollama / OpenAI-compat) | — | bound to one | bound to one |
| Auditable | ✅ confidence scores + step-by-step trail | ❌ | ❌ | ❌ |

If you've ever inherited a 200-file repo and spent an afternoon working out "wait, what does this thing actually do?" — that's the problem this solves.

---

## Installation

```bash
pip install app-classifier
```

Zero runtime dependencies. The LLM adapters use stdlib `urllib`. If you'd rather use the official SDK clients:

```bash
pip install app-classifier[openai]        # adds openai SDK
pip install app-classifier[anthropic]     # adds anthropic SDK
pip install app-classifier[all]           # both
```

Requires Python 3.10+.

---

## Quick start

### 1. Pure rule-based (no network, no deps, no setup)

```python
from app_classifier import classify
result = classify("./my-repo")
print(result.app_category, result.app_category_confidence)
print(result.functional_description)
print([r.path for r in result.routes[:5]])
```

### 2. Smart — rule-based first, LLM-escalated when uncertain

```python
import os
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-..."
from app_classifier import classify_smart
result = classify_smart("./my-repo")  # auto-detects provider from env
print(result.app_category, result.app_category_confidence)
```

High-confidence repos (≥0.75) return immediately with no LLM call. Only ambiguous ones get the agentic treatment.

### 3. Code mapping for impact analysis (no LLM)

```python
from app_classifier import map_code
cm = map_code("./my-repo")
print("Entry points:", cm.entry_points)
print("If I change src/auth.py:", cm.impact_of("src/auth.py"))
```

`impact_of()` does BFS over the reverse dependency graph with cycle detection. Works across Python, JS/TS, Java, Go, Ruby, PHP at the file level; Python also gets function-level resolution.

---

## Configuration

### Option A: environment variables (simplest)

```bash
export APP_CLASSIFIER_LLM_PROVIDER=anthropic     # picks the provider
export ANTHROPIC_API_KEY=sk-ant-...               # per-provider key
```

`classify_smart()` will autodetect this. The provider name maps to one of: `openai`, `anthropic`, `openrouter`, `ollama`, `openai_compat`.

### Option B: `~/.app-classifier/providers.json`

```json
{
  "default": "anthropic",
  "providers": {
    "anthropic": {
      "type": "anthropic",
      "api_key": "${ANTHROPIC_API_KEY}",
      "model": "claude-haiku-4-5-20251001"
    },
    "local": {
      "type": "openai_compat",
      "base_url": "http://localhost:1234/v1",
      "model": "llama-3.2-3b"
    }
  }
}
```

`${VAR}` placeholders are interpolated from the environment at load time.

### Option C: explicit instantiation

```python
from app_classifier import classify_smart, OpenAIProvider
provider = OpenAIProvider(api_key="sk-...", model="gpt-4o-mini")
result = classify_smart("./my-repo", llm_provider=provider)
```

See the [per-provider guide](https://github.com/kadaba/repolens/blob/main/oss/app-classifier/docs/llm-providers.md) for full quickstarts (Groq, LM Studio, Ollama, vLLM, llama.cpp, Together, Fireworks).

---

## API reference

| Symbol | Module | Purpose |
|---|---|---|
| `classify(repo)` | `app_classifier` | Rule-based, deterministic, no network |
| `classify_smart(repo)` | `app_classifier` | Rule-first; LLM-escalated for low-confidence |
| `classify_smart_async(repo)` | `app_classifier` | Async variant; returns full audit trail |
| `classify_agentic(repo, llm_provider)` | `app_classifier` | LLM tool-loop (low level — `classify_smart` wraps this) |
| `map_code(repo)` | `app_classifier` | Build a `CodeMap` for impact analysis |
| `CodeMap.impact_of(target)` | `app_classifier` | BFS over reverse-dep graph |
| `OpenAIProvider(api_key, model, base_url=None)` | `app_classifier` | OpenAI + any OpenAI-compatible endpoint |
| `AnthropicProvider(api_key, model)` | `app_classifier` | Anthropic Messages API |
| `OpenRouterProvider(api_key, model)` | `app_classifier` | OpenRouter (auto-routed across providers) |
| `OllamaProvider(host, model)` | `app_classifier` | Local Ollama serving |
| `OpenAICompatProvider(base_url, model, api_key=None)` | `app_classifier` | LM Studio / vLLM / llama.cpp / Groq / Together |
| `load_provider(name=None)` | `app_classifier` | Resolve provider from env + config |
| `analyze_hosting_requirements(repo)` | `app_classifier` | Runtime / DB / port / env-var detection |

Full dataclass shapes: `AppDescription`, `RouteEntry`, `DataModel`, `CodeMap`, `FileNode`, `FunctionNode`, `AgentClassificationResult`, `AgentStep`, `SubappClassification`, `HostingReport`, `Signal`.

---

## CLI

```bash
app-classifier ./my-repo                   # human-readable summary
app-classifier ./my-repo --json            # JSON for piping
```

---

## What it can't do (yet)

- Java / JS / Go function-call graph (file-level dep only; v0.6.0+)
- Streaming completion (provider layer always waits for the full response)
- Cost / token caps per call
- Tree-sitter-backed parsing (everything is stdlib + regex right now — fast, but imperfect)

See the [CHANGELOG](https://github.com/kadaba/repolens/blob/main/oss/app-classifier/CHANGELOG.md) for what landed in each release. The [code-mapping guide](https://github.com/kadaba/repolens/blob/main/oss/app-classifier/docs/code-mapping.md) has impact-analysis recipes.

---

## License

MIT. Contributions welcome.
