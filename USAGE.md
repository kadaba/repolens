# Using `app-classifier` — Complete Guide

> Point it at a repo, get back **"this is an e-commerce app that does X"**.
>
> This guide covers: how to use it, where it shines, when to skip it, and the honest answer to "is this agentic?".

---

## Table of contents

1. [Installation](#installation)
2. [The 5-second tour](#the-5-second-tour)
3. [Programmatic API — every method explained](#programmatic-api)
4. [CLI usage](#cli-usage)
5. [LLM enrichment — bring your own provider](#llm-enrichment)
6. [Where this is helpful — 12 real-world use cases](#where-helpful)
7. [Where this is NOT the right tool](#where-not-helpful)
8. [Is this agentic?](#is-this-agentic)
9. [Performance characteristics](#performance)
10. [Extending it](#extending)
11. [FAQ](#faq)

---

<a name="installation"></a>
## 1. Installation

```bash
pip install app-classifier
```

That's it. **Zero runtime dependencies.** Pure Python stdlib. Works on Python 3.10+.

Optional development extras:

```bash
pip install "app-classifier[test]"   # pytest
pip install "app-classifier[dev]"    # ruff + mypy
```

For the LLM-polish path, install your provider SDK separately (we never pin one):

```bash
pip install openai      # if using OpenAI
pip install anthropic   # if using Anthropic
# ... or nothing if you don't need LLM polish
```

---

<a name="the-5-second-tour"></a>
## 2. The 5-second tour

```python
from app_classifier import classify

result = classify("./my-repo")

print(result.app_category)              # 'e-commerce'
print(result.app_category_confidence)   # 0.78
print(result.functional_description)
# 'my-repo is an e-commerce application. Primary functionality: online
#  shopping. It models entities like Cart, Order, Product, User serving
#  authenticated users.'
```

Or from the shell:

```bash
$ app-classifier ./my-repo
=== my-repo ===

Category:    e-commerce (78% confidence)
Runtime:     python 3.11
Framework:   FastAPI
Deploys as:  ASGI server (uvicorn / hypercorn / daphne)
Databases:   PostgreSQL
Features:    online shopping, messaging
📋 Summary:  my-repo · python 3.11 · FastAPI · 23 routes · 5 models · DB: PostgreSQL
📝 What it does: ...
```

---

<a name="programmatic-api"></a>
## 3. Programmatic API — every method explained

### `classify(repo_root: str) -> AppDescription`

The main entry point. **Sync. No network. No LLM.** Returns a fully structured `AppDescription` object.

```python
from app_classifier import classify

result = classify("./my-repo")
```

**What you get back** — every field on `AppDescription`:

| Field | Type | Example |
|---|---|---|
| `name` | `str` | `"my-repo"` (the directory name) |
| `app_category` | `str` | `"e-commerce"`, `"blog / content platform"`, `"admin panel / dashboard"`, `"REST API service"`, `"authentication / SSO"`, `"social network"`, `"file / document management"`, `"scheduling / booking"`, `"messaging / notification"`, or `"unknown"` |
| `app_category_confidence` | `float` | `0.0`–`0.95` |
| `detected_features` | `List[str]` | `["online shopping", "messaging"]` |
| `functional_description` | `str` | 2-3 sentence prose answer to "what does this app do?" |
| `runtime` | `Dict[str, Any]` | `{"language": "python", "version": "3.11"}` |
| `framework` | `Optional[str]` | `"FastAPI"`, `"Django"`, `"Spring Boot"`, `"Express"`, etc. |
| `deployment_target` | `Optional[str]` | `"ASGI server (uvicorn / hypercorn / daphne)"` |
| `routes` | `List[RouteEntry]` | `[RouteEntry(path="/users", method="GET", handler="list_users", source="...")]` |
| `data_models` | `List[DataModel]` | `[DataModel(name="User", file="...", fields_hint=["id", "email"], framework="JPA")]` |
| `databases` | `List[str]` | `["PostgreSQL", "Redis"]` |
| `caches_queues` | `List[str]` | `["Redis", "Celery"]` |
| `one_line_summary` | `str` | `"my-repo · python 3.11 · FastAPI · 23 routes · 5 models"` |
| `architecture_summary` | `str` | Multi-line paragraph |
| `purpose` | `str` | First meaningful paragraph from README, or `""` |
| `notable_files` | `List[Dict]` | `[{"name": "README.md", "source": "..."}]` |

### `classify_async(repo_root, llm_provider=None) -> AppDescription`

Same as `classify`, but **async** and supports optional LLM enrichment.

```python
import asyncio
from app_classifier import classify_async

# Without LLM — identical to sync classify()
result = asyncio.run(classify_async("./my-repo"))

# With LLM — polishes functional_description
async def my_provider(prompt, max_tokens=400, temperature=0.2):
    # ... call your LLM ...
    return "polished description text"

result = asyncio.run(classify_async("./my-repo", llm_provider=my_provider))
print(result.functional_description)  # Now LLM-polished
```

If the LLM returns nothing useful (or raises, or trips the hallucination guard), the deterministic description stays. **No silent degradation.**

### `analyze_hosting_requirements(repo_root: str) -> HostingReport`

Skip the classifier — get only deployment data. Useful if you don't care about app category, just want to know "how do I deploy this?".

```python
from app_classifier import analyze_hosting_requirements

report = analyze_hosting_requirements("./my-repo")
print(report.runtime)         # {'language': 'python', 'version': '3.11'}
print(report.web_server)      # {'framework': 'FastAPI', 'deployment_target': '...'}
print(report.databases)       # [{'name': 'PostgreSQL', ...}, ...]
print(report.ports)           # [{'port': 8000, 'source': 'Dockerfile', ...}]
print(report.env_vars_required)
print(report.web_server_vulnerabilities)  # CVEs on the container base image
```

`HostingReport` includes every signal source — useful for auditing the analyzer's reasoning:

```python
for signal in report.signals:
    print(f"{signal.source}: {signal.snippet} (confidence: {signal.confidence})")
```

### `to_dict()` — JSON serialization

Every result object has a `.to_dict()` method that returns a JSON-serializable dict:

```python
import json

result = classify("./my-repo")
payload = result.to_dict()
print(json.dumps(payload, indent=2))
```

---

<a name="cli-usage"></a>
## 4. CLI usage

```bash
# Human-readable (default)
app-classifier ./my-repo

# JSON for piping
app-classifier ./my-repo --json > result.json

# JSON with full signal trail
app-classifier ./my-repo --json --include-signals

# Version
app-classifier --version
```

**Exit codes:**
- `0` — success
- `2` — bad argument (e.g., path not a directory)
- `1` — unexpected error

### Pipe to `jq`

```bash
# Get just the category
app-classifier ./my-repo --json | jq '.app_category'

# Get all detected features as comma-separated
app-classifier ./my-repo --json | jq -r '.detected_features | join(", ")'

# Get all routes grouped by method
app-classifier ./my-repo --json | jq '.routes | group_by(.method) | map({(.[0].method): map(.path)}) | add'
```

### Batch-classify a directory of repos

```bash
for repo in /path/to/repos/*/; do
  echo "=== $(basename "$repo") ==="
  app-classifier "$repo" --json | jq -c '{name, app_category, confidence: .app_category_confidence}'
done
```

---

<a name="llm-enrichment"></a>
## 5. LLM enrichment — bring your own provider

The LLM step is **provider-agnostic**. You supply an async callable; we never pin an SDK. Example shims for the most common providers:

### OpenAI

```python
import os
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

async def openai_provider(prompt, max_tokens=400, temperature=0.2):
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content
```

### Anthropic Claude

```python
import os
from anthropic import AsyncAnthropic

client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

async def anthropic_provider(prompt, max_tokens=400, temperature=0.2):
    resp = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text
```

### AWS Bedrock

```python
import boto3
import json
import asyncio

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

async def bedrock_provider(prompt, max_tokens=400, temperature=0.2):
    # boto3 is sync — run it in an executor
    loop = asyncio.get_event_loop()
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens, "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    })
    resp = await loop.run_in_executor(
        None,
        lambda: bedrock.invoke_model(
            modelId="anthropic.claude-haiku-4-5-20251001-v1:0",
            body=body,
        ),
    )
    payload = json.loads(resp["body"].read())
    return payload["content"][0]["text"]
```

### Local Ollama (free, no API keys)

```python
import httpx

async def ollama_provider(prompt, max_tokens=400, temperature=0.2):
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post("http://localhost:11434/api/generate", json={
            "model": "llama3", "prompt": prompt, "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature},
        })
        return r.json().get("response")
```

### Local llama.cpp (via OpenAI-compatible server)

```python
from openai import AsyncOpenAI

# llama.cpp's --api-server speaks OpenAI's protocol
local = AsyncOpenAI(base_url="http://localhost:8080/v1", api_key="not-needed")

async def llama_cpp_provider(prompt, max_tokens=400, temperature=0.2):
    resp = await local.chat.completions.create(
        model="local",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens, temperature=temperature,
    )
    return resp.choices[0].message.content
```

### What the prompt looks like

If you want to inspect / customize what we feed the LLM, use `_build_llm_prompt`:

```python
from app_classifier.classifier import _build_llm_prompt
from app_classifier import classify

result = classify("./my-repo")
prompt = _build_llm_prompt(result)
print(prompt)
```

This prints the full structural-context block we send. Useful if you want to wrap it with your own system prompt, run it through your own RAG pipeline, etc.

---

<a name="where-helpful"></a>
## 6. Where this is helpful — 12 real-world use cases

### Developer & engineering

**1. Repo onboarding for new engineers.** First day at a new job, you clone 47 microservices. `for repo in repos/*; do app-classifier "$repo" --json | jq '{name, app_category, summary: .one_line_summary}'; done` → instantly know what each service does. Beats reading 47 stale READMEs.

**2. Internal service catalog.** Backstage and similar service catalogs need a "type" field that's almost always stale. Run app-classifier on every repo nightly via CI; auto-update the catalog. Now your discovery actually reflects code state.

**3. Pre-onboarding briefing for AI coding assistants.** Before pointing Cursor / Claude Code / Continue at an unfamiliar repo, run app-classifier and pre-pend the description to your prompt. The assistant immediately knows it's "an e-commerce backend with FastAPI + PostgreSQL + Stripe integration" — drastically improves answer quality.

### Documentation

**4. README generators / boilerplate.** Use the output as input to an LLM that drafts a README skeleton. Sections like "Stack", "Deployment", "API surface", "Data model" become auto-fillable.

**5. Auto-updating architecture docs.** A nightly job runs the classifier, writes a markdown report to a `docs/architecture-auto.md` file, opens a PR if anything changed. Architecture diagrams stay honest.

### Security & compliance

**6. Compliance scope identification.** PCI-DSS applies to anything handling payment cards. HIPAA applies to health-data apps. Run the classifier across your fleet; flag any repo classified as "e-commerce" or matching health-related fingerprints — instant compliance scope.

**7. Threat-modeling prioritization.** A pen-test team has 200 repos and 3 weeks. Use the classifier to surface high-risk patterns: "authentication / SSO" + "file / document management" combos are higher-priority than "internal admin dashboards". Use the runtime CVE detection to flag base-image vulns immediately.

**8. Codefixer's own use case.** This is literally how Codefixer's main product surfaces "what does this app do?" to security analysts before they review findings. Without context, a SQL injection finding is just a SQL injection finding. With context ("this is the payment-processing service"), it's an emergency.

### DevOps & platform

**9. Auto-generated deployment manifests.** Detect runtime + framework + ports + env vars → generate a starter k8s deployment, a docker-compose, a Heroku Procfile, a Render `render.yaml`. Codefixer's "Download Deploy Bundle" button uses this pattern.

**10. Migration planning.** "Find all our Express apps so we can migrate them to Hono together." Or "find all Django 3.x apps that need Django 5.x." Run the classifier across the org, filter, action.

**11. Cloud cost attribution.** Group services by category (e-commerce, blog, admin) for cost reporting. A 10-line script does what FinOps tools charge $50k/year for.

### AI & search

**12. Code search ranking.** Give your search results category-aware ranking. A search for "checkout flow" should rank e-commerce repos higher than blog repos even if both have the word "checkout" somewhere.

---

<a name="where-not-helpful"></a>
## 7. Where this is NOT the right tool

Be honest with yourself about the boundaries:

- **Not a security scanner.** It detects runtime CVEs on base images, but doesn't audit application code. For that, use Semgrep, Snyk, or Codefixer.
- **Not a static analyzer.** No control-flow analysis, no taint tracking, no type checking. It reads structure, not semantics.
- **Not a replacement for a human-written README.** Your "what does this do" sentence is structural. If your app is doing something genuinely novel, the README is the only place that captures intent.
- **Not great on monorepos with unrelated apps.** It unifies signals across the whole tree. If you have an e-commerce app and a blog in the same repo, you'll get a confused answer. Workaround: run it per-subdirectory.
- **Not a substitute for `git log` / domain expertise.** It tells you WHAT exists, not WHY it exists or whether it should.
- **Doesn't classify libraries well.** A repo that's a `react-stripe-checkout-component` library will probably classify as e-commerce because of the README. False positive — fix is to feed it only the actual app code.

---

<a name="is-this-agentic"></a>
## 8. Is this agentic?

**Honest answer: no.** Let me break it down.

### What "agentic" typically means

An AI system is "agentic" when it has some combination of:
- **Autonomy** — decides what to do next without being told
- **Multi-step planning** — chains actions toward a goal
- **Tool use** — calls APIs, runs code, reads files dynamically
- **Loop until done** — keeps going until a condition is met
- **Self-correction** — observes outcomes and revises plans

### What app-classifier actually is

**A deterministic analyzer.** Specifically:

| Property | app-classifier |
|---|---|
| Autonomous? | No — runs once, returns once |
| Multi-step plan? | No — fixed pipeline (walk files → extract signals → match patterns → compose result) |
| Tool use? | No — only reads files; no API calls in the core path |
| Loops? | Only the file walker (bounded at 800 files) |
| Self-correction? | No |
| Non-deterministic? | Only if you supply an LLM provider — and even then, the structural extraction is deterministic |

It's the same shape as `grep`, `wc -l`, `tree`, or `pip-audit`. A useful command-line tool that always produces the same output for the same input.

### But it's a perfect TOOL for agents

This is the interesting part. While app-classifier itself isn't agentic, **it's exactly the kind of tool an agent would call** to gather context. Think of it like the calculator an AI math tutor uses — the calculator isn't intelligent, but it makes the tutor smarter.

#### Pattern 1: Tool-use in function calling

Expose it as a tool to your agent:

```python
from app_classifier import classify

TOOLS = [{
    "type": "function",
    "function": {
        "name": "classify_repo",
        "description": "Classify what a repository does. Returns app category, "
                       "framework, databases, routes, data models, and a 2-3 "
                       "sentence functional description. Use this BEFORE making "
                       "changes to an unfamiliar repo.",
        "parameters": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Path to the repo"},
            },
            "required": ["repo_path"],
        },
    },
}]

def execute_tool(name, args):
    if name == "classify_repo":
        return classify(args["repo_path"]).to_dict()
```

Now your agent can call `classify_repo` whenever it lands on an unfamiliar codebase. It gets ground truth about app type before deciding what to do next.

#### Pattern 2: Agent loop wrapper

Build an actual agent ON TOP of it:

```python
async def repo_review_agent(repo_path, llm):
    """An agent that classifies a repo, then plans security-review steps based
    on the classification, then runs them, then composes a report."""

    # Step 1: gather context (this is where app-classifier helps)
    description = classify(repo_path)

    # Step 2: agent plans what to do based on the classification
    plan_prompt = f"""You're reviewing a {description.app_category} app
    ({description.functional_description}). What 3 security checks should
    you run? Return JSON list of check names."""
    plan = await llm(plan_prompt)
    checks = json.loads(plan)

    # Step 3: execute each check (uses other tools)
    findings = []
    for check in checks:
        finding = await run_security_check(check, repo_path)
        findings.append(finding)

    # Step 4: synthesize report
    return await llm(f"Compose a security review report from: {findings}")
```

The loop, the planning, the tool-chaining — THAT's the agent. `app-classifier` is one tool the agent uses, not the agent itself.

#### Pattern 3: LLM-only "agentic" mode (built-in)

If you pass an `llm_provider` to `classify_async`, there's a tiny bit of agentic behavior — the LLM gets structural context and writes prose. But it's still:
- One LLM call (not a loop)
- No tool use by the LLM
- Output post-processed by a hallucination guard

So at best, this is a 1-step "augmented prompt" pattern, not an agent loop.

### Bottom line

- **Is app-classifier itself agentic?** No.
- **Can app-classifier be USED by an agent?** Yes, perfectly. It's exactly the kind of high-value tool agents need.
- **Should you wrap it in an agent?** If you have a multi-step workflow (review → plan → act → verify), yes. The classifier gives the agent grounded context to reason from.

This is the right separation. Determinism and predictability at the analyzer layer; non-determinism at the orchestration layer. Mixing them tends to produce systems that are both unreliable AND inflexible.

---

<a name="performance"></a>
## 9. Performance characteristics

| Metric | Value | Notes |
|---|---|---|
| Time | **<1 second** on a 5K-file repo | Bounded scan: 800 files max |
| Memory | **<50 MB** typical | One pass, no graph construction |
| Network | **0 calls** | CVE manifest is bundled |
| Disk writes | **0** | Pure-read analyzer |
| LLM calls | **0** by default, **1** if you supply a provider | One-shot, no retries |
| Languages supported | Python, Java, JS/TS, Node, Go, Ruby, PHP, Rust | Routes + models for the top 3 |
| Frameworks | Flask / FastAPI / Django / Express / Fastify / NestJS / Next / Spring Boot / Struts / classic Spring | More via PRs |

### Scaling tips

- **Parallel batches**: `multiprocessing.Pool` works fine — no shared state.

  ```python
  from multiprocessing import Pool
  from app_classifier import classify

  with Pool(8) as pool:
      results = pool.map(classify, ["./repo1", "./repo2", ...])
  ```

- **Skip irrelevant trees**: Pre-filter directories before passing to `classify`. The analyzer respects standard `.gitignore`-style skip dirs (`node_modules`, `.venv`, `target`, etc.), but a deeply-nested monorepo can still hit the 800-file cap. Run per-subdirectory if you have many small services in one repo.

- **Cache results**: The classifier is deterministic, so caching by `(repo_path, mtime_of_manifests)` is safe. Useful in CI.

---

<a name="extending"></a>
## 10. Extending it

### Add a new app category

In `src/app_classifier/classifier.py`, find `_CATEGORY_FINGERPRINTS`. Each entry is:

```python
{
    "name": "your category name",
    "feature_label": "human-readable feature tag",
    "signals": [
        (r"distinctive_pattern_1", 3),  # high-weight, very specific
        (r"distinctive_pattern_2", 2),  # medium-weight
        (r"weaker_pattern", 1),         # low-weight, can co-occur
    ],
},
```

The matcher concatenates all routes + model names + README purpose into one haystack and runs each regex against it. Weights stack additively. **Score ≥ 2** is the threshold for "this is a detected feature." Top score wins as the app category.

### Add a new framework / language

Add to `_extract_python_routes`, `_extract_js_routes`, `_extract_java_routes` (in `classifier.py`) or add a new `_extract_<lang>_routes` function and call it from `describe_app`.

For data models, see `_extract_java_entities` and `_extract_python_models`.

For runtime detection, see `_analyze_pom`, `_analyze_pyproject`, `_analyze_package_json` in `hosting.py`.

### Add a runtime CVE

Add an entry to `src/app_classifier/data/web_server_cves.json`. Schema:

```json
{
  "server_name": {
    "latest_stable": "1.25.3",
    "cves": [
      {
        "cve": "CVE-2024-NNNNN",
        "severity": "critical",
        "summary": "short description",
        "fix": "1.24.0",
        "affects_max_version": "1.23.4"
      }
    ]
  }
}
```

### Run the tests

```bash
pytest                  # 24 tests
pytest -v               # verbose
pytest -k ecommerce     # just e-commerce tests
ruff check src tests    # lint
mypy src                # type check
```

---

<a name="faq"></a>
## 11. FAQ

**Q: Can I run this on a private/proprietary repo without sending anything outside?**
A: Yes. Zero network calls in the core path. CVE manifest is bundled. The only outbound call is your LLM provider — and only if you supply one.

**Q: What happens if my repo has both an e-commerce app and a blog in different folders?**
A: It'll mix the signals and probably classify as whichever has more pattern hits. Workaround: run the classifier per-subdirectory.

**Q: How accurate is the category detection?**
A: On the 3 fixture repos, 100% (e-commerce / blog / admin all correct, confidences 95% / 56% / 87%). On real-world repos, anecdotally ~85% on apps that fit one of the 9 fingerprints. Libraries and unusual apps drop to "unknown" (which is the right answer).

**Q: Why aren't there more categories?**
A: Each new category needs to be both common AND distinctive. We chose nine that cover ~80% of the apps in the wild. Splinter categories (like "e-commerce subscriptions" or "blog with newsletter") would degrade precision more than they'd improve recall. If you have a strong case for adding one, see [CONTRIBUTING.md](CONTRIBUTING.md).

**Q: Can I use this without Python?**
A: The CLI emits JSON; pipe it into any tool. You could shell out from Node / Go / Rust / etc.

**Q: Is the heuristic confidence reliable?**
A: It's a *signal*, not a ground truth. ≥0.7 means "very probably this category", 0.4-0.7 means "leaning this way", <0.4 means "weak match — manual review recommended". The `app_category_confidence` field always shows the value so you can threshold for your use case.

**Q: How does this differ from GitHub topics / repository metadata?**
A: GitHub topics are *self-reported* and usually missing or stale. We extract from *code structure* — much more reliable.

**Q: Will this work on Bitbucket / GitLab / self-hosted?**
A: Yes. We don't talk to any forge. We talk to the filesystem.

**Q: Is this affiliated with Codefixer?**
A: Yes — it was extracted from Codefixer's `app_description` + `hosting_requirements` analyzers. The OSS release is MIT-licensed; Codefixer's main product (fix generation, cascade analysis, GitHub PR flow, dashboard) remains closed-source. The classifier was always going to be the most reusable part — happy to make it broadly useful.

**Q: How do I contribute?**
A: See [CONTRIBUTING.md](CONTRIBUTING.md). The three best PRs to send: new category fingerprint, new framework extractor, new CVE entry.

---

## TL;DR

```bash
pip install app-classifier
app-classifier ./my-repo
```

Use it for: repo onboarding, service catalogs, agent context, doc generation, compliance scoping, threat-modeling prioritization, deployment automation, code search ranking.

Not agentic itself — but a high-value tool for agents that need to understand "what is this codebase?" before doing anything else.

---

## 12. Agentic mode (v0.2.0+)

Earlier in this doc I said the classifier wasn't agentic. **That's no longer true** for the new opt-in `classify_agentic()` path.

### What changed

`classify_agentic()` wraps the deterministic core with a real agent loop:

1. **Run deterministic classifier** as ground-truth baseline.
2. **Detect monorepo signals** (workspaces config, multiple manifests in subdirs, `lerna.json` / `nx.json` / `turbo.json` / `pnpm-workspace.yaml` / `Cargo.toml [workspace]`). If detected, classify each sub-app, then synthesize a top-level description via the LLM.
3. **If single-app AND confidence below threshold**, enter the agent loop:
   - LLM picks a tool to call (`read_file`, `list_files`, `grep`, `get_subdirs`)
   - Agent executes the tool, sends result back to LLM
   - LLM picks the next tool OR concludes
   - Loop until conclusion OR `max_iterations` (default 8)

### What makes this genuinely agentic (not just LLM-augmented)

| Property | classify_agentic |
|---|---|
| Autonomy | ✅ LLM picks the next investigation step |
| Multi-step planning | ✅ Plans a chain of tool calls toward a conclusion |
| Tool use | ✅ Real file-reading, grep, subdirectory traversal |
| Loop | ✅ Up to `max_iterations` (default 8) |
| Self-correction | ✅ Each observation can revise the hypothesis |

Compared to a calculator-as-tool pattern (where the AI uses the calculator), here the AI **drives the investigation strategy itself**. We provide the file-system tools; it decides what to look at.

### Usage

```python
import asyncio
from app_classifier import classify_agentic

# Your async LLM provider — same shape as classify_async
async def my_provider(prompt, max_tokens=400, temperature=0.0):
    # ... call OpenAI/Anthropic/Bedrock/Ollama ... see section 5
    return response_text

result = asyncio.run(classify_agentic(
    "./my-repo",
    llm_provider=my_provider,
    max_iterations=8,             # cap on LLM-tool calls
    confidence_threshold=0.75,    # below this, agent investigates
))

print(result.description.app_category)
print(result.description.functional_description)
print(f"LLM calls: {result.llm_calls}")
print(f"Iterations used: {result.iterations_used}")
print(f"Changed verdict? {result.changed_verdict} — {result.change_reason}")

# Full audit trail — every step the agent took
for step in result.steps:
    print(f"  step {step.iteration}: {step.action} — {step.reasoning}")
    print(f"    observed: {step.observation_summary[:120]}")
```

### Monorepo handling

For a repo with multiple sub-apps:

```python
result = asyncio.run(classify_agentic("./monorepo", llm_provider=my_provider))

if result.is_monorepo:
    print(f"Found {len(result.subapps)} sub-app(s):")
    for sub in result.subapps:
        print(f"  {sub.path}: {sub.description.app_category}")
    print(f"\nTop-level: {result.description.functional_description}")
```

The deterministic monorepo detector finds sub-apps (capped at 6); each is classified independently; the LLM writes a one-paragraph synthesis. **One LLM call total** for the whole monorepo, not one per sub-app.

### Safety properties

- **Path traversal blocked**: tools refuse paths outside the repo root (verified by test)
- **Read-only**: no `Write`, no `exec`, no network outside the LLM call itself
- **Bounded iterations**: hard cap stops runaway loops
- **Bounded per-tool output**: file reads truncated to 8KB; grep capped at 40 hits
- **JSON-strict**: invalid LLM responses are caught and logged, not executed
- **Cost-aware**: every call counted; surfaced in `result.llm_calls`
- **Audit trail**: every step recorded with reasoning + observation summary

### When to use `classify` vs `classify_async` vs `classify_agentic`

| Use case | Best fit |
|---|---|
| Just need a quick category, no LLM available | `classify()` |
| Want polished prose description | `classify_async(llm_provider=fn)` |
| Confidence matters, willing to spend a few LLM calls | `classify_agentic(llm_provider=fn)` |
| Monorepo with multiple distinct apps | `classify_agentic(llm_provider=fn)` |
| Low-confidence cases where heuristic is unsure | `classify_agentic(llm_provider=fn)` |

