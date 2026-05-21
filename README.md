# app-classifier

> Point it at a repo, get back **"this is an e-commerce app that does X"**.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)]()

Pattern-based application functional-category inference from routes, data models, and README. **Zero runtime dependencies** (pure stdlib). Optional LLM polish — bring your own provider.

## What problem this solves

Onboarding to a new repo, every engineer asks the same questions: *"What does this thing do? Is it a CRUD app or a queue worker? What database? What ports does it need?"* The README is usually wrong or stale. Codeowners are unavailable. You end up grepping for clues.

`app-classifier` answers those questions in **under a second** for any repo, on disk, with no network calls:

- **What kind of app is this?** — e-commerce, blog, social network, admin panel, REST API, auth/SSO, file management, scheduling, or messaging (9 categories, weighted-pattern matching, confidence-scored)
- **What does it do?** — a 2-3 sentence functional description, deterministically composed, optionally LLM-polished
- **How does it deploy?** — runtime + version, framework, web server, databases, caches, ports, env vars, container base image, runtime CVEs

## Quick start

```bash
pip install app-classifier
app-classifier ./my-repo
```

```
=== my-repo ===

Category:    e-commerce (78% confidence)
Runtime:     python 3.11
Framework:   FastAPI
Deploys as:  ASGI server (uvicorn / hypercorn / daphne)
Databases:   PostgreSQL, SQLAlchemy ORM
Cache/Queue: Redis, Celery
Features:    online shopping, messaging

📋 Summary: my-repo · python 3.11 · FastAPI · 23 HTTP route(s) · 5 data model(s) · DB: PostgreSQL, SQLAlchemy ORM

📝 What it does:
  my-repo is a e-commerce application. Primary functionality: online shopping, messaging.
  It models entities like Cart, Order, Product, User serving authenticated users.

🌐 HTTP Routes (23 found):
  GET    /products       →  list_products
  POST   /cart/add       →  add_to_cart
  POST   /checkout       →  checkout
  ...
```

## Python API

```python
from app_classifier import classify

result = classify("./my-repo")

print(result.app_category)              # 'e-commerce'
print(result.app_category_confidence)   # 0.78
print(result.detected_features)         # ['online shopping', 'messaging']
print(result.functional_description)    # "my-repo is a e-commerce application. ..."

# Full structured access
for route in result.routes:
    print(route.method, route.path, route.handler)

for model in result.data_models:
    print(model.name, model.framework, model.fields_hint)

# JSON-serializable
import json
print(json.dumps(result.to_dict(), indent=2))
```

## Just the deployment data?

Skip the classifier, use `hosting` directly:

```python
from app_classifier import analyze_hosting_requirements

report = analyze_hosting_requirements("./my-repo")
print(report.runtime)         # {'language': 'python', 'version': '3.11'}
print(report.web_server)      # {'framework': 'FastAPI', 'deployment_target': '...'}
print(report.databases)       # [{'name': 'PostgreSQL', ...}, ...]
print(report.ports)           # [{'port': 8000, 'source': 'Dockerfile', ...}]
print(report.web_server_vulnerabilities)  # CVEs on the container base image
```

## Optional: LLM polish

`classify_async` accepts ANY async callable as the LLM provider — no SDK pinned. If the LLM gives a useful response, the deterministic `functional_description` is replaced with the polished version; on any failure (timeout / parse error / hallucination guard / no provider) the deterministic version is kept.

```python
# OpenAI shim
async def my_openai_provider(prompt, max_tokens=400, temperature=0.2):
    import openai
    client = openai.AsyncOpenAI()
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens, temperature=temperature,
    )
    return resp.choices[0].message.content


# Anthropic shim
async def my_anthropic_provider(prompt, max_tokens=400, temperature=0.2):
    import anthropic
    client = anthropic.AsyncAnthropic()
    resp = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=max_tokens, temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


# Local llama.cpp / Ollama shim
async def my_ollama_provider(prompt, max_tokens=400, temperature=0.2):
    import httpx
    async with httpx.AsyncClient() as client:
        r = await client.post("http://localhost:11434/api/generate", json={
            "model": "llama3", "prompt": prompt, "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature},
        })
        return r.json().get("response")


# Use any of the above
import asyncio
from app_classifier import classify_async
result = asyncio.run(classify_async("./my-repo", llm_provider=my_openai_provider))
print(result.functional_description)
```

## What detection is supported

### Runtimes
Python, Java (JDK 8+), Node.js, Go, Ruby, PHP, Rust — detected from manifest files, Dockerfiles, version files (`.nvmrc`, `.python-version`, `.ruby-version`).

### Web frameworks (route extraction)
| Language | Frameworks |
|---|---|
| Python | Flask, FastAPI, Django |
| Java | Spring Boot, Struts 2 (struts.xml), classic Spring |
| Node | Express, Fastify, NestJS, Next.js |

### Data model ORMs
| ORM | Detected from |
|---|---|
| JPA / Hibernate | `@Entity`, `@Table` annotations |
| SQLAlchemy | `class X(Base)` |
| Django ORM | `class X(models.Model)` |

### Databases / caches
PostgreSQL, MySQL, MongoDB, H2, Oracle, SQL Server, MariaDB, Redis, RabbitMQ, Kafka, Elasticsearch, Celery.

### Container/deployment
Dockerfile (`FROM`, `EXPOSE`, `ENV`), docker-compose, Kubernetes manifests, Helm charts, k8s deployment YAML, Heroku Procfile, Vercel / Netlify configs.

### Runtime CVEs (web-server vulnerabilities)
Curated CVE manifest for nginx, Apache HTTPD, Tomcat, OpenJDK / Eclipse Temurin / Amazon Corretto. ~30 high-impact CVEs covered out of the box. PRs welcome.

### App categories (functional fingerprints)
e-commerce, blog/content, social network, admin panel/dashboard, REST API service, authentication/SSO, file/document management, scheduling/booking, messaging/notification. Each is matched by a weighted regex pattern against routes + model names + README.

## How it works

1. Walk every manifest/config file in the repo (capped at 800 files for speed)
2. Each file extracts language-specific signals (Maven artifact IDs, npm package names, Python deps, Dockerfile FROM, k8s containerPort, etc.) → `HostingReport`
3. Walk source files to extract HTTP routes + data models per framework
4. Pattern-match routes + model names + README purpose against 9 category fingerprints (weighted regex)
5. Compose the 2-3 sentence functional description deterministically
6. (Optional) Hand the structured signals to your LLM for a polished rewrite

**Time budget:** under 1 second on a 5K-file repo. Bounded scan caps file count + per-file read size.

## Design principles

- **No network**. Every signal comes from on-disk content. Bundled CVE manifest, no live API calls.
- **No SDK pin**. The LLM step is provider-agnostic — bring your own callable. We never `import openai`.
- **No surprises**. Failures on individual files don't kill the pass. Confidence is always reported; the consumer decides whether to trust it.
- **Pure read**. We never modify the target repo.

## Contributing

PRs welcome on three axes:

1. **More category fingerprints** — `_CATEGORY_FINGERPRINTS` in `classifier.py`. Each is `{ name, feature_label, signals: [(regex, weight), ...] }`.
2. **More CVE entries** — `data/web_server_cves.json`. Schema is documented in the file header.
3. **More framework extractors** — route + model extraction for Ruby on Rails, Phoenix, ASP.NET Core, Gin, Rocket, etc. would all be welcome.

### Run the test suite

```bash
pip install -e ".[test]"
pytest
```

Tests use fixture directories under `tests/fixtures/` — point the classifier at each, assert the expected category + features.

## What this is NOT

- **Not a security scanner.** It surfaces runtime CVEs on the container base image, but the rest of the code is for understanding, not vulnerability detection.
- **Not a deployment tool.** It tells you what the deployment looks like; it doesn't deploy anything.
- **Not a replacement for a README.** It generates a structural sketch; humans still write the narrative.

If you want a full security analysis + fix pipeline that uses this internally, see [Codefixer](https://codefixer.ai) (closed-source).

## License

MIT — see [LICENSE](LICENSE). Use it however you want. Attribution appreciated but not required.

## Acknowledgements

Extracted from Codefixer's `hosting_requirements` + `app_description` analyzers. The category-fingerprint approach was inspired by Sourcegraph's "what is this repo?" tooling and the way Backstage classifies services.
