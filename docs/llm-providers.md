# LLM Provider Configuration

app-classifier ships with 5 stdlib-only adapters. Pick whichever fits — they all satisfy the same `LLMProviderProtocol` and the existing `LLMProvider` Callable contract.

## OpenAI

```python
from app_classifier import OpenAIProvider, classify_smart
provider = OpenAIProvider(api_key="sk-...", model="gpt-4o-mini")
result = classify_smart("./my-repo", llm_provider=provider)
```

**Env-var setup:**
```bash
export APP_CLASSIFIER_LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
```

**JSON config:**
```json
{
  "default": "openai",
  "providers": {
    "openai": {
      "type": "openai",
      "api_key": "${OPENAI_API_KEY}",
      "model": "gpt-4o-mini"
    }
  }
}
```

---

## Anthropic

```python
from app_classifier import AnthropicProvider, classify_smart
provider = AnthropicProvider(api_key="sk-ant-...", model="claude-haiku-4-5-20251001")
result = classify_smart("./my-repo", llm_provider=provider)
```

**Env-var setup:**
```bash
export APP_CLASSIFIER_LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

---

## OpenRouter

OpenRouter proxies many models behind one key. Model names take the `provider/model` form.

```python
from app_classifier import OpenRouterProvider, classify_smart
provider = OpenRouterProvider(
    api_key="sk-or-...",
    model="anthropic/claude-haiku-4-5-20251001",
    app_name="my-tool",
    app_url="https://github.com/me/my-tool",
)
result = classify_smart("./my-repo", llm_provider=provider)
```

---

## Ollama (local)

```python
from app_classifier import OllamaProvider, classify_smart
provider = OllamaProvider(host="http://localhost:11434", model="llama3.2")
result = classify_smart("./my-repo", llm_provider=provider)
```

**Env-var setup:**
```bash
export APP_CLASSIFIER_LLM_PROVIDER=ollama
export OLLAMA_HOST=http://localhost:11434
```

**Prereqs:** Install Ollama, then `ollama pull llama3.2`.

---

## OpenAI-compatible servers

One adapter covers LM Studio, vLLM, llama.cpp server, Groq, Together, Fireworks, DeepSeek, Mistral, Perplexity — anything that implements `/v1/chat/completions`.

### LM Studio

```python
from app_classifier import OpenAICompatProvider, classify_smart
provider = OpenAICompatProvider(
    base_url="http://localhost:1234/v1",
    model="llama-3.2-3b-instruct",
    api_key=None,  # LM Studio default has no auth
)
result = classify_smart("./my-repo", llm_provider=provider)
```

### vLLM

```python
provider = OpenAICompatProvider(
    base_url="http://localhost:8000/v1",
    model="meta-llama/Llama-3.1-8B-Instruct",
    api_key="EMPTY",
)
```

### llama.cpp server

```bash
./server -m llama-3.2-3b.gguf -c 4096 --port 8080
```

```python
provider = OpenAICompatProvider(
    base_url="http://localhost:8080/v1",
    model="llama-3.2-3b",
    api_key=None,
)
```

### Groq

```python
provider = OpenAICompatProvider(
    base_url="https://api.groq.com/openai/v1",
    api_key="gsk_...",
    model="llama-3.3-70b-versatile",
)
```

### Together

```python
provider = OpenAICompatProvider(
    base_url="https://api.together.xyz/v1",
    api_key="...",
    model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
)
```

---

## Multi-provider configuration

```json
{
  "default": "anthropic",
  "providers": {
    "anthropic": {"type": "anthropic", "api_key": "${ANTHROPIC_API_KEY}", "model": "claude-haiku-4-5-20251001"},
    "groq":      {"type": "openai_compat", "base_url": "https://api.groq.com/openai/v1", "api_key": "${GROQ_API_KEY}", "model": "llama-3.3-70b-versatile"},
    "local":     {"type": "openai_compat", "base_url": "http://localhost:1234/v1", "model": "llama-3.2-3b"}
  }
}
```

Override the default per call:
```python
from app_classifier import load_provider
provider = load_provider(name="groq")
```

---

## Precedence order

When `classify_smart()` resolves a provider it tries, in order:

1. Explicit `llm_provider=` argument
2. `$APP_CLASSIFIER_LLM_PROVIDER` env var
3. `default` field in `~/.app-classifier/providers.json`
4. Autodetect: `ANTHROPIC_API_KEY` → `OPENAI_API_KEY` → `OLLAMA_HOST`
5. `None` — `classify_smart()` returns the rule-based baseline gracefully
