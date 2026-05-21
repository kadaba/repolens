"""app-classifier — pattern-based application functional-category inference.

Point it at a repo on disk, get back:
    - what kind of app it is (e-commerce, blog, admin panel, REST API, etc.)
    - a 2-3 sentence functional description
    - hosting requirements (runtime, web server, databases, ports, env vars)
    - detected HTTP routes + data models
    - optional LLM-refined description (provider-agnostic — bring your own)

Quick start:
    >>> from app_classifier import classify
    >>> result = classify("./my-repo")
    >>> print(result.summary)
    'my-repo · python 3.11 · FastAPI · 23 HTTP route(s) · 5 data model(s) · DB: PostgreSQL'
    >>> print(result.app_category, result.app_category_confidence)
    'e-commerce' 0.78
    >>> print(result.functional_description)
    'my-repo is an e-commerce application. Primary functionality: online shopping. ...'
"""

from app_classifier.classifier import (
    AppDescription,
    DataModel,
    RouteEntry,
    classify,
    classify_async,
    describe_app,                 # alias for classify
    llm_enrich_description,
)
from app_classifier.hosting import (
    HostingReport,
    Signal,
    analyze_hosting_requirements,
)

__version__ = "0.2.0"

__all__ = [
    # Primary API
    "classify",
    "classify_async",
    "describe_app",
    "AppDescription",
    "RouteEntry",
    "DataModel",
    # Hosting subsystem (re-exported for users who only want deployment data)
    "analyze_hosting_requirements",
    "HostingReport",
    "Signal",
    # LLM enrichment hook
    "llm_enrich_description",
    # Agentic mode — opt-in, requires an LLM provider
    "classify_agentic",
    "AgentClassificationResult",
    "AgentStep",
    "SubappClassification",
]

# Agentic API (imported lazily to keep `import app_classifier` cheap for
# users who only need the deterministic path)
from app_classifier.agent import (
    AgentClassificationResult,
    AgentStep,
    SubappClassification,
    classify_agentic,
)
