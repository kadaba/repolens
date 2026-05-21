# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
