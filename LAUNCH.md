# Launching `app-classifier` — Naming, SEO, and Real-World Applications

This doc is for the moment **before you push to GitHub**. It covers:

1. [Repository name recommendations](#repo-names) — three good options with reasoning
2. [GitHub SEO setup](#github-seo) — topics, description, social preview
3. [Application gallery](#applications) — 18 concrete use cases with code
4. [Comparison vs alternatives](#vs-alternatives) — how to position this
5. [Launch checklist](#checklist) — concrete steps before going live

---

<a name="repo-names"></a>
## 1. Repository name recommendations

The current package name is `app-classifier`. Three options for the GitHub repo, ranked by my recommendation:

### 🥇 Recommended: **`repolens`**

- **Domain feel**: A *lens* you point at a repo. Implies insight without overpromising "intelligence."
- **Brandable**: `repolens.dev`, `@repolens` Twitter, `repolens` GitHub org, all likely available.
- **Searchable**: Distinctive enough to dominate its own search results within 6 months.
- **Pronounceable**: Two syllables, hard to misspell.
- **Tagline**: *"Point it at a repo, instantly see what it does."*
- **Trade-off**: Doesn't tell you exactly what it does until you read the README.

```bash
pip install repolens
repolens ./my-repo
```

### 🥈 **`whatdoes`**

- **Memorable**: Verb-first CLI experience: `whatdoes ./my-repo` reads like the question it answers.
- **SEO**: People literally Google "what does this repo do" — this name dominates that query.
- **Quirky**: Stands out in a sea of `*-analyzer` / `*-scanner` names.
- **Trade-off**: Looks like a typo in some contexts ("what does what?"). And the PyPI name might be taken.

```bash
pip install whatdoes
whatdoes ./my-repo
```

### 🥉 Safe choice: **`app-classifier`**

- **Descriptive**: The name IS the documentation.
- **No surprises**: Existing PyPI conventions, immediately understood.
- **Trade-off**: Generic, hard to brand around, easy to confuse with ML "classifier" tools.

### Names I considered but rejected

| Name | Why rejected |
|---|---|
| `code-iq` | "IQ" feels like overclaiming intelligence |
| `repology` | Too academic-sounding |
| `repo-xray` | The "xray" trope is overused (logstash-xray, react-x-ray, etc.) |
| `stackid` | Confusable with Stack Overflow / stack traces |
| `appsense` | "Sense" implies more semantic understanding than the heuristic provides |
| `archeo` | Cute for "archaeology" but unclear connection to repos |

### Final recommendation

**Go with `repolens`** unless one of the following is true:
- You want maximum literal clarity over branding → use `app-classifier`
- You want the quirky/memorable angle → use `whatdoes`

The Python package can stay `app-classifier` (it's already on PyPI under that name in your control), and the GitHub repo name can differ. Most projects do this: package name = literal, repo name = brand.

```
GitHub repo:  github.com/repolens/repolens
PyPI:         pip install app-classifier
CLI:          app-classifier ./repo   (or alias: repolens)
```

---

<a name="github-seo"></a>
## 2. GitHub SEO setup

### Repository description (160-char limit)

Pick one based on the name you chose:

**For `repolens`:**
> Point it at any repo, instantly see what it does. Pattern-matches routes + data models to classify apps (e-commerce, blog, REST API…). Pure Python, agentic mode optional.

**For `whatdoes`:**
> `whatdoes ./my-repo` — answers "what does this code do?" by classifying any repo into 9 functional categories. Zero deps. Optional LLM agent for deep cases.

**For `app-classifier`:**
> Pattern-based application functional-category inference from routes, data models, and README. Zero deps. Optional agentic LLM mode for deep investigation.

### GitHub topics (max 20 — pick 15-20)

GitHub topics are the single biggest SEO lever. Use the slots well. Recommended set:

```
code-analysis
static-analysis
repository-analysis
code-understanding
developer-tools
developer-onboarding
ai-agent
llm-tool
agentic-ai
agentic-framework
function-calling
monorepo
monorepo-detection
tech-stack-detection
documentation-generator
code-intelligence
python
mit-license
zero-dependencies
devops
```

**Why these specifically:**
- `code-analysis`, `static-analysis` — bread-and-butter discoverability
- `ai-agent`, `agentic-ai`, `agentic-framework`, `llm-tool`, `function-calling` — captures the post-2024 AI tooling search waves
- `monorepo`, `monorepo-detection` — niche but uncontested; people land here from Google
- `developer-onboarding`, `code-understanding` — speaks to the human use case
- `python`, `mit-license`, `zero-dependencies` — practical filters people use
- `documentation-generator`, `code-intelligence`, `devops` — adjacent communities

### Social preview image

GitHub generates a default but a custom one boosts CTR ~30%. Suggested mock-up content for `social-preview.png` (1280×640):

```
┌─────────────────────────────────────────────────┐
│                                                  │
│  repolens                                        │
│  point it at any repo → instantly see what       │
│                          it does                 │
│                                                  │
│  $ repolens ./my-repo                            │
│  Category:  e-commerce (78% confidence)          │
│  Stack:     FastAPI + PostgreSQL + Redis         │
│  Features:  online shopping, messaging           │
│                                                  │
│  Pure Python · Zero deps · MIT · Agentic mode    │
│                                                  │
└─────────────────────────────────────────────────┘
```

Upload via: Repo Settings → General → Social preview → Edit.

### README hook (above-the-fold)

The first 150 words decide whether someone scrolls. Recommended opener:

```markdown
# repolens

> **Point it at any repo, instantly see what it does.**
>
> `repolens ./my-repo` → "e-commerce app · FastAPI + PostgreSQL · 23 routes · 5 data models"
> in **under a second**, with **zero dependencies**.

[![PyPI](https://img.shields.io/pypi/v/app-classifier.svg)](https://pypi.org/project/app-classifier/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MIT License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/<owner>/<repo>/actions/workflows/test.yml/badge.svg)](https://github.com/<owner>/<repo>/actions)

**What it does** — reads HTTP routes, data models, and README signals, then pattern-matches against 9 application categories (e-commerce, blog, admin panel, REST API, …). Returns category + confidence + 2-3 sentence functional description + full deployment picture (runtime, framework, databases, ports, container CVEs).

**What's novel** — works on any language (Python, Java, JS/TS, Node, Go), handles monorepos, and ships an optional **agentic mode** where an LLM autonomously investigates low-confidence cases by reading files and grepping for evidence. The agent is real (tool use, multi-step planning, bounded loop), not LLM-augmented theater.

[Quickstart](#quickstart) · [Use Cases](#use-cases) · [API](USAGE.md) · [Why](#why)
```

The hook works because:
- Headline = literal value prop
- One-line example shows output AND speed AND simplicity
- Badges signal "this is a real package, not a toy"
- Two paragraphs cover "what" then "what's novel"
- Footer links route advanced readers deeper

### Tags for the first release

When you `git tag v0.1.0` and push, GitHub creates a release page. Use this release-notes template:

```markdown
## v0.1.0 — Initial release

The first cut. Pattern-based functional-category inference from routes + data models + README. Zero runtime deps.

### Features

- **9 application categories** with weighted regex fingerprints
- **6 language detectors** for runtime + framework + databases + ports
- **Optional LLM polish** — provider-agnostic, bring your own callable
- **Agentic mode** — opt-in autonomous investigation for low-confidence cases (`classify_agentic()`)
- **Monorepo detection** — workspaces config + per-subapp classification
- **CLI** — `app-classifier ./repo` with human + JSON modes
- **Runtime CVE detection** — curated manifest for nginx / Apache / Tomcat / OpenJDK

### Tested on

- 3 fixture repos (e-commerce Django, blog Flask, admin Express)
- Live test on Codefixer's own repo
- 33 unit tests passing

### Coming in v0.2.0

- More framework extractors (Rails, Phoenix, ASP.NET Core, Gin)
- Java + Python symbol-usage catalogs (currently JS-only)
- Expanded runtime CVE manifest (Redis, PostgreSQL, MongoDB, HAProxy)
- Web UI for browsing classification results

### Acknowledgements

Extracted from [Codefixer](https://codefixer.ai)'s code-understanding analyzers. MIT-licensed.
```

---

<a name="applications"></a>
## 3. Application gallery — 18 concrete use cases

The point of this section: someone landing on the repo should immediately recognize *their own problem* in this list. Generic use cases don't sell — specific ones do.

### 🆕 Developer onboarding

**1. First-day repo tour** — A new engineer joins, gets pointed at 47 microservices. Without `repolens`: spends a week reading READMEs. With:

```bash
for repo in services/*/; do
  echo "=== $(basename $repo) ==="
  app-classifier "$repo" --json | jq '{category: .app_category, summary: .one_line_summary}'
done
```

Output: a one-line summary per service. New hire knows the lay of the land in 10 minutes.

**2. Internal Backstage / service catalog auto-populate** — Most catalogs have stale type fields. Run nightly:

```python
from app_classifier import classify
import yaml

for repo_path in iterate_org_repos():
    result = classify(repo_path)
    update_catalog_entry(
        name=result.name,
        kind=result.app_category,
        languages=[result.runtime.get("language")],
        databases=result.databases,
        deployment_target=result.deployment_target,
    )
```

**3. AI coding assistant context-pre-briefing** — Before pointing Cursor / Claude Code / Continue / Aider at an unfamiliar repo:

```python
result = classify(repo_path)
context_prefix = f"""
You're working in {result.name}, which is a {result.app_category} application.
{result.functional_description}
Tech stack: {result.framework} on {result.runtime.get('language')} {result.runtime.get('version', '')}.
Databases: {', '.join(result.databases)}.
""".strip()

# Pass context_prefix as system prompt or first message
```

Anecdotally improves AI assistant answer quality 2-3x on first-day-in-codebase questions.

### 🔍 Documentation & discovery

**4. Auto-generated README skeleton** — Pass the classification + structure to an LLM, get a starter README:

```python
result = classify("./my-repo")
prompt = f"""Generate a README for a {result.app_category} app called
{result.name}. It uses {result.framework} and exposes these routes:
{[r.path for r in result.routes[:20]]}. Data models: {[m.name for m in result.data_models]}.
Include sections: Overview, Quick Start, API Reference."""
# ... send to OpenAI / Anthropic / etc.
```

**5. Auto-updating architecture docs** — Nightly job classifies the repo, writes a `docs/architecture-auto.md` file, opens a PR if anything changed. Architecture diagrams stay honest.

**6. Code search ranking** — Give Sourcegraph / your internal search category-aware boosting. Searches for "checkout flow" rank e-commerce repos higher than blog repos with the same keyword.

**7. Search-engine for internal codebases** — Build a "what's our [X] service?" Q&A bot. Classify every repo, embed the descriptions, semantic-search over them.

### 🔒 Security & compliance

**8. PCI-DSS / HIPAA scope identification** — Compliance applies based on what the app DOES, not what's in its repo metadata. Use this to find every repo classified as `e-commerce` or matching `payment|cardholder|PHI` in features:

```python
in_scope = []
for repo in org_repos:
    r = classify(repo)
    if r.app_category == "e-commerce":
        in_scope.append((repo, "PCI", r.detected_features))
    if any(x in (r.purpose or "").lower() for x in ("health", "patient", "phi")):
        in_scope.append((repo, "HIPAA", r.detected_features))
```

**9. Threat-modeling prioritization** — A pen-test team has 200 repos and 3 weeks. Combine category + runtime CVE detection to triage:

```python
from app_classifier import classify
priority_score = {"e-commerce": 5, "authentication / SSO": 5, "admin panel / dashboard": 4,
                   "REST API service": 3, "blog / content platform": 2}

for repo in repos:
    r = classify(repo)
    score = priority_score.get(r.app_category, 1)
    cves = sum(len(v["cves"]) for v in r.runtime.get("web_server_vulnerabilities", []))
    yield (repo, score + cves, r)
```

**10. Container base-image CVE alerts** — The bundled CVE manifest already covers nginx / Apache / Tomcat / OpenJDK. Hook into CI:

```yaml
# .github/workflows/security.yml
- run: pip install app-classifier
- run: app-classifier . --json | jq '.web_server_vulnerabilities'
- run: |
    if [ "$(app-classifier . --json | jq '.web_server_vulnerabilities | length')" -gt 0 ]; then
      echo "⚠️ Runtime/container CVEs detected" >> $GITHUB_STEP_SUMMARY
      exit 1
    fi
```

### 🛠️ DevOps & platform

**11. Auto-generated Kubernetes manifests** — Detect runtime + framework + ports + env vars → generate a starter k8s deployment, docker-compose, Heroku Procfile, Render `render.yaml`. Codefixer's "Download Deploy Bundle" uses this exact pattern.

**12. Migration planning** — "Find all Express apps so we can migrate them to Hono together":

```python
from app_classifier import classify
candidates = [
    r for r in org_repos
    if classify(r).framework == "Express"
]
```

**13. Cloud cost attribution** — Group services by category for FinOps reporting:

```python
costs_by_category = defaultdict(float)
for repo in org_repos:
    cat = classify(repo).app_category
    costs_by_category[cat] += get_aws_cost_for_service(repo)
# Report: "e-commerce: $42k/mo, admin panel: $8k/mo, blog: $1.2k/mo"
```

**14. Pre-deployment gate** — In CI, block deploys when the classifier detects a regression (e.g., a payment-handling commit lands in a repo previously classified as blog):

```python
prev = json.load(open(".github/prev-classification.json"))
curr = classify(".").to_dict()
if curr["app_category"] != prev["app_category"]:
    sys.exit("Classification changed — review needed")
```

### 🤖 AI & agent integration

**15. Tool in an AI agent's toolkit** — Function-calling shim for OpenAI / Anthropic / Bedrock agents:

```python
TOOLS = [{
    "type": "function",
    "function": {
        "name": "classify_repo",
        "description": "Get the application type, framework, stack, and "
                       "functional description for a repository. Call this "
                       "BEFORE making changes to an unfamiliar codebase.",
        "parameters": {
            "type": "object",
            "properties": {"repo_path": {"type": "string"}},
            "required": ["repo_path"],
        },
    },
}]

# When agent calls classify_repo, execute:
from app_classifier import classify
result = classify(args["repo_path"]).to_dict()
```

The agent now knows what the repo IS before deciding what to do.

**16. Agentic deep-dive for ambiguous cases** — Use `classify_agentic` when the heuristic confidence is low and you have an LLM available:

```python
import asyncio
from app_classifier import classify_agentic

async def claude_provider(prompt, max_tokens=400, temperature=0.0):
    # ... call Claude ...

result = asyncio.run(classify_agentic(
    "./my-monorepo", llm_provider=claude_provider,
    max_iterations=8, confidence_threshold=0.75,
))

# Agent autonomously read files, grepped, refined the verdict
print(f"Final: {result.description.app_category}")
print(f"Investigation: {result.iterations_used} steps")
for step in result.steps:
    print(f"  {step.action}: {step.reasoning}")
```

**17. M&A / due diligence** — Acquiring a company; need to understand 50 unfamiliar repos fast. Batch-classify, focus humans on the high-value or compliance-relevant ones.

```python
import csv
with open("dd-classification.csv", "w") as f:
    w = csv.writer(f)
    w.writerow(["repo", "category", "confidence", "stack", "summary"])
    for repo in acquired_repos:
        r = classify(repo)
        w.writerow([repo, r.app_category, r.app_category_confidence,
                    f"{r.framework or '?'} + {r.runtime.get('language', '?')}",
                    r.one_line_summary])
```

### 🎓 Educational

**18. Open-source learning aid** — Point at a popular project (Django, Sentry, n8n, etc.), use the output to scaffold a "what does this project actually do?" study guide for newcomers.

```bash
git clone https://github.com/getsentry/sentry
app-classifier sentry --json | jq '{category: .app_category, stack: .framework, models: .data_models[].name}'
```

---

<a name="vs-alternatives"></a>
## 4. Comparison vs alternatives

| Tool | Detects what app does? | Multi-language? | Monorepo aware? | Network needed? | License |
|---|---|---|---|---|---|
| **`repolens` (this)** | ✅ 9 categories + features | ✅ Python/Java/JS/TS/Go/Node | ✅ + LLM synth | ❌ none | MIT |
| GitHub Linguist | ❌ only language % | ✅ language detect | ❌ flat | ❌ | MIT |
| `tree`, `cloc` | ❌ counts only | n/a | ❌ | ❌ | various |
| Sourcegraph code intelligence | ❌ no app classification | ✅ | ✅ | ✅ (SaaS) | mixed |
| Backstage | ❌ user-configured types | n/a | ✅ | ✅ (server) | Apache 2 |
| Renovate | ❌ deps only | ✅ | ✅ | ✅ | AGPL |
| `pip-audit`, `osv-scanner` | ❌ CVE only | partial | ❌ | ✅ (OSV) | MIT / Apache |
| GitHub Copilot | partial (per-file) | ✅ | ❌ | ✅ (SaaS) | proprietary |

The closest alternative is **GitHub Linguist** (language detection only — doesn't tell you what the app DOES). The closest at "what does this do" is **a human reading the README** — which is why this tool exists.

---

<a name="checklist"></a>
## 5. Pre-launch checklist

Before pushing to GitHub:

### Inside the repo

- [ ] Update `pyproject.toml` `[project.urls]` with the actual GitHub URLs
- [ ] Update `README.md` and `USAGE.md` to reference the new repo name (if you change it from `app-classifier`)
- [ ] Add a `CODE_OF_CONDUCT.md` (use Contributor Covenant 2.1 template)
- [ ] Add a `SECURITY.md` (link to a contact email or HackerOne policy)
- [ ] Add a `.github/workflows/test.yml` (the README badge expects this)
- [ ] Add a `.github/ISSUE_TEMPLATE/` with `bug.yml` + `feature.yml`
- [ ] Add a `.github/PULL_REQUEST_TEMPLATE.md`
- [ ] Make sure `LICENSE` author line says what you want it to say
- [ ] Strip any test fixtures that contain dummy "passwords" if they look real

### GitHub Settings

- [ ] Set the repo description (use one of the 160-char options above)
- [ ] Set the 20 topics (list above — copy and paste)
- [ ] Upload the social preview image (1280×640)
- [ ] Enable Discussions (Settings → Features → Discussions)
- [ ] Enable Sponsors button (if you want one) → Sponsor button → Custom
- [ ] Branch protection on `main` (require PR + 1 review)
- [ ] Enable GitHub Actions
- [ ] Set the website to `https://codefixer.ai` or your project page

### PyPI

- [ ] `pip install -e ".[dev,test]"` → run `pytest` once more (should be 33 passing)
- [ ] `python -m build` → creates `dist/*.whl` + `dist/*.tar.gz`
- [ ] `twine check dist/*` → checks metadata
- [ ] `twine upload --repository testpypi dist/*` → test on test.pypi.org first
- [ ] Verify install works: `pip install -i https://test.pypi.org/simple/ app-classifier`
- [ ] `twine upload dist/*` → push to real PyPI

### Announcement plan

Don't underestimate the launch — a good tool with a bad launch dies. In order:

1. **GitHub repo public** (day 0)
2. **PyPI release** (day 0, same time)
3. **HN "Show HN" post** (day 1, Tuesday or Wednesday morning UTC, title format below)
4. **Twitter/X thread** (day 1, after HN post — link to the HN thread, not the repo)
5. **r/Python "Showcase Saturday"** (the following Saturday)
6. **DEV.to / Hashnode article** explaining the agentic angle specifically (week 2)
7. **Hacker News follow-up** ("repolens 1 week later: what I learned from your feedback") at week 2

Suggested HN title: `Show HN: Repolens – point it at any repo, instantly see what it does`

**What NOT to do at launch:**
- Don't bury the agentic angle. Lead with it. *"the agent is real, not LLM theater"* is the differentiator.
- Don't open with the corporate origin. Mention Codefixer briefly at the bottom of the README, not in the headline.
- Don't claim you're better than CodeQL / Sourcegraph. You're not — you're complementary.

### Day-1 success metrics (sanity check, not OKRs)

- ⭐ 100 stars by end of week 1 → indicates "people are intrigued"
- 📥 1000 PyPI downloads by end of week 1 → indicates "people are actually trying it"
- 🐛 3-5 issues / PRs in week 1 → indicates "people are using it"
- 📨 1-2 inbound emails about Codefixer → the OSS funnel is working

If you hit all four, you have a real project. If you hit none, the positioning is off — iterate the README hook + try again in 6 weeks with a fresh angle (the framework-extractor PRs, the agentic deep-dive blog post, etc.).

---

## Quick links

- [README.md](README.md) — the front door
- [USAGE.md](USAGE.md) — comprehensive API guide
- [CONTRIBUTING.md](CONTRIBUTING.md) — 3 ways to contribute
- [docs/FINGERPRINTS.md](docs/FINGERPRINTS.md) — how the pattern matching works internally
- [CHANGELOG.md](CHANGELOG.md) — what changed in each release

---

_Generated as the launch-prep brief. Update before you push to GitHub._
