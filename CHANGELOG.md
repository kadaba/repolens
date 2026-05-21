# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
