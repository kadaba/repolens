# Contributing to app-classifier

Thanks for considering a contribution. There are three high-leverage axes — pick whichever fits your itch.

## 1. Add a category fingerprint

Open `src/app_classifier/classifier.py` and find `_CATEGORY_FINGERPRINTS`. Each entry is:

```python
{
    "name": "internal name shown in output",
    "feature_label": "human-readable feature tag",
    "signals": [
        (r"regex\\b", weight_int),
        ...
    ],
}
```

The matcher concatenates all routes + model names + README purpose into one haystack and runs each regex against it. Weights stack additively per fingerprint. A category needs **score ≥ 2** to show up as a detected feature, and the top-scoring fingerprint becomes the app category.

When adding one:

1. Pick distinctive signals that are unlikely to false-positive. `\\bcart\\b` is strong; `\\bdata\\b` is too generic.
2. Add a fixture to `tests/fixtures/<your_category>/` with a minimal route file + model file + README excerpt.
3. Add a parametrized test to `tests/test_classifier.py`.

## 2. Add a framework extractor

Route extraction is in `_extract_python_routes`, `_extract_js_routes`, `_extract_java_routes` in `classifier.py`. Model extraction is in `_extract_python_models`, `_extract_java_entities`.

To add support for a new framework (Rails, Phoenix, Gin, ASP.NET Core, etc.):

1. Add a regex constant at the top of the route/model extraction section.
2. Add a branch in the appropriate `_extract_*` function.
3. Add a fixture under `tests/fixtures/` and a test.

## 3. Add a runtime CVE entry

The web-server CVE manifest lives at `src/app_classifier/data/web_server_cves.json`. Schema:

```json
{
  "server_name": {
    "latest_stable": "version string",
    "cves": [
      {
        "cve": "CVE-YYYY-NNNNN",
        "severity": "critical|high|medium|low",
        "summary": "short description",
        "fix": "version it was fixed in",
        "affects_max_version": "highest unpatched version"
      }
    ]
  }
}
```

Currently covers nginx, Apache HTTPD, Tomcat, OpenJDK / Eclipse Temurin / Amazon Corretto. PRs for Redis, PostgreSQL, MySQL, MongoDB, HAProxy, etc. very welcome.

When adding a server, also add a base-image pattern to `_IMAGE_PATTERNS` in `web_server_vulns.py` so the analyzer can detect it from Dockerfiles.

## Development setup

```bash
git clone https://github.com/codefixer/app-classifier.git
cd app-classifier
pip install -e ".[dev,test]"
pytest                  # run tests
ruff check src tests    # lint
mypy src                # type-check
```

## Pull request checklist

- [ ] Tests added or updated
- [ ] `pytest` passes
- [ ] `ruff check` passes
- [ ] No new runtime dependencies (we're stdlib-only on purpose)
- [ ] README updated if the public API changed
- [ ] CHANGELOG entry under "Unreleased"

## What we won't accept

- Pinning specific LLM SDKs in dependencies. The LLM step is provider-agnostic on purpose.
- Network calls during analysis (other than the optional LLM step, which is user-controlled).
- Anything that modifies the target repo. We're pure-read.
- Massive new fingerprint lists from one project type — keep new categories distinct, not splinters of existing ones.
