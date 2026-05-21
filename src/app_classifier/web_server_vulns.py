"""Web-server CVE detector.

Given a list of base-image refs (`nginx:1.21.6`, `tomcat:9.0.50`,
`openjdk:8`) and compose images, extract server name + version, look up
against the curated CVE manifest at `data/web_server_cves.json`, return
findings with severity + recommended upgrade target.

Designed to slot into the existing hosting-requirements report — no new
endpoint required.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


_MANIFEST_PATH = Path(__file__).parent / "data" / "web_server_cves.json"

# Recognized base-image patterns → (server_name, version)
# Each tuple: regex over the image ref, capture-name for version
_IMAGE_PATTERNS = [
    (re.compile(r"^(?:docker\.io/library/)?nginx:([0-9][0-9.\-a-z]*)", re.IGNORECASE),    "nginx"),
    (re.compile(r"^(?:docker\.io/library/)?httpd:([0-9][0-9.\-a-z]*)", re.IGNORECASE),    "apache_httpd"),
    (re.compile(r"^(?:docker\.io/library/)?apache:([0-9][0-9.\-a-z]*)", re.IGNORECASE),    "apache_httpd"),
    (re.compile(r"^(?:docker\.io/library/)?tomcat:([0-9][0-9.\-a-z]*)", re.IGNORECASE),   "tomcat"),
    (re.compile(r"^(?:docker\.io/library/)?openjdk:([0-9][0-9._\-a-z]*)", re.IGNORECASE), "openjdk"),
    (re.compile(r"^(?:docker\.io/library/)?eclipse-temurin:([0-9][0-9._\-a-z]*)", re.IGNORECASE), "openjdk"),
    (re.compile(r"^(?:docker\.io/library/)?amazoncorretto:([0-9][0-9._\-a-z]*)", re.IGNORECASE), "openjdk"),
]


@dataclass
class WebServerFinding:
    server: str           # nginx | apache_httpd | tomcat | openjdk
    version: str
    source: str           # file path (Dockerfile, compose, ...)
    cves: List[Dict[str, Any]] = field(default_factory=list)
    recommended_version: Optional[str] = None
    rationale: str = ""


def _parse_version_tuple(v: str) -> Tuple[int, ...]:
    parts: List[int] = []
    for tok in re.split(r"[.\-_]", v):
        m = re.match(r"^(\d+)", tok)
        if not m:
            break
        parts.append(int(m.group(1)))
    return tuple(parts)


def _version_le(a: str, b: str) -> bool:
    """`a` <= `b` by parsed numeric tuple. Unknown comparisons return False."""
    pa, pb = _parse_version_tuple(a), _parse_version_tuple(b)
    if not pa or not pb:
        return False
    # Pad shorter tuple with zeros for fair comparison
    n = max(len(pa), len(pb))
    pa = pa + (0,) * (n - len(pa))
    pb = pb + (0,) * (n - len(pb))
    return pa <= pb


def _load_manifest() -> Dict[str, Any]:
    try:
        return json.loads(_MANIFEST_PATH.read_text())
    except Exception as exc:
        logger.warning(f"Could not load web_server_cves manifest: {exc}")
        return {}


_MANIFEST = _load_manifest()


def identify_server(image_ref: str) -> Optional[Tuple[str, str]]:
    """Return (server_name, version) if image_ref matches a known server."""
    for pat, name in _IMAGE_PATTERNS:
        m = pat.match(image_ref)
        if m:
            return (name, m.group(1))
    return None


def lookup_cves(server: str, version: str) -> Tuple[List[Dict[str, Any]], Optional[str], str]:
    """For (server, version) return (cve list, recommended upgrade version, rationale).

    A CVE applies if `version <= cve.affects_max_version`. The recommended
    upgrade is the manifest's `latest_stable` for that server.
    """
    manifest = _MANIFEST.get(server) or {}
    cves_data = manifest.get("cves") or []
    latest = manifest.get("latest_stable")

    matching: List[Dict[str, Any]] = []
    for entry in cves_data:
        if _version_le(version, entry["affects_max_version"]):
            matching.append({
                "cve_id": entry["cve"],
                "severity": entry["severity"],
                "summary": entry["summary"],
                "fix_introduced_in": entry["fix"],
                "affects_versions_up_to": entry["affects_max_version"],
            })

    if not matching:
        rationale = f"{server} {version}: no known CVEs in curated manifest."
        return [], latest, rationale

    severities = {}
    for c in matching:
        severities[c["severity"]] = severities.get(c["severity"], 0) + 1
    sev_str = ", ".join(f"{n} {s}" for s, n in sorted(severities.items()))
    rationale = (
        f"{server} {version}: {len(matching)} CVE(s) ({sev_str}). "
        f"Recommended upgrade: {latest}."
    )
    return matching, latest, rationale


def analyze_web_servers(base_images: List[str]) -> List[WebServerFinding]:
    """Walk a list of base-image refs (from Dockerfile FROM, compose images,
    k8s manifests). Identify servers, look up CVEs, return findings."""
    findings: List[WebServerFinding] = []
    seen: set = set()
    for ref in base_images:
        if not ref:
            continue
        ident = identify_server(ref)
        if not ident:
            continue
        server, version = ident
        key = (server, version)
        if key in seen:
            continue
        seen.add(key)
        cves, recommended, rationale = lookup_cves(server, version)
        findings.append(WebServerFinding(
            server=server, version=version, source=ref,
            cves=cves, recommended_version=recommended, rationale=rationale,
        ))
    return findings


def findings_to_dict(findings: List[WebServerFinding]) -> List[Dict[str, Any]]:
    return [asdict(f) for f in findings]
