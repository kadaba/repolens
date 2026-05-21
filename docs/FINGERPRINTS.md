# How the pattern matching works

`app-classifier` infers the app's functional category by running weighted regex patterns over a unified "signal haystack" built from three sources:

1. **HTTP routes** — every path + handler name extracted from Flask/FastAPI/Django/Express/Spring/Struts source
2. **Data model names + fields** — JPA entities, SQLAlchemy/Django models
3. **README purpose** — first non-trivial paragraph from `README.md` / `README.rst`

Each category has a list of `(regex, weight)` signals. When a regex matches the haystack, its weight is added to the category's score. The category with the highest score wins; ties get medium confidence.

## Confidence computation

```
confidence = min(0.95, top_score / (top_score + second_score + 0.5))
```

The `+ 0.5` smoothing prevents 100% confidence when the second-place category had zero signals. If `top_score >= 5`, confidence gets a `+0.15` boost (capped at 0.95) — represents "the evidence is overwhelming, even if alternatives also matched".

## The 9 fingerprints

| Category | Distinguishing signals |
|---|---|
| **e-commerce** | `cart`, `basket`, `checkout`, `payment`, `order`, `shipping`, `invoice`, `product`, `catalog`, `sku`, `inventory`, `wishlist`, `coupon` |
| **blog / content platform** | `post`, `article`, `comment`, `tag`, `category`, `feed`, `rss`, `author`, `draft`, `publish`, `markdown` |
| **social network** | `friend`, `follow`, `like`, `message`, `chat`, `feed`, `timeline`, `notification`, `mention`, `reaction` |
| **admin panel / dashboard** | `admin`, `dashboard`, `report`, `metric`, `analytics`, `audit`, `permission`, `role`, `grant`, `revoke` |
| **REST API service** | `^/api(/v\d+)?(/|$)`, `^/v\d+/`, `swagger`, `openapi`, `graphql` |
| **authentication / SSO** | `oauth`, `saml`, `oidc`, `jwt`, `sso`, `token`, `refresh`, `user`, `login`, `register`, `password`, `reset`, `signin`, `signup` |
| **file / document management** | `file`, `upload`, `download`, `document`, `attachment`, `media`, `share`, `folder`, `version` |
| **scheduling / booking** | `booking`, `reservation`, `appointment`, `schedule`, `calendar`, `slot` |
| **messaging / notification** | `message`, `notification`, `email`, `sms`, `webhook`, `broadcast` |

## Why this approach

Three alternatives we deliberately rejected:

1. **LLM-only classification**. Slow, expensive, non-deterministic, and you have to ship an LLM dependency. The heuristic gives 80% of the value at ~0.5 seconds with no API key required. We layer optional LLM polish ON TOP.
2. **ML classifier trained on labelled repos**. Hard to maintain, hard to debug ("why did it say e-commerce?"), and no good open dataset of labeled repos exists.
3. **Existing GitHub topics / package.json keywords**. Mostly absent or stale. We extract from CODE structure, not metadata.

The pattern approach is auditable (you can see exactly which regex matched which file), extensible (PR a new fingerprint), and bounded (always returns in < 1 second).

## When the matcher gets it wrong

If you find a category misclassification, file an issue with:

1. A minimal reproducible fixture (or link to a public repo)
2. What category it returned
3. What category you expected
4. Which signals you think drove the wrong answer

Common false-positive sources:

- A library repo that documents auth/payment integration in its README → may classify as e-commerce or auth. Fix: tune the regex weights so README signals count less than route signals.
- A monorepo containing multiple distinct apps → only the unified haystack is matched. Fix: run the classifier per-subdirectory.
- A repo with no routes AND no data models → falls back to "unknown" with 0% confidence. Working as designed.

## Adding your own category

See [CONTRIBUTING.md](../CONTRIBUTING.md#1-add-a-category-fingerprint).
