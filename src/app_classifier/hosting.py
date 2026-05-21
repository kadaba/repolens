"""Hosting-requirements analyzer.

Given a repo on disk, infer where it expects to be hosted: runtime version,
web server, databases, caches, container metadata, exposed ports, env vars,
TLS, cloud-provider SDK signals. The signals come from purely static files
(pom.xml, package.json, Dockerfile, k8s manifests, application.properties,
etc.) plus shallow code grep for things like `process.env.X` references.

This is a SIGNAL-GATHERING analyzer, not a deployment validator — every
finding includes the source file path so a reviewer can trace it back.
Findings the analyzer is uncertain about are tagged with a confidence
level; the consumer decides whether to surface them.

Design constraints:
  * Pure read — never writes to the repo.
  * Bounded scan — caps file count + per-file read size to stay fast on
    huge monorepos.
  * Best-effort — failures on individual files don't kill the whole pass.
  * No network — every signal comes from on-disk content.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


@dataclass
class Signal:
    """One piece of evidence supporting a hosting finding."""
    source: str                 # file path relative to repo root
    snippet: str                # matched text or summary
    confidence: str = "high"    # high | medium | low


@dataclass
class HostingReport:
    runtime: Dict[str, Any] = field(default_factory=dict)
    web_server: Dict[str, Any] = field(default_factory=dict)
    databases: List[Dict[str, Any]] = field(default_factory=list)
    caches_queues: List[Dict[str, Any]] = field(default_factory=list)
    container: Dict[str, Any] = field(default_factory=dict)
    ports: List[Dict[str, Any]] = field(default_factory=list)
    env_vars_required: List[Dict[str, Any]] = field(default_factory=list)
    cloud_provider: Dict[str, Any] = field(default_factory=dict)
    tls: Dict[str, Any] = field(default_factory=dict)
    build_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    web_server_vulnerabilities: List[Dict[str, Any]] = field(default_factory=list)
    signals: List[Signal] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "runtime": self.runtime,
            "web_server": self.web_server,
            "databases": self.databases,
            "caches_queues": self.caches_queues,
            "container": self.container,
            "ports": sorted(self.ports, key=lambda p: p.get("port", 0)),
            "env_vars_required": self.env_vars_required,
            "cloud_provider": self.cloud_provider,
            "tls": self.tls,
            "build_artifacts": self.build_artifacts,
            "web_server_vulnerabilities": self.web_server_vulnerabilities,
            "summary": self.summary,
            "signals": [{"source": s.source, "snippet": s.snippet, "confidence": s.confidence}
                        for s in self.signals],
        }


# ---------------------------------------------------------------------------
# File walker
# ---------------------------------------------------------------------------


_INTERESTING_NAMES = {
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg",
    "Pipfile", "Pipfile.lock", "poetry.lock", "runtime.txt",
    "go.mod", "go.sum", "Gemfile", "Gemfile.lock", "composer.json",
    "Cargo.toml", "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "Procfile", "app.json", "app.yaml", "appspec.yml",
    "vercel.json", "netlify.toml", "now.json",
    "web.xml", "applicationContext.xml", "persistence.xml",
    "application.properties", "application.yml", "application.yaml",
    "struts.xml", "spring.xml", "context.xml", "server.xml",
    ".nvmrc", ".node-version", ".python-version", ".ruby-version", ".java-version",
    "nginx.conf", "apache2.conf", "httpd.conf",
    "manifest.yml",  # cloud foundry
    "buildspec.yml",  # AWS CodeBuild
    "cloudbuild.yaml",  # GCP
    "Chart.yaml", "values.yaml",  # Helm
}

# Patterns for additional matches (filenames that match a regex)
_INTERESTING_PATTERNS = (
    re.compile(r"\.tf$"),                    # Terraform
    re.compile(r"^k8s/.*\.ya?ml$"),          # k8s manifests under k8s/
    re.compile(r"^kubernetes/.*\.ya?ml$"),
    re.compile(r"^deployment.*\.ya?ml$"),
    re.compile(r"^helm/.*\.ya?ml$"),
    re.compile(r"\.env(\..+)?$"),            # .env, .env.example, .env.local
)


_SKIP_DIRS = {
    "node_modules", ".git", ".svn", ".hg", "dist", "build", "target",
    "out", "__pycache__", ".pytest_cache", ".tox", ".venv", "venv",
    "vendor", ".gradle", ".idea", ".vscode", "coverage", ".next",
    ".nuxt", "Pods", ".cache",
}


_MAX_FILES = 800                # cap files scanned to keep this fast
_MAX_FILE_BYTES = 256 * 1024    # cap individual file size to 256 KB


def _walk_interesting_files(root: Path) -> List[Path]:
    """Return paths to manifest/config files we care about, capped to _MAX_FILES.

    Skip-dir matching is RELATIVE to `root` — so a user passing
    `.cloned_repos/dvja/` as their target repo still gets analyzed even
    though `.cloned_repos` is also a skip-dir name. Only skip-dirs *under*
    the root count.
    """
    found: List[Path] = []
    if not root.exists():
        return found
    for p in root.rglob("*"):
        if len(found) >= _MAX_FILES:
            break
        if not p.is_file():
            continue
        # Check skip-dirs only against path segments BELOW root
        try:
            rel_parts = p.relative_to(root).parts
        except ValueError:
            rel_parts = p.parts
        if any(seg in _SKIP_DIRS for seg in rel_parts):
            continue
        name = p.name
        if name in _INTERESTING_NAMES:
            found.append(p)
            continue
        rel = "/".join(rel_parts)
        if any(pat.search(rel) for pat in _INTERESTING_PATTERNS):
            found.append(p)
    return found


def _read_text(p: Path, max_bytes: int = _MAX_FILE_BYTES) -> str:
    try:
        with p.open("rb") as f:
            return f.read(max_bytes).decode("utf-8", errors="replace")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Java / JVM detectors
# ---------------------------------------------------------------------------


_POM_VERSION_RE = re.compile(
    r"<(?:java\.version|maven\.compiler\.source|maven\.compiler\.target|source|target)>"
    r"\s*([0-9.]+)\s*</",
    re.IGNORECASE,
)
_POM_ARTIFACT_RE = re.compile(
    r"<artifactId>\s*([a-zA-Z0-9._-]+)\s*</artifactId>",
)
_GRADLE_JAVA_RE = re.compile(
    r"(?:sourceCompatibility|targetCompatibility)\s*[=:]?\s*['\"]?(?:JavaVersion\.VERSION_)?([\d.]+)",
)


def _analyze_pom(p: Path, txt: str, report: HostingReport) -> None:
    rel = str(p)
    # Java version
    m = _POM_VERSION_RE.search(txt)
    if m and "version" not in report.runtime:
        report.runtime["language"] = "java"
        report.runtime["version"] = m.group(1)
        report.signals.append(Signal(rel, f"java version: {m.group(1)}"))

    artifacts = set(_POM_ARTIFACT_RE.findall(txt))

    # Web framework / server inference from artifacts
    if any(a.startswith("struts") for a in artifacts):
        report.web_server.update(
            framework="Struts 2",
            deployment_target="Tomcat / Jetty / WildFly (servlet container)",
            packaging="WAR",
        )
        report.signals.append(Signal(rel, "Struts 2 artifacts → servlet container"))
    if any(a.startswith("spring-boot") for a in artifacts):
        report.web_server.update(
            framework="Spring Boot",
            deployment_target="Standalone fat-jar (embedded Tomcat/Jetty/Undertow)",
            packaging="JAR",
        )
        report.signals.append(Signal(rel, "spring-boot artifacts → embedded server fat-jar"))
    elif any(a.startswith("spring-") for a in artifacts) and "framework" not in report.web_server:
        report.web_server.update(
            framework="Spring (classic)",
            deployment_target="Tomcat / Jetty / WildFly (servlet container)",
        )
        report.signals.append(Signal(rel, "spring-* artifacts (non-boot) → external container"))
    if any(a.startswith("jetty") for a in artifacts):
        report.web_server.setdefault("deployment_target", "Jetty")
        report.signals.append(Signal(rel, "jetty artifact dependency"))
    if "tomcat-embed-core" in artifacts:
        report.web_server.setdefault("deployment_target", "Embedded Tomcat")
        report.signals.append(Signal(rel, "embedded Tomcat dependency"))

    # ORM / DB drivers
    if "hibernate-core" in artifacts or "hibernate-entitymanager" in artifacts or "hibernate-annotations" in artifacts:
        report.databases.append({"name": "Hibernate ORM", "type": "orm", "source": rel})
        report.signals.append(Signal(rel, "Hibernate ORM dependency"))
    if "mysql-connector-java" in artifacts or "mysql-connector-j" in artifacts:
        report.databases.append({"name": "MySQL", "type": "rdbms", "driver": "mysql-connector-java", "source": rel})
    if any(a == "postgresql" for a in artifacts):
        report.databases.append({"name": "PostgreSQL", "type": "rdbms", "driver": "postgresql", "source": rel})
    if "h2" in artifacts:
        report.databases.append({"name": "H2", "type": "embedded_rdbms", "driver": "h2", "source": rel})
        report.signals.append(Signal(rel, "H2 — embedded; suitable for dev/test only"))
    if "ojdbc8" in artifacts or "ojdbc6" in artifacts:
        report.databases.append({"name": "Oracle", "type": "rdbms", "source": rel})
    if any(a.startswith("mongo") for a in artifacts):
        report.databases.append({"name": "MongoDB", "type": "document", "source": rel})

    # Build artifact (war vs jar) from <packaging>
    pkg = re.search(r"<packaging>\s*(war|jar|ear|pom)\s*</packaging>", txt, re.IGNORECASE)
    if pkg:
        report.build_artifacts.append({"type": pkg.group(1).lower(), "source": rel})


def _analyze_gradle(p: Path, txt: str, report: HostingReport) -> None:
    rel = str(p)
    m = _GRADLE_JAVA_RE.search(txt)
    if m and "version" not in report.runtime:
        report.runtime["language"] = "java"
        report.runtime["version"] = m.group(1)
        report.signals.append(Signal(rel, f"gradle java version: {m.group(1)}"))
    if "spring-boot" in txt or "org.springframework.boot" in txt:
        report.web_server.setdefault("framework", "Spring Boot")
        report.web_server.setdefault("deployment_target", "Standalone fat-jar (embedded server)")
        report.signals.append(Signal(rel, "Spring Boot plugin in gradle"))


# ---------------------------------------------------------------------------
# Python detectors
# ---------------------------------------------------------------------------


def _analyze_pyproject(p: Path, txt: str, report: HostingReport) -> None:
    rel = str(p)
    # requires-python = ">=3.10"
    m = re.search(r"requires-python\s*=\s*['\"]([^'\"]+)['\"]", txt)
    if m and "version" not in report.runtime:
        report.runtime["language"] = "python"
        report.runtime["version_spec"] = m.group(1)
        report.signals.append(Signal(rel, f"requires-python: {m.group(1)}"))
    _python_dep_signals(rel, txt, report)


def _analyze_requirements_txt(p: Path, txt: str, report: HostingReport) -> None:
    rel = str(p)
    if "language" not in report.runtime:
        report.runtime["language"] = "python"
        report.signals.append(Signal(rel, "requirements.txt — Python project"))
    _python_dep_signals(rel, txt, report)


def _python_dep_signals(source: str, txt: str, report: HostingReport) -> None:
    """Detect web frameworks, DB drivers, caches based on Python deps."""
    deps = {ln.split("==")[0].split(">=")[0].split("<")[0].split("[")[0].strip().lower()
            for ln in txt.splitlines() if ln.strip() and not ln.strip().startswith("#")}
    # Web frameworks
    if "fastapi" in deps or "starlette" in deps:
        report.web_server.setdefault("framework", "FastAPI")
        report.web_server.setdefault("deployment_target", "ASGI server (uvicorn / hypercorn / daphne)")
        report.signals.append(Signal(source, "FastAPI dep → ASGI"))
    elif "flask" in deps:
        report.web_server.setdefault("framework", "Flask")
        report.web_server.setdefault("deployment_target", "WSGI server (gunicorn / uwsgi / waitress)")
        report.signals.append(Signal(source, "Flask dep → WSGI"))
    elif "django" in deps:
        report.web_server.setdefault("framework", "Django")
        report.web_server.setdefault("deployment_target", "WSGI/ASGI server (gunicorn / daphne)")
        report.signals.append(Signal(source, "Django dep"))
    if "gunicorn" in deps:
        report.web_server.setdefault("runner", "gunicorn")
    if "uvicorn" in deps:
        report.web_server.setdefault("runner", "uvicorn")
    # DB drivers
    if "psycopg2" in deps or "psycopg2-binary" in deps or "psycopg" in deps:
        report.databases.append({"name": "PostgreSQL", "type": "rdbms", "driver": "psycopg", "source": source})
    if "pymysql" in deps or "mysqlclient" in deps:
        report.databases.append({"name": "MySQL", "type": "rdbms", "driver": "pymysql/mysqlclient", "source": source})
    if "sqlalchemy" in deps:
        report.databases.append({"name": "SQLAlchemy ORM", "type": "orm", "source": source})
    if "pymongo" in deps or "motor" in deps:
        report.databases.append({"name": "MongoDB", "type": "document", "source": source})
    # Caches / queues
    if "redis" in deps or "aioredis" in deps:
        report.caches_queues.append({"name": "Redis", "type": "cache", "source": source})
    if "celery" in deps:
        report.caches_queues.append({"name": "Celery", "type": "queue", "broker_hint": "Redis or RabbitMQ", "source": source})
    if "pika" in deps or "aio-pika" in deps:
        report.caches_queues.append({"name": "RabbitMQ", "type": "queue", "source": source})
    if "kafka-python" in deps or "confluent-kafka" in deps:
        report.caches_queues.append({"name": "Kafka", "type": "queue", "source": source})
    if "elasticsearch" in deps:
        report.caches_queues.append({"name": "Elasticsearch", "type": "search", "source": source})
    # Cloud SDKs
    if "boto3" in deps or "aioboto3" in deps:
        report.cloud_provider.setdefault("aws", []).append({"signal": "boto3", "source": source})
    if any(d.startswith("google-cloud-") for d in deps):
        report.cloud_provider.setdefault("gcp", []).append({"signal": "google-cloud-*", "source": source})
    if any(d.startswith("azure-") for d in deps):
        report.cloud_provider.setdefault("azure", []).append({"signal": "azure-*", "source": source})


# ---------------------------------------------------------------------------
# Node / JS detectors
# ---------------------------------------------------------------------------


def _analyze_package_json(p: Path, txt: str, report: HostingReport) -> None:
    rel = str(p)
    try:
        pkg = json.loads(txt)
    except Exception:
        return
    if "language" not in report.runtime:
        report.runtime["language"] = "javascript"
    engines = pkg.get("engines", {}) or {}
    if isinstance(engines, dict) and engines.get("node"):
        report.runtime["version_spec"] = engines["node"]
        report.signals.append(Signal(rel, f"engines.node: {engines['node']}"))
    deps = dict(pkg.get("dependencies", {}) or {})
    deps.update(pkg.get("devDependencies", {}) or {})
    deps_lc = {k.lower() for k in deps}
    if "express" in deps_lc:
        report.web_server.setdefault("framework", "Express")
        report.web_server.setdefault("deployment_target", "Node process (PM2 / systemd / container)")
        report.signals.append(Signal(rel, "express in deps"))
    if "fastify" in deps_lc:
        report.web_server.setdefault("framework", "Fastify")
        report.signals.append(Signal(rel, "fastify in deps"))
    if "next" in deps_lc:
        report.web_server.setdefault("framework", "Next.js")
        report.web_server.setdefault("deployment_target", "Vercel / Node server / static export")
        report.signals.append(Signal(rel, "next in deps"))
    if "@nestjs/core" in deps_lc:
        report.web_server.setdefault("framework", "NestJS")
    if any(d in deps_lc for d in ("pg", "@types/pg")):
        report.databases.append({"name": "PostgreSQL", "type": "rdbms", "driver": "pg", "source": rel})
    if any(d in deps_lc for d in ("mysql", "mysql2")):
        report.databases.append({"name": "MySQL", "type": "rdbms", "source": rel})
    if any(d in deps_lc for d in ("mongoose", "mongodb")):
        report.databases.append({"name": "MongoDB", "type": "document", "source": rel})
    if any(d in deps_lc for d in ("redis", "ioredis")):
        report.caches_queues.append({"name": "Redis", "type": "cache", "source": rel})
    if "aws-sdk" in deps_lc or any(d.startswith("@aws-sdk/") for d in deps_lc):
        report.cloud_provider.setdefault("aws", []).append({"signal": "aws-sdk", "source": rel})


# ---------------------------------------------------------------------------
# PHP detectors — composer.json + standalone .php source
# ---------------------------------------------------------------------------


def _analyze_composer_json(p: Path, txt: str, report: HostingReport) -> None:
    """Detect PHP runtime + framework + ORM from composer.json."""
    rel = str(p)
    try:
        data = json.loads(txt)
    except Exception:
        return
    if "language" not in report.runtime:
        report.runtime["language"] = "php"
        report.signals.append(Signal(rel, "composer.json — PHP project"))
    require = {**(data.get("require") or {}), **(data.get("require-dev") or {})}
    php_constraint = require.get("php")
    if php_constraint and "version_spec" not in report.runtime:
        report.runtime["version_spec"] = php_constraint
        report.signals.append(Signal(rel, f"composer php: {php_constraint}"))
    # Frameworks — most specific first
    if "laravel/framework" in require:
        report.web_server.setdefault("framework", "Laravel")
        report.web_server.setdefault("deployment_target", "PHP-FPM behind nginx/apache (or Octane standalone)")
        report.signals.append(Signal(rel, "laravel/framework"))
    elif any(k.startswith("symfony/") for k in require):
        report.web_server.setdefault("framework", "Symfony")
        report.web_server.setdefault("deployment_target", "PHP-FPM behind nginx/apache")
        report.signals.append(Signal(rel, "symfony/* deps"))
    elif "slim/slim" in require:
        report.web_server.setdefault("framework", "Slim")
        report.web_server.setdefault("deployment_target", "PHP-FPM behind nginx/apache")
    elif "cakephp/cakephp" in require:
        report.web_server.setdefault("framework", "CakePHP")
    elif "yiisoft/yii2" in require:
        report.web_server.setdefault("framework", "Yii 2")
    elif "codeigniter4/framework" in require:
        report.web_server.setdefault("framework", "CodeIgniter 4")
    # ORM / DB drivers
    if "doctrine/orm" in require or "doctrine/dbal" in require:
        report.databases.append({"name": "Doctrine ORM", "type": "orm", "source": rel})
    if "illuminate/database" in require:
        report.databases.append({"name": "Eloquent ORM", "type": "orm", "source": rel})


def _detect_php_from_source(root: Path, report: HostingReport) -> None:
    """Fallback PHP detection — looks for raw .php files when no composer.json
    was found. Covers DVWA, WordPress, Drupal, and other pre-composer apps."""
    if report.runtime.get("language"):
        return
    php_files: List[Path] = []
    for p in root.rglob("*.php"):
        rel_parts = p.relative_to(root).parts
        if any(seg in {"vendor", "node_modules", ".git"} for seg in rel_parts):
            continue
        php_files.append(p)
        if len(php_files) >= 5:
            break
    if not php_files:
        return
    report.runtime["language"] = "php"
    report.signals.append(Signal(
        str(php_files[0].relative_to(root)),
        f"detected {len(php_files)}+ PHP source files (no composer.json)",
    ))
    # WordPress / Drupal sniff from any of the first few files
    for p in php_files:
        txt = _read_text(p, max_bytes=2048).lower()
        if "wp-config" in txt or "wordpress" in txt:
            report.web_server.setdefault("framework", "WordPress")
            report.signals.append(Signal(str(p.relative_to(root)), "WordPress marker"))
            break
        if "drupal" in txt and "drupal_bootstrap" in txt:
            report.web_server.setdefault("framework", "Drupal")
            report.signals.append(Signal(str(p.relative_to(root)), "Drupal marker"))
            break
    # Default deployment_target for plain PHP apps
    report.web_server.setdefault(
        "deployment_target", "PHP-FPM behind nginx / Apache mod_php",
    )


def _enrich_from_readme(root: Path, report: HostingReport) -> None:
    """Last-resort signals from README prose — used when manifests didn't
    cover everything. Marked low-confidence so consumers know it's prose-mined."""
    for name in ("README.md", "README.rst", "README", "README.txt"):
        readme = root / name
        if readme.exists():
            break
    else:
        return
    text = _read_text(readme, max_bytes=16 * 1024).lower()
    if not text:
        return
    # DB hints — only fire if manifests didn't already detect them
    db_hints = {
        "mariadb": ("MariaDB", "rdbms"),
        "postgresql": ("PostgreSQL", "rdbms"),
        "postgres": ("PostgreSQL", "rdbms"),
        "mongodb": ("MongoDB", "document"),
        "redis": ("Redis", "cache"),
        "sqlite": ("SQLite", "rdbms"),
        "cassandra": ("Cassandra", "wide_column"),
        "elasticsearch": ("Elasticsearch", "search"),
    }
    seen = {d["name"].lower() for d in report.databases}
    seen |= {c["name"].lower() for c in report.caches_queues}
    for kw, (name, kind) in db_hints.items():
        if kw in text and name.lower() not in seen:
            target = report.caches_queues if kind in ("cache", "search") else report.databases
            target.append({
                "name": name, "type": kind, "source": "README",
                "confidence": "low",
            })
            seen.add(name.lower())


# ---------------------------------------------------------------------------
# Container / k8s detectors
# ---------------------------------------------------------------------------


_DOCKERFILE_FROM_RE = re.compile(r"^\s*FROM\s+([^\s]+)", re.IGNORECASE | re.MULTILINE)
_DOCKERFILE_EXPOSE_RE = re.compile(r"^\s*EXPOSE\s+(.+)$", re.IGNORECASE | re.MULTILINE)
_DOCKERFILE_ENV_RE = re.compile(r"^\s*ENV\s+([A-Z_][A-Z0-9_]*)", re.IGNORECASE | re.MULTILINE)
_DOCKERFILE_CMD_RE = re.compile(r"^\s*(?:CMD|ENTRYPOINT)\s+(.+)$", re.IGNORECASE | re.MULTILINE)


def _analyze_dockerfile(p: Path, txt: str, report: HostingReport) -> None:
    rel = str(p)
    base = _DOCKERFILE_FROM_RE.findall(txt)
    if base:
        report.container.setdefault("base_images", []).extend(base)
        report.signals.append(Signal(rel, f"FROM: {base[0]}"))
        # Heuristic: detect runtime from base image. ONLY apply the
        # version-from-base when the project's primary language matches.
        # Cross-contamination (e.g. a Python project with a side container
        # built on openjdk for one tool) used to overwrite the Python
        # version with the JDK version.
        primary_lang = report.runtime.get("language")
        for b in base:
            blow = b.lower()
            if "openjdk" in blow or "amazoncorretto" in blow or "eclipse-temurin" in blow:
                if primary_lang in (None, "java"):
                    report.runtime.setdefault("language", "java")
                    jv = re.search(r"(?:jdk|java|temurin|corretto)[:-]?(\d+)", blow)
                    if jv and report.runtime.get("language") == "java":
                        report.runtime.setdefault("version", jv.group(1))
            elif "python" in blow:
                if primary_lang in (None, "python"):
                    report.runtime.setdefault("language", "python")
                    pv = re.search(r"python:(\d+(?:\.\d+)?)", blow)
                    if pv and report.runtime.get("language") == "python":
                        report.runtime.setdefault("version", pv.group(1))
            elif "node" in blow:
                if primary_lang in (None, "javascript"):
                    report.runtime.setdefault("language", "javascript")
                    nv = re.search(r"node:(\d+(?:\.\d+)?)", blow)
                    if nv and report.runtime.get("language") == "javascript":
                        report.runtime.setdefault("version", nv.group(1))
            elif "tomcat" in blow:
                report.web_server.setdefault("deployment_target", "Tomcat (from base image)")
            elif "nginx" in blow:
                report.web_server.setdefault("deployment_target", "nginx (from base image)")
            elif "alpine" in blow:
                report.container["os_family"] = "alpine"
            elif "ubuntu" in blow or "debian" in blow:
                report.container["os_family"] = "debian"
    for m in _DOCKERFILE_EXPOSE_RE.finditer(txt):
        for tok in m.group(1).split():
            try:
                port_num = int(tok.split("/")[0])
                report.ports.append({"port": port_num, "source": rel, "via": "dockerfile EXPOSE"})
            except ValueError:
                pass


def _analyze_docker_compose(p: Path, txt: str, report: HostingReport) -> None:
    rel = str(p)
    # Service-level signals: image + ports + db images
    img_re = re.compile(r"image:\s*['\"]?([a-z0-9./:_-]+)", re.IGNORECASE)
    port_re = re.compile(r"-\s*['\"]?(\d+):(\d+)['\"]?")
    for img in img_re.findall(txt):
        low = img.lower()
        if "mysql" in low:
            report.databases.append({"name": "MySQL", "type": "rdbms", "source": rel, "via": "compose image"})
        elif "postgres" in low:
            report.databases.append({"name": "PostgreSQL", "type": "rdbms", "source": rel, "via": "compose image"})
        elif "mongo" in low:
            report.databases.append({"name": "MongoDB", "type": "document", "source": rel, "via": "compose image"})
        elif "redis" in low:
            report.caches_queues.append({"name": "Redis", "type": "cache", "source": rel, "via": "compose image"})
        elif "rabbitmq" in low:
            report.caches_queues.append({"name": "RabbitMQ", "type": "queue", "source": rel, "via": "compose image"})
        elif "elasticsearch" in low or "elastic.co" in low:
            report.caches_queues.append({"name": "Elasticsearch", "type": "search", "source": rel, "via": "compose image"})
        elif "tomcat" in low:
            report.web_server.setdefault("deployment_target", "Tomcat (from compose)")
    for host, container in port_re.findall(txt):
        try:
            report.ports.append({"port": int(host), "container_port": int(container),
                                  "source": rel, "via": "compose ports"})
        except ValueError:
            pass


def _analyze_k8s_manifest(p: Path, txt: str, report: HostingReport) -> None:
    rel = str(p)
    if "kind:" not in txt.lower():
        return
    # Container port
    for m in re.finditer(r"containerPort:\s*(\d+)", txt):
        report.ports.append({"port": int(m.group(1)), "source": rel, "via": "k8s containerPort"})
    # Resource limits
    cpu = re.search(r"cpu:\s*['\"]?([0-9a-zA-Z.]+)", txt)
    mem = re.search(r"memory:\s*['\"]?([0-9a-zA-Z.]+)", txt)
    if cpu or mem:
        report.container.setdefault("resource_hints", []).append({
            "source": rel,
            "cpu": cpu.group(1) if cpu else None,
            "memory": mem.group(1) if mem else None,
        })


# ---------------------------------------------------------------------------
# Application properties / web.xml
# ---------------------------------------------------------------------------


def _analyze_app_properties(p: Path, txt: str, report: HostingReport) -> None:
    rel = str(p)
    # Spring Boot server.port
    m = re.search(r"server\.port\s*[:=]\s*(\d+)", txt)
    if m:
        report.ports.append({"port": int(m.group(1)), "source": rel, "via": "server.port"})
    # SSL
    if re.search(r"server\.ssl\.enabled\s*[:=]\s*true", txt, re.IGNORECASE):
        report.tls["enabled"] = True
        report.signals.append(Signal(rel, "server.ssl.enabled=true"))
    # DB url (JDBC)
    for jdbc in re.findall(r"jdbc:([a-z0-9]+)://", txt, re.IGNORECASE):
        flavor = jdbc.lower()
        known = {"mysql": "MySQL", "postgresql": "PostgreSQL", "oracle": "Oracle",
                 "sqlserver": "SQL Server", "h2": "H2", "mariadb": "MariaDB"}
        if flavor in known:
            report.databases.append({"name": known[flavor], "type": "rdbms",
                                      "source": rel, "via": "jdbc url"})


def _analyze_web_xml(p: Path, txt: str, report: HostingReport) -> None:
    rel = str(p)
    if "<servlet" in txt or "<filter" in txt:
        report.web_server.setdefault("deployment_target",
                                       "Servlet container (Tomcat / Jetty / WildFly)")
        report.web_server.setdefault("packaging", "WAR")
        report.signals.append(Signal(rel, "web.xml — servlet container required"))


def _analyze_env_file(p: Path, txt: str, report: HostingReport) -> None:
    rel = str(p)
    # Capture variable names (don't capture values — they may be real secrets
    # in a checked-in .env, but we only need names for the report).
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        var = line.split("=", 1)[0].strip()
        if var.isupper() and re.match(r"^[A-Z_][A-Z0-9_]*$", var):
            report.env_vars_required.append({"name": var, "source": rel})


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _build_summary(r: HostingReport) -> str:
    """Compose a single-line human-readable summary for the dashboard."""
    parts = []
    if r.runtime:
        lang = r.runtime.get("language", "?")
        ver = r.runtime.get("version") or r.runtime.get("version_spec") or "?"
        parts.append(f"{lang} {ver}")
    if r.web_server.get("framework"):
        parts.append(r.web_server["framework"])
    if r.web_server.get("deployment_target"):
        parts.append(f"on {r.web_server['deployment_target']}")
    if r.databases:
        # Dedupe by name
        db_names = sorted({d["name"] for d in r.databases})
        parts.append("DB: " + ", ".join(db_names))
    if r.caches_queues:
        cq_names = sorted({c["name"] for c in r.caches_queues})
        parts.append("cache/queue: " + ", ".join(cq_names))
    if r.container.get("base_images"):
        parts.append(f"container ({r.container['base_images'][0]})")
    return " · ".join(parts) if parts else "no hosting signals detected"


def analyze_hosting_requirements(repo_root: str) -> HostingReport:
    """Inspect every manifest/config file under `repo_root` and produce a
    HostingReport summarizing the expected deployment environment.
    """
    report = HostingReport()
    root = Path(repo_root)
    if not root.exists() or not root.is_dir():
        report.summary = f"path not found: {repo_root}"
        return report

    files = _walk_interesting_files(root)
    for p in files:
        try:
            name = p.name
            txt = _read_text(p)
            if not txt:
                continue
            if name == "pom.xml":
                _analyze_pom(p, txt, report)
            elif name in ("build.gradle", "build.gradle.kts"):
                _analyze_gradle(p, txt, report)
            elif name == "pyproject.toml":
                _analyze_pyproject(p, txt, report)
            elif name == "requirements.txt":
                _analyze_requirements_txt(p, txt, report)
            elif name == "package.json":
                _analyze_package_json(p, txt, report)
            elif name == "composer.json":
                _analyze_composer_json(p, txt, report)
            elif name == "Dockerfile":
                _analyze_dockerfile(p, txt, report)
            elif name in ("docker-compose.yml", "docker-compose.yaml"):
                _analyze_docker_compose(p, txt, report)
            elif name in ("application.properties", "application.yml", "application.yaml"):
                _analyze_app_properties(p, txt, report)
            elif name == "web.xml":
                _analyze_web_xml(p, txt, report)
            elif name.startswith(".env"):
                _analyze_env_file(p, txt, report)
            elif name.endswith((".yml", ".yaml")) and ("k8s" in str(p) or "kubernetes" in str(p)
                                                       or "deployment" in name.lower()):
                _analyze_k8s_manifest(p, txt, report)
        except Exception as e:
            logger.debug(f"hosting_requirements: skip {p}: {e}")

    # De-dupe databases by (name, type)
    seen = set()
    deduped = []
    for d in report.databases:
        key = (d["name"], d.get("type"))
        if key not in seen:
            seen.add(key)
            deduped.append(d)
    report.databases = deduped

    # De-dupe caches/queues
    seen = set()
    deduped = []
    for c in report.caches_queues:
        key = (c["name"], c.get("type"))
        if key not in seen:
            seen.add(key)
            deduped.append(c)
    report.caches_queues = deduped

    # De-dupe env vars by name (keep first source)
    seen_vars: Set[str] = set()
    deduped_vars = []
    for v in report.env_vars_required:
        if v["name"] not in seen_vars:
            seen_vars.add(v["name"])
            deduped_vars.append(v)
    report.env_vars_required = deduped_vars

    # De-dupe ports
    seen_ports: Set[int] = set()
    deduped_ports = []
    for pt in report.ports:
        if pt["port"] not in seen_ports:
            seen_ports.add(pt["port"])
            deduped_ports.append(pt)
    report.ports = deduped_ports

    # Cross-reference detected container base images + compose images
    # against the curated web-server CVE manifest (nginx / Apache HTTPD /
    # Tomcat / OpenJDK). Same shape as the lib-vulns pipeline: findings
    # carry severity + recommended upgrade target.
    try:
        from app_classifier.web_server_vulns import (
            analyze_web_servers, findings_to_dict,
        )
        candidate_refs: List[str] = list(report.container.get("base_images", []) or [])
        # Also pull any image refs from compose / k8s signals that included
        # `via=compose image`, etc. We already stash docker-compose images
        # in `databases` and `caches_queues` (mysql/postgres/redis), but
        # web-server images may show up in deploy compose files too.
        # For now we accept base_images as the main signal.
        ws_findings = analyze_web_servers(candidate_refs)
        report.web_server_vulnerabilities = findings_to_dict(ws_findings)
    except Exception as exc:
        logger.debug(f"web-server CVE detection failed: {exc}")

    # Fallback PHP detection — catches DVWA / WordPress / Drupal / Magento
    # where no composer.json exists. Only fires when no other runtime found.
    _detect_php_from_source(root, report)

    # README prose mining — last-resort DB/cache hints when manifests didn't
    # surface them. e.g. DVWA's README says "PHP/MariaDB" but ships no manifest.
    _enrich_from_readme(root, report)

    report.summary = _build_summary(report)
    return report
