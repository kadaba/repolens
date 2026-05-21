"""Application classifier — "what does this app do?".

Given a repo, aggregate signals from the hosting analyzer + source-tree
scan, return a structured description with:
  - Functional category (e-commerce, blog, admin, REST API, ...)
  - Confidence + detected features
  - 2-3 sentence functional description
  - Routes inventory (Flask/FastAPI/Django/Express/Spring/Struts)
  - Data models (JPA / SQLAlchemy / Django ORM)
  - Tech stack from `hosting.HostingReport`

Pure static read — no network. Optional LLM synthesis is provider-agnostic:
pass a callable to `classify_async(..., llm_provider=fn)` and we use it for
the polished description. No SDK pinned.
"""
from __future__ import annotations

import json  # noqa: F401  (used by extractor blocks below)
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# A pluggable LLM provider. Users supply ANY async callable that takes the
# prompt + max_tokens + temperature and returns the generated string (or
# None on failure). This decouples app-classifier from any specific SDK
# (OpenAI, Anthropic, Bedrock, local llama.cpp, etc.).
LLMProvider = Callable[..., Awaitable[Optional[str]]]


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


@dataclass
class RouteEntry:
    path: str
    method: str
    handler: str
    source: str           # file path that defined the route


@dataclass
class DataModel:
    name: str
    file: str
    fields_hint: List[str] = field(default_factory=list)
    framework: Optional[str] = None  # 'JPA' | 'SQLAlchemy' | 'Mongoose' | 'Django ORM' | etc.


@dataclass
class AppDescription:
    name: str
    purpose: str                                  # from README or inferred
    runtime: Dict[str, Any]                       # mirrors hosting-requirements runtime
    framework: Optional[str]
    deployment_target: Optional[str]
    routes: List[RouteEntry]                      # public HTTP entry points
    data_models: List[DataModel]
    databases: List[str]                          # name list
    caches_queues: List[str]                      # name list
    notable_files: List[Dict[str, str]]           # README, LICENSE, etc.
    one_line_summary: str                         # composed from all signals
    architecture_summary: str                     # multi-line paragraph
    # Semantic understanding — what the app actually DOES (not just its
    # stack). Derived from route + model + README signals via pattern
    # matching; an LLM enrichment layer rewrites this into a polished
    # natural-language description when an LLM provider is healthy.
    app_category: str = "unknown"                 # "ecommerce" | "blog" | "admin" | ...
    app_category_confidence: float = 0.0          # 0..1 — how sure we are about the category
    functional_description: str = ""              # 2-3 sentences: "What this app does"
    detected_features: List[str] = None           # ["user auth", "shopping cart", "REST API", ...]

    def __post_init__(self):
        if self.detected_features is None:
            self.detected_features = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "purpose": self.purpose,
            "runtime": self.runtime,
            "framework": self.framework,
            "deployment_target": self.deployment_target,
            "routes": [asdict(r) for r in self.routes],
            "data_models": [asdict(m) for m in self.data_models],
            "databases": self.databases,
            "caches_queues": self.caches_queues,
            "notable_files": self.notable_files,
            "one_line_summary": self.one_line_summary,
            "architecture_summary": self.architecture_summary,
            "app_category": self.app_category,
            "app_category_confidence": self.app_category_confidence,
            "functional_description": self.functional_description,
            "detected_features": self.detected_features,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "venv_312", "target", "build",
    "dist", "out", "__pycache__", ".pytest_cache", ".tox", ".gradle",
    ".idea", ".vscode", "coverage", ".cache",
    ".cloned_repos", ".planning", "org_databases",
}


def _walk(root: Path, exts: tuple):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            rel_parts = p.relative_to(root).parts
        except ValueError:
            rel_parts = p.parts
        if any(seg in _SKIP_DIRS for seg in rel_parts):
            continue
        if str(p).lower().endswith(exts):
            yield p


def _read(p: Path, max_bytes: int = 256 * 1024) -> str:
    try:
        with p.open("rb") as f:
            return f.read(max_bytes).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_purpose_from_readme(root: Path) -> str:
    """Pull the first meaningful paragraph from README.md / README.rst."""
    for name in ("README.md", "README.rst", "README", "README.txt"):
        p = root / name
        if not p.exists():
            continue
        text = _read(p)
        # Strip Markdown headers, blockquotes, code blocks; take the first
        # paragraph longer than 40 chars.
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"^#+\s*.*$", "", text, flags=re.MULTILINE)
        text = re.sub(r"^>.*$", "", text, flags=re.MULTILINE)
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text)]
        for para in paragraphs:
            cleaned = re.sub(r"\s+", " ", para).strip()
            if len(cleaned) >= 40:
                return cleaned[:600]
    return ""


# ---------------------------------------------------------------------------
# Route extraction per framework
# ---------------------------------------------------------------------------


_FLASK_ROUTE_RE = re.compile(
    r"@(?:app|bp|blueprint)\.route\s*\(\s*['\"]([^'\"]+)['\"]"
    r"(?:.*?methods\s*=\s*\[([^\]]+)\])?",
    re.DOTALL,
)
_FASTAPI_ROUTE_RE = re.compile(
    r"@(?:app|router)\.(get|post|put|delete|patch|head|options)\s*\(\s*['\"]([^'\"]+)['\"]",
)
_DJANGO_URL_RE = re.compile(
    r"path\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([a-zA-Z_][a-zA-Z0-9_.]*)",
)
_EXPRESS_ROUTE_RE = re.compile(
    r"(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]",
)
_SPRING_MAPPING_RE = re.compile(
    r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\s*\(\s*"
    r"(?:value\s*=\s*)?['\"]([^'\"]+)['\"]",
)
_STRUTS_ACTION_RE = re.compile(
    r'<action\s+name=["\']([^"\']+)["\']\s+(?:method=["\']([^"\']+)["\']\s+)?'
    r'class=["\']([^"\']+)["\']',
)


def _extract_python_routes(root: Path) -> List[RouteEntry]:
    out: List[RouteEntry] = []
    for p in _walk(root, (".py",)):
        text = _read(p)
        # Flask
        for m in _FLASK_ROUTE_RE.finditer(text):
            path_pat = m.group(1)
            methods_raw = (m.group(2) or "GET")
            methods = [t.strip().strip("'\"").upper()
                       for t in methods_raw.split(",") if t.strip()]
            for method in (methods or ["GET"]):
                # The handler name follows on the next def line
                handler_match = re.search(r"def\s+([A-Za-z_]\w*)\s*\(", text[m.end():m.end()+200])
                handler = handler_match.group(1) if handler_match else "?"
                out.append(RouteEntry(path=path_pat, method=method, handler=handler, source=str(p)))
        # FastAPI
        for m in _FASTAPI_ROUTE_RE.finditer(text):
            method, path_pat = m.group(1).upper(), m.group(2)
            handler_match = re.search(r"def\s+([A-Za-z_]\w*)\s*\(", text[m.end():m.end()+200])
            handler = handler_match.group(1) if handler_match else "?"
            out.append(RouteEntry(path=path_pat, method=method, handler=handler, source=str(p)))
        # Django
        if "urls.py" in str(p) or "/urls/" in str(p):
            for m in _DJANGO_URL_RE.finditer(text):
                out.append(RouteEntry(path=m.group(1), method="*", handler=m.group(2), source=str(p)))
    return out


def _extract_js_routes(root: Path) -> List[RouteEntry]:
    out: List[RouteEntry] = []
    for p in _walk(root, (".js", ".ts", ".mjs", ".cjs")):
        text = _read(p)
        for m in _EXPRESS_ROUTE_RE.finditer(text):
            method, path_pat = m.group(1).upper(), m.group(2)
            # Best-effort: handler is the first `function`/arrow name nearby
            handler = "(anonymous)"
            out.append(RouteEntry(path=path_pat, method=method, handler=handler, source=str(p)))
    return out


def _extract_java_routes(root: Path) -> List[RouteEntry]:
    out: List[RouteEntry] = []
    method_anno = {
        "GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
        "DeleteMapping": "DELETE", "PatchMapping": "PATCH",
        "RequestMapping": "*",
    }
    for p in _walk(root, (".java",)):
        text = _read(p)
        for m in _SPRING_MAPPING_RE.finditer(text):
            anno, path_pat = m.group(1), m.group(2)
            method = method_anno.get(anno, "*")
            # Handler name: nearest method definition after the annotation
            after = text[m.end():m.end()+400]
            hm = re.search(r"(?:public|private|protected)\s+\S+\s+([A-Za-z_]\w*)\s*\(", after)
            handler = hm.group(1) if hm else "?"
            out.append(RouteEntry(path=path_pat, method=method, handler=handler, source=str(p)))

    # Struts XML routes (dvja-style)
    for p in _walk(root, (".xml",)):
        if p.name != "struts.xml":
            continue
        text = _read(p)
        for m in _STRUTS_ACTION_RE.finditer(text):
            name, method, klass = m.group(1), (m.group(2) or "execute"), m.group(3)
            handler = f"{klass.split('.')[-1]}.{method}"
            out.append(RouteEntry(path=f"/{name}", method="*", handler=handler, source=str(p)))
    return out


# ---------------------------------------------------------------------------
# Data model extraction
# ---------------------------------------------------------------------------


def _extract_java_entities(root: Path) -> List[DataModel]:
    """Find @Entity-annotated classes — JPA data models."""
    out: List[DataModel] = []
    for p in _walk(root, (".java",)):
        text = _read(p)
        if "@Entity" not in text and "@Table" not in text:
            continue
        # Class name
        cm = re.search(r"public\s+class\s+([A-Za-z_]\w*)", text)
        if not cm:
            continue
        # Field names (best-effort)
        fields = []
        for fm in re.finditer(r"(?:private|protected)\s+[A-Za-z_]\w*(?:<[^>]+>)?\s+([A-Za-z_]\w*)\s*[=;]", text):
            fields.append(fm.group(1))
            if len(fields) >= 20:
                break
        out.append(DataModel(name=cm.group(1), file=str(p),
                              fields_hint=fields, framework="JPA"))
    return out


def _extract_python_models(root: Path) -> List[DataModel]:
    """SQLAlchemy models (`class X(Base):`), Django models (`class X(models.Model):`)."""
    out: List[DataModel] = []
    for p in _walk(root, (".py",)):
        text = _read(p)
        for m in re.finditer(
            r"^class\s+([A-Za-z_]\w*)\s*\(\s*"
            r"(?:[A-Za-z_]\w*\.)?(Base|Model|db\.Model|models\.Model)\s*[\),]",
            text, re.MULTILINE,
        ):
            framework = "SQLAlchemy" if "Base" in m.group(2) else "Django ORM"
            # Find Column(...) / models.X fields near the class
            class_start = m.end()
            class_block = text[class_start:class_start + 2000]
            fields = []
            for fm in re.finditer(
                r"\n\s+([a-zA-Z_]\w*)\s*=\s*(?:Column|models\.[A-Z]\w+)",
                class_block,
            ):
                fields.append(fm.group(1))
                if len(fields) >= 20:
                    break
            out.append(DataModel(name=m.group(1), file=str(p),
                                  fields_hint=fields, framework=framework))
    return out


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _compose_summary(name: str, hosting, routes: List[RouteEntry],
                     models: List[DataModel]) -> str:
    """Build a one-line, deterministic summary from the structured signals."""
    parts = [name]
    if hosting.runtime.get("language"):
        rt = hosting.runtime["language"]
        if hosting.runtime.get("version"):
            rt += f" {hosting.runtime['version']}"
        parts.append(rt)
    if hosting.web_server.get("framework"):
        parts.append(hosting.web_server["framework"])
    if routes:
        parts.append(f"{len(routes)} HTTP route(s)")
    if models:
        parts.append(f"{len(models)} data model(s)")
    if hosting.databases:
        parts.append("DB: " + ", ".join(sorted({d["name"] for d in hosting.databases})))
    return " · ".join(parts)


def _compose_architecture(hosting, routes, models, purpose) -> str:
    """Multi-line paragraph synthesizing everything we know."""
    lines: List[str] = []
    rt = hosting.runtime.get("language", "?")
    rt_ver = hosting.runtime.get("version") or hosting.runtime.get("version_spec") or ""
    fw = hosting.web_server.get("framework") or "(framework unknown)"
    deploy = hosting.web_server.get("deployment_target") or "(deployment target unknown)"
    lines.append(
        f"This is a {rt} {rt_ver} application built on {fw}, "
        f"deployed as {deploy}."
    )
    if purpose:
        lines.append(f"From the project README: {purpose}")
    if routes:
        methods = {r.method for r in routes}
        lines.append(
            f"Exposes {len(routes)} HTTP route(s) using {', '.join(sorted(methods))} method(s)."
        )
        if any(r.path.startswith("/admin") or "admin" in r.path.lower() for r in routes):
            lines.append("Has admin-scoped routes — review authorization carefully.")
    if models:
        frameworks = sorted({m.framework for m in models if m.framework})
        lines.append(
            f"Persists data via {', '.join(frameworks) or 'unknown ORM'} "
            f"across {len(models)} entity/model class(es)."
        )
    if hosting.databases:
        db_names = sorted({d["name"] for d in hosting.databases})
        lines.append(f"Database tier: {', '.join(db_names)}.")
    if hosting.caches_queues:
        cq = sorted({c["name"] for c in hosting.caches_queues})
        lines.append(f"Auxiliary services: {', '.join(cq)}.")
    if hosting.env_vars_required:
        lines.append(
            f"Requires {len(hosting.env_vars_required)} environment variable(s) at runtime "
            f"(includes: {', '.join(v['name'] for v in hosting.env_vars_required[:5])}…)."
        )
    return " ".join(lines)


# ---------------------------------------------------------------------------
# Semantic inference — what does this app DO?
# ---------------------------------------------------------------------------


# Route-pattern + model-name fingerprints that signal an app category.
# Each entry: signals = list of (regex, weight) tuples; threshold = min
# score to claim the category with at least medium confidence (0.5+).
# Weights add across signals; we don't double-count signals from the same
# bucket (a route called both `/cart` and `/cart/items` only counts once).
_CATEGORY_FINGERPRINTS = [
    {
        "name": "e-commerce",
        "feature_label": "online shopping",
        "signals": [
            (r"\b(?:cart|basket|checkout|payment|order|shipping|invoice)\b", 3),
            (r"\b(?:product|catalog|sku|inventory)\b", 2),
            (r"\b(?:wishlist|coupon|discount|promo)\b", 1),
        ],
    },
    {
        "name": "blog / content platform",
        "feature_label": "publishing",
        "signals": [
            (r"\b(?:post|article|comment|tag|category|feed|rss)\b", 2),
            (r"\b(?:author|draft|publish|markdown)\b", 1),
        ],
    },
    {
        "name": "social network",
        "feature_label": "social interaction",
        "signals": [
            (r"\b(?:friend|follow|like|message|chat|feed|timeline)\b", 3),
            (r"\b(?:notification|mention|reaction)\b", 1),
        ],
    },
    {
        "name": "admin panel / dashboard",
        "feature_label": "internal admin",
        "signals": [
            (r"\b(?:admin|dashboard|report|metric|analytics|audit)\b", 2),
            (r"\b(?:permission|role|grant|revoke)\b", 1),
        ],
    },
    {
        "name": "REST API service",
        "feature_label": "API backend",
        "signals": [
            (r"^/api(?:/v\d+)?(?:/|$)", 3),
            (r"^/v\d+/", 2),
            (r"\b(?:swagger|openapi|graphql)\b", 1),
        ],
    },
    {
        "name": "authentication / SSO",
        "feature_label": "identity provider",
        "signals": [
            (r"\b(?:oauth|saml|oidc|jwt|sso|token|refresh)\b", 3),
            (r"\b(?:user|login|register|password|reset|signin|signup)\b", 1),
        ],
    },
    {
        "name": "file / document management",
        "feature_label": "file storage",
        "signals": [
            (r"\b(?:file|upload|download|document|attachment|media)\b", 2),
            (r"\b(?:share|folder|version)\b", 1),
        ],
    },
    {
        "name": "scheduling / booking",
        "feature_label": "appointment booking",
        "signals": [
            (r"\b(?:booking|reservation|appointment|schedule|calendar|slot)\b", 3),
        ],
    },
    {
        "name": "messaging / notification",
        "feature_label": "messaging",
        "signals": [
            (r"\b(?:message|notification|email|sms|webhook|broadcast)\b", 2),
        ],
    },
]


def _infer_app_category(routes: List["RouteEntry"], models: List["DataModel"],
                        purpose: str) -> Dict[str, Any]:
    """Pattern-match across routes + model names + README purpose to
    infer what kind of app this is. Returns dict with category, score,
    confidence, matched_features."""
    # Build a single haystack of all the signals we have
    haystack_parts: List[str] = []
    for r in routes:
        if r.path:
            haystack_parts.append(r.path.lower())
        if getattr(r, "handler", None):
            haystack_parts.append(r.handler.lower())
    for m in models:
        haystack_parts.append(m.name.lower())
        for f in (m.fields_hint or []):
            haystack_parts.append(f.lower())
    if purpose:
        haystack_parts.append(purpose.lower()[:2000])
    haystack = " | ".join(haystack_parts)

    scores: List[Dict[str, Any]] = []
    detected_features: List[str] = []
    for fp in _CATEGORY_FINGERPRINTS:
        matched_signals = 0
        matched_examples = set()
        for pattern, weight in fp["signals"]:
            ms = re.findall(pattern, haystack, re.IGNORECASE)
            if ms:
                matched_signals += weight
                # Capture unique terms for the feature list
                for m_ in ms[:3]:
                    if isinstance(m_, tuple):
                        m_ = " ".join(m_)
                    matched_examples.add(m_.strip().lower())
        if matched_signals > 0:
            scores.append({
                "name": fp["name"],
                "feature_label": fp["feature_label"],
                "score": matched_signals,
                "examples": sorted(matched_examples)[:5],
            })
            if matched_signals >= 2:
                detected_features.append(fp["feature_label"])

    scores.sort(key=lambda x: x["score"], reverse=True)

    if not scores:
        return {
            "category": "unknown",
            "confidence": 0.0,
            "detected_features": detected_features,
            "all_matches": [],
        }

    # Confidence: top score / sum of top-2 (so a clear winner gives high
    # confidence, a tie gives medium). Capped at 0.95 because we never
    # claim certainty without LLM semantic verification.
    top = scores[0]
    second = scores[1]["score"] if len(scores) > 1 else 0
    if top["score"] + second == 0:
        confidence = 0.0
    else:
        confidence = round(min(0.95, top["score"] / (top["score"] + second + 0.5)), 2)
        # Boost confidence when the top signal is very high in absolute terms
        if top["score"] >= 5:
            confidence = round(min(0.95, confidence + 0.15), 2)
    return {
        "category": top["name"],
        "confidence": confidence,
        "detected_features": detected_features,
        "all_matches": scores[:3],  # top-3 for the UI
    }


def _compose_functional_description(name: str, category_info: Dict[str, Any],
                                     routes: List["RouteEntry"],
                                     models: List["DataModel"],
                                     purpose: str) -> str:
    """Build a 2-3 sentence "what this app does" description from the
    structured signals. Deterministic — no LLM required. Falls back to
    a frank "purpose unclear" sentence when we couldn't match patterns."""
    category = category_info.get("category", "unknown")
    confidence = category_info.get("confidence", 0.0)
    features = category_info.get("detected_features", [])

    sentences: List[str] = []

    if category != "unknown" and confidence >= 0.4:
        confidence_qualifier = "appears to be" if confidence < 0.7 else "is"
        sentences.append(f"{name} {confidence_qualifier} a {category} application.")
    elif category != "unknown":
        sentences.append(f"{name} has signals of being a {category} application "
                         f"(low confidence — pattern match was weak).")
    else:
        sentences.append(
            f"{name}'s functional category couldn't be inferred from routes + "
            f"models alone. Review the README and route handlers manually."
        )

    # Sentence 2: what it does, drawn from detected features
    if features:
        unique_features = list(dict.fromkeys(features))[:4]
        sentences.append(f"Primary functionality: {', '.join(unique_features)}.")

    # Sentence 3: anchor with concrete signals (route + model counts)
    concrete_bits = []
    if models:
        model_names = sorted({m.name for m in models})[:5]
        concrete_bits.append(f"entities like {', '.join(model_names)}")
    if routes:
        # Highlight any auth-related route as a fingerprint of who uses it
        has_auth = any(
            re.search(r"login|signin|register|signup|auth", r.path or "", re.IGNORECASE)
            for r in routes
        )
        has_admin = any("admin" in (r.path or "").lower() for r in routes)
        scope_bits = []
        if has_auth:
            scope_bits.append("authenticated users")
        if has_admin:
            scope_bits.append("administrators")
        if scope_bits:
            concrete_bits.append(f"serving {' and '.join(scope_bits)}")
    if concrete_bits:
        sentences.append(f"It models {' '.join(concrete_bits)}.")

    # If purpose came from README, append a separate sentence so the
    # human-written intent is preserved verbatim (truncated).
    if purpose and len(purpose) > 40:
        truncated = purpose[:200].rstrip()
        if len(purpose) > 200:
            truncated += "…"
        sentences.append(f"From the README: \"{truncated}\"")

    return " ".join(sentences)


def _build_llm_prompt(description: "AppDescription") -> str:
    """Compose the prompt sent to whichever LLM provider the user supplies.
    Exposed separately so users running custom prompts can grab the same
    structural-context block we feed to their LLM."""
    routes_snippet = "\n".join(
        f"  {r.method or 'GET'} {r.path}" for r in description.routes[:25]
    ) or "  (no routes detected)"
    models_snippet = "\n".join(
        f"  {m.name}: {', '.join((m.fields_hint or [])[:8])}"
        for m in description.data_models[:10]
    ) or "  (no models detected)"
    return (
        "You are reading the structural signals of a software project and "
        "writing a 2-3 sentence functional description. Be specific. Do not "
        "invent features — only describe what the structural evidence "
        "supports.\n\n"
        f"Project name: {description.name}\n"
        f"Language: {description.runtime.get('language', '?')}\n"
        f"Framework: {description.framework or '?'}\n"
        f"Heuristic category: {description.app_category} "
        f"(confidence {description.app_category_confidence:.0%})\n"
        f"Detected features: {', '.join(description.detected_features) or '(none)'}\n"
        f"Databases: {', '.join(description.databases) or '(none)'}\n\n"
        f"HTTP routes (first 25):\n{routes_snippet}\n\n"
        f"Data models (first 10):\n{models_snippet}\n\n"
        f"README purpose excerpt: \"{(description.purpose or '')[:300]}\"\n\n"
        "Write 2-3 sentences describing WHAT THIS APP DOES, who it's for, "
        "and its core functionality. Use plain prose, no markdown, no bullet "
        "points. Avoid restating the language/framework — focus on purpose "
        "and user-facing functionality. If the evidence is thin, say so."
    )


async def llm_enrich_description(
    description: "AppDescription",
    llm_provider: Optional[LLMProvider] = None,
    max_tokens: int = 400,
) -> Optional[str]:
    """Optional LLM rewrite of the functional description.

    `llm_provider` is YOUR async callable. It receives the prompt as the
    `prompt` kwarg plus `max_tokens` + `temperature`, and returns the
    generated string (or None on any failure). Example shims:

        # OpenAI
        async def my_provider(prompt, max_tokens=400, temperature=0.2):
            client = openai.AsyncOpenAI()
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens, temperature=temperature,
            )
            return resp.choices[0].message.content

        # Anthropic
        async def my_provider(prompt, max_tokens=400, temperature=0.2):
            client = anthropic.AsyncAnthropic()
            resp = await client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=max_tokens, temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text

    Returns None on any failure — caller should fall back to the
    deterministic description (`description.functional_description`).
    """
    if llm_provider is None:
        return None
    prompt = _build_llm_prompt(description)
    try:
        content = await llm_provider(prompt=prompt, max_tokens=max_tokens, temperature=0.2)
    except Exception as exc:
        logger.debug(f"llm_enrich_description: provider raised: {exc}")
        return None
    if not content:
        return None
    content = content.strip()
    # Hallucination guard: refuse if heuristic confidence was already
    # low AND the model wrote a long confident-sounding response.
    if description.app_category_confidence < 0.3 and len(content) > 400:
        return None
    if len(content) < 40:
        return None
    return content


def describe_app(repo_root: str) -> AppDescription:
    """Run all extractors and produce a structured AppDescription.

    Equivalent to `classify(repo_root)`. Sync — no LLM step.
    """
    from app_classifier.hosting import analyze_hosting_requirements
    root = Path(repo_root)
    hosting = analyze_hosting_requirements(repo_root)

    # Routes — dispatch by detected language
    lang = hosting.runtime.get("language")
    routes: List[RouteEntry] = []
    if lang == "python":
        routes = _extract_python_routes(root)
    elif lang == "java":
        routes = _extract_java_routes(root)
    elif lang == "javascript":
        routes = _extract_js_routes(root)
    else:
        # Try all, in case multi-language repo
        routes = (_extract_python_routes(root) + _extract_java_routes(root)
                  + _extract_js_routes(root))

    # Data models — same dispatch
    models: List[DataModel] = []
    if lang == "java":
        models = _extract_java_entities(root)
    elif lang == "python":
        models = _extract_python_models(root)
    else:
        models = _extract_java_entities(root) + _extract_python_models(root)

    purpose = _extract_purpose_from_readme(root)

    # Notable files
    notable: List[Dict[str, str]] = []
    for fname in ("README.md", "README.rst", "LICENSE", "CHANGELOG.md", "CONTRIBUTING.md"):
        p = root / fname
        if p.exists():
            notable.append({"name": fname, "source": str(p)})

    name = root.name
    one_line = _compose_summary(name, hosting, routes, models)
    architecture = _compose_architecture(hosting, routes, models, purpose)

    # Semantic layer — what this app DOES, not just its tech.
    category_info = _infer_app_category(routes, models, purpose or "")
    functional = _compose_functional_description(
        name, category_info, routes, models, purpose or "",
    )

    return AppDescription(
        name=name,
        purpose=purpose or "(no README description found)",
        runtime=hosting.runtime,
        framework=hosting.web_server.get("framework"),
        deployment_target=hosting.web_server.get("deployment_target"),
        routes=routes,
        data_models=models,
        databases=sorted({d["name"] for d in hosting.databases}),
        caches_queues=sorted({c["name"] for c in hosting.caches_queues}),
        notable_files=notable,
        one_line_summary=one_line,
        architecture_summary=architecture,
        app_category=category_info.get("category", "unknown"),
        app_category_confidence=category_info.get("confidence", 0.0),
        functional_description=functional,
        detected_features=category_info.get("detected_features", []),
    )


# ---------------------------------------------------------------------------
# Friendly aliases — primary public API
# ---------------------------------------------------------------------------


def classify(repo_root: str) -> AppDescription:
    """Classify the application at `repo_root`.

    Sync. No network, no LLM. Returns a structured AppDescription with:
      - app_category + app_category_confidence + detected_features
      - functional_description (2-3 sentence deterministic prose)
      - routes / data_models / databases / framework / runtime
      - one_line_summary + architecture_summary

    >>> result = classify("./my-repo")
    >>> result.app_category, result.app_category_confidence
    ('e-commerce', 0.78)
    """
    return describe_app(repo_root)


async def classify_async(
    repo_root: str,
    llm_provider: Optional[LLMProvider] = None,
) -> AppDescription:
    """Same as `classify`, but if `llm_provider` is supplied, AND it returns
    something useful, swap the deterministic `functional_description` for
    the LLM-refined version.

    The LLM provider is YOUR callable (see `llm_enrich_description`'s
    docstring for OpenAI / Anthropic / local-model shim examples). On any
    LLM failure (timeout, parse error, hallucination guard, no provider
    supplied), the deterministic description stays.
    """
    description = describe_app(repo_root)
    if llm_provider is not None:
        try:
            enriched = await llm_enrich_description(
                description, llm_provider=llm_provider,
            )
            if enriched:
                description.functional_description = enriched
        except Exception as exc:
            logger.debug(f"classify_async: LLM step failed: {exc}")
    return description
