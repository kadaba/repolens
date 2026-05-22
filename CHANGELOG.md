# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.2] — 2026-05-22

### Added

- **New fingerprint: `developer tooling / CLI`** — recognizes code-analysis
  tools, linters, formatters, scaffolders, and CLI utilities. Signals include
  CLI framework names (`commander`, `yargs`, `click`, `argparse`, `cobra`,
  `clap`, `oclif`, `typer`), parsing infra (`ast`, `tree-sitter`, `parser`,
  `lexer`), linting/formatting tools (`eslint`, `ruff`, `prettier`, `gofmt`),
  and code-analysis terminology (`call graph`, `dependency graph`, `static
  analysis`, `sast`, `codebase`, `code review`).
- Requires 2+ distinct signal rows (`min_signals: 2`) so a stray `argparse`
  import in a random Python script doesn't auto-classify the whole repo as
  a CLI tool.

### Fixed

- **Route extractor no longer leaks test-fixture routes.** Test directories
  (`tests/`, `test/`, `__tests__/`, `spec/`, `specs/`, `e2e/`, `cypress/`,
  `playwright/`, `__mocks__/`, `fixtures/`) and test-file naming patterns
  (`*.test.*`, `*.spec.*`, `*_test.*`, `*_spec.*`, `*_test.go`) are now
  skipped. Real-world regression: pointing `app-classifier` at a code-analysis
  tool surfaced `/fake`, `/also-fake`, `/real` from its `tests/*.test.js`
  fixtures as if they were production routes.

### Compatibility

- Backwards compatible. Public API unchanged. Test-directory skip is purely
  additive — no fixture's expected routes overlap with the new skip list.

## [0.5.1] — 2026-05-22

### Fixed

- README links to `docs/llm-providers.md` and `docs/code-mapping.md` now use
  absolute GitHub URLs. PyPI only renders `README.md` — the `docs/` directory
  isn't included in the published package, so relative links 404'd on
  https://pypi.org/project/app-classifier/.

## [0.5.0] — 2026-05-22

### Added — multi-provider LLM layer

- **`LLMProviderProtocol`** — new typed Protocol for adapter classes
- **5 stdlib-only adapters** — `OpenAIProvider`, `AnthropicProvider`, `OpenRouterProvider`, `OllamaProvider`, `OpenAICompatProvider`
- **OpenAICompat covers** LM Studio, vLLM, llama.cpp server, Groq, Together, Fireworks, DeepSeek, Mistral — anything OpenAI-compatible
- **`load_provider()`** — resolves a provider from env var → `~/.app-classifier/providers.json` → autodetect, with `${VAR}` interpolation
- **Zero new runtime deps.** All adapters use stdlib `urllib`. Optional extras for official SDK clients: `pip install app-classifier[openai]`, `[anthropic]`, `[all]`

### Added — `classify_smart()`

- **`classify_smart(repo)`** — rule-based first; escalates to the agentic loop only when confidence is below threshold AND a provider is configured. Returns `AppDescription`.
- **`classify_smart_async(repo)`** — async variant returning the full `AgentClassificationResult` audit trail.
- **Graceful degradation** — no provider configured → returns the low-confidence baseline rather than raising.

### Added — `map_code()` non-LLM impact analysis

- **`map_code(repo)`** — produces a `CodeMap` with file-dependency graph (Python, JS/TS, Java, Go, Ruby, PHP) plus a Python function-call graph.
- **`CodeMap.impact_of(target, transitive=True)`** — BFS over the reverse graph with cycle detection. Supports file paths and `"file:function"` keys.
- **Entry-point detection** — zero-importer files **plus** framework markers (`@app.route`, `@RequestMapping`, Express `app.get`, `func main()`, etc.).
- **New fixtures** — `tests/fixtures/go_service`, `ruby_sinatra`, `java_spring`.

### Compatibility

- Backwards compatible. The existing `LLMProvider` Callable alias in `classifier.py` is **not removed** — both `LLMProvider` (Callable) and `LLMProviderProtocol` (Protocol) coexist.
- All existing tests pass unchanged.
- `classify()` and `classify_smart()` (with no provider configured) make **no network calls**.

## [0.4.1] — 2026-05-22

### Fixed — fingerprint over-matching from v0.4.0

The 18 new app fingerprints introduced in v0.4.0 occasionally won verdicts on
weak single-token evidence. The scoring algorithm now supports a `min_signals`
field per fingerprint that requires N distinct signal rows to match before
the category contributes to scoring.

- **marketplace / two-sided platform** (`min_signals: 2`) — a lone
  "multi-vendor" mention in an e-commerce README no longer flips the
  verdict away from "e-commerce".
- **FinTech / banking / payments** (`min_signals: 2`) — a single "Stripe"
  mention (used by most e-commerce checkout flows) is no longer enough to
  classify an app as FinTech.
- **admin panel / dashboard** (`min_signals: 2`) — a lone "dashboard" word
  (which appears in customer portals, BI tools, vendor consoles) no longer
  classifies the app as an admin panel. The permission/role/grant/revoke
  row must also fire.

Concrete impact: `tests/fixtures/ecommerce_django` confidence rose
**0.72 → 0.95**, restoring the agentic short-circuit
(`test_agent_uses_baseline_when_confidence_high` now passes). The Laravel
"Customer Portal" fixture is no longer misclassified as an admin panel.

### Compatibility

- Backwards compatible. `min_signals` defaults to 1; existing fingerprints
  behave unchanged unless explicitly opted in.

## [0.4.0] — 2026-05-21

### Added — 18 new app fingerprints

- data analytics / dashboard (Grafana / Superset / Metabase / KPI prose)
- marketplace / two-sided platform (seller+buyer, commission, payouts)
- real-time collaboration (WebSocket, CRDT, Yjs, Liveblocks, multiplayer)
- CMS / wiki / static site (WordPress / Strapi / Sanity / Hugo / Astro)
- DevOps / CI-CD tooling (Jenkins / GitHub Actions / Terraform / k8s / Helm)
- crypto / Web3 / blockchain (Solidity / ethers / wagmi / NFT / DeFi)
- streaming / media (HLS / DASH / WebRTC / transcoding / CDN)
- forum / community / Q&A (Discourse / threads / upvote / reputation)
- customer support / helpdesk (Zendesk / tickets / SLA / chatbot)
- CRM / sales pipeline (Salesforce / HubSpot / leads / opportunities)
- project management / issue tracker (Jira / Linear / sprint / kanban)
- search engine / discovery (Elasticsearch / Meilisearch / Algolia / facets)
- healthcare / EHR / medical (HIPAA / FHIR / HL7 / patient / clinician)
- FinTech / banking / payments (Stripe / Plaid / ACH / SWIFT / KYC)
- IoT / device management (MQTT / LoRaWAN / Zigbee / Home Assistant)
- ML / data science pipeline (pandas / pytorch / Jupyter / MLflow / dbt)
- mobile application (React Native / Flutter / Android / iOS)
- desktop application (Electron / Tauri / Qt / WPF)
- gaming / game backend (Unity / Unreal / matchmaking / PlayFab)

### Added — 6 new language detectors

- **Ruby** via `Gemfile` — detects Rails / Sinatra / Hanami / Roda + DB drivers (pg / mysql2 / sqlite3) + Sidekiq
- **.NET / C#** via `.csproj` / `.fsproj` / `.vbproj` — detects ASP.NET Core + Entity Framework Core + Npgsql / MySqlConnector
- **Rust** via `Cargo.toml` — detects Actix Web / Axum / Rocket / Warp / Poem / Tide + SQLx / Diesel
- **Elixir** via `mix.exs` — detects Phoenix + Ecto + Postgrex + Redix
- **Dart / Flutter** via `pubspec.yaml`
- **Mobile fallback** — directory layout (`android/` + `ios/`) detects React Native; pure Android Manifest detects Android Native; Podfile / Package.swift detects iOS

### Compatibility

- Backwards compatible. Existing 42 tests still pass.

## [0.3.0] — 2026-05-21

### Added

- **Source-file scanning for AI/LLM library imports** — walks up to 80 source files (Python/JS/TS/Go/Ruby) for `import openai`, `require('langchain')`, `from anthropic`, `huggingface_hub`, `chromadb`, etc. Closes the Stripe-AI-sample gap: even when routes + models are sparse, an `import openai` in any source file lights up the AI fingerprint.
- **Full-README haystack** — pattern matcher now reads up to 16KB of the README (previously only the first 600 chars). Catches "AI-powered" / "GenAI" / "agentic" prose buried below the banner.
- **Broader AI/LLM fingerprint** — adds generic AI terminology (`AI-powered`, `AI-driven`, `GenAI`, `chatbot`, `conversational AI`, `agentic`, `machine learning`, etc.) alongside the specific SDK names. No more false-negatives on "we built an AI agent" prose.
- More AI SDK keywords: `crewai`, `autogen`, `transformers`, `sentence-transformers`, `huggingface_hub`, `ollama`, `llama.cpp`, `pgvector`.

### Compatibility

- Backwards compatible. `_infer_app_category` gains an optional `root` parameter (None-default preserves old behavior for direct callers).

## [0.2.0] — 2026-05-21

### Added

- **PHP runtime detection** — `composer.json` parser (Laravel, Symfony, Slim, CakePHP, Yii, CodeIgniter) + Doctrine/Eloquent ORM detection
- **Standalone PHP detection** — falls back to walking `.php` files when no `composer.json` exists (catches DVWA, WordPress, Drupal, Magento, legacy PHP apps)
- **AI / LLM application fingerprint** — detects OpenAI/Anthropic/Bedrock SDKs, LangChain/LlamaIndex/Haystack, vector DBs (Chroma/Pinecone/Weaviate/Qdrant), RAG patterns, agent frameworks
- **Security training / vulnerable app fingerprint** — recognizes DVWA, WebGoat, Juice Shop, Mutillidae, bWAPP, NodeGoat, CTF challenges
- **README database mining** — when manifests don't surface a DB but the README says "MariaDB" / "MongoDB" / "PostgreSQL" / "Redis" etc., that's surfaced as a low-confidence signal
- **Markdown-image-only README skip** — purpose extractor no longer returns banner GIF markdown like `![Hero](...)` as the app's purpose

### Fixed

- Cross-language contamination: PHP-only repos no longer get misclassified as Java when a stray `.java-version` is present (PHP detection now runs in the fallback pass)

### Compatibility

- Backwards compatible. All existing API surfaces unchanged.

## [0.1.0] — 2026-05-21

### Initial release

- Pattern-based functional category inference (9 fingerprints)
- Route extraction for Python (Flask / FastAPI / Django), Java (Spring / Struts), Node (Express)
- Data model extraction for JPA, SQLAlchemy, Django ORM
- Hosting requirements analyzer (runtime / framework / databases / ports / env vars)
- Curated web-server CVE manifest (nginx / Apache HTTPD / Tomcat / OpenJDK)
- Provider-agnostic LLM enrichment hook (`classify_async(repo, llm_provider=fn)`)
- CLI: `app-classifier <path>` + `--json` mode
- 24 tests, 3 fixture repos (e-commerce / blog / admin)
