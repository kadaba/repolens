"""Agentic classification — autonomous repo investigation via LLM tool-use.

This is the OPT-IN agentic layer on top of the deterministic classifier.
The deterministic path (`classify()`) is always run first as ground truth
— it's fast, predictable, and zero-cost. The agent kicks in when:

  1. **Confidence is below threshold** — the agent investigates further
     by reading files, grepping, listing subdirs, reading README sections.
  2. **A monorepo is detected** — the agent identifies sub-apps and
     classifies each independently, then synthesizes a top-level answer.

Architecture: the LLM is given the current observations + a JSON tool
schema. It picks the next tool to call (or concludes). The agent executes
the tool, updates state, and loops until either a conclusion is reached
or `max_iterations` is hit.

What makes this actually agentic (not just LLM-augmented):
  - Autonomy: LLM decides what to investigate next, not us
  - Tool use: real file-reading, real grep, real subdirectory traversal
  - Loop: keeps investigating until satisfied OR bounded
  - Self-correction: each observation can update the hypothesis
  - Multi-step planning: complex cases (monorepo → enumerate → classify-each → synthesize)

What's deliberately bounded:
  - Read-only tools (no code execution, no network outside LLM)
  - Max iterations cap (default 8 — enough for complex repos, prevents
    runaway loops)
  - Per-tool result truncation (so a giant file doesn't blow context)
  - LLM call cost tracking surfaced in the final result
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from app_classifier.classifier import (
    AppDescription, LLMProvider, classify, _build_llm_prompt,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------


@dataclass
class AgentStep:
    """One step the agent took during investigation. Full audit trail."""
    iteration: int
    action: str                       # tool name OR 'conclude' OR 'error'
    arguments: Dict[str, Any] = field(default_factory=dict)
    observation_summary: str = ""     # short text the LLM saw
    reasoning: str = ""               # why the LLM chose this step


@dataclass
class SubappClassification:
    """A classification of one sub-app within a monorepo."""
    path: str                         # relative to the repo root
    description: AppDescription
    detected_via: str = "monorepo_walker"


@dataclass
class AgentClassificationResult:
    """The full agentic-classification output. Includes the deterministic
    description as a baseline + everything the agent learned on top."""
    # Final answer — the agent's best classification
    description: AppDescription
    # Was this a monorepo? If so, here are the sub-apps the agent found.
    is_monorepo: bool = False
    subapps: List[SubappClassification] = field(default_factory=list)
    # How the agent reasoned — full step-by-step audit trail
    steps: List[AgentStep] = field(default_factory=list)
    # Cost + perf data
    llm_calls: int = 0
    llm_tokens_estimated: int = 0     # rough — varies by provider
    iterations_used: int = 0
    final_confidence: float = 0.0
    # Did the agent change the heuristic's verdict? If so, why?
    changed_verdict: bool = False
    change_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description.to_dict(),
            "is_monorepo": self.is_monorepo,
            "subapps": [
                {
                    "path": s.path,
                    "detected_via": s.detected_via,
                    "description": s.description.to_dict(),
                }
                for s in self.subapps
            ],
            "steps": [asdict(s) for s in self.steps],
            "llm_calls": self.llm_calls,
            "llm_tokens_estimated": self.llm_tokens_estimated,
            "iterations_used": self.iterations_used,
            "final_confidence": self.final_confidence,
            "changed_verdict": self.changed_verdict,
            "change_reason": self.change_reason,
        }


# ---------------------------------------------------------------------------
# Monorepo detection — runs BEFORE the LLM loop. Cheap deterministic check.
# ---------------------------------------------------------------------------


_MONOREPO_SIGNALS = (
    # File-level signals at the root
    "lerna.json", "nx.json", "turbo.json", "rush.json",
    "pnpm-workspace.yaml", "pnpm-workspace.yml",
)


def _detect_monorepo(repo_root: Path) -> Tuple[bool, List[str]]:
    """Return (is_monorepo, list of likely sub-app paths)."""
    # Signal 1: explicit monorepo config files at root
    explicit_signals = [
        f for f in _MONOREPO_SIGNALS if (repo_root / f).exists()
    ]

    # Signal 2: package.json with `workspaces`
    pkg = repo_root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
            if data.get("workspaces"):
                explicit_signals.append("package.json:workspaces")
        except Exception:
            pass

    # Signal 3: Cargo.toml with [workspace]
    cargo = repo_root / "Cargo.toml"
    if cargo.exists():
        try:
            txt = cargo.read_text(encoding="utf-8", errors="replace")
            if re.search(r"^\s*\[workspace\]", txt, re.MULTILINE):
                explicit_signals.append("Cargo.toml:workspace")
        except Exception:
            pass

    # Signal 4: multiple manifests in different subdirs (implicit monorepo)
    # We look for at least 2 subdirs that each contain a primary manifest.
    subapp_candidates: set[Path] = set()
    for manifest_name in ("package.json", "pom.xml", "go.mod", "Cargo.toml",
                          "requirements.txt", "pyproject.toml", "Gemfile",
                          "composer.json"):
        for p in repo_root.rglob(manifest_name):
            # Skip if it's in the root itself
            if p.parent == repo_root:
                continue
            # Skip if it's deep in a vendored / build / cache tree
            rel_parts = p.relative_to(repo_root).parts
            if any(seg in {"node_modules", "vendor", "target", "build",
                           "dist", ".gradle", "venv", ".venv", "__pycache__"}
                   for seg in rel_parts):
                continue
            # Cap depth — sub-apps usually live within 2-3 levels
            if len(rel_parts) > 4:
                continue
            subapp_candidates.add(p.parent)

    implicit_signal = len(subapp_candidates) >= 2

    is_monorepo = bool(explicit_signals) or implicit_signal

    # Return up to 20 sub-app paths
    subapp_paths = sorted(
        [str(p.relative_to(repo_root)) for p in subapp_candidates]
    )[:20]

    return is_monorepo, subapp_paths


# ---------------------------------------------------------------------------
# Tools — the agent's read-only verbs
# ---------------------------------------------------------------------------


def _tool_read_file(repo_root: Path, relpath: str, max_bytes: int = 8000) -> Dict[str, Any]:
    """Read a file relative to repo_root. Truncated to max_bytes."""
    p = (repo_root / relpath).resolve()
    # Path traversal guard — never let the LLM read outside the repo
    try:
        p.relative_to(repo_root.resolve())
    except ValueError:
        return {"error": "path traversal blocked", "path": relpath}
    if not p.exists():
        return {"error": "file not found", "path": relpath}
    if not p.is_file():
        return {"error": "not a regular file", "path": relpath}
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"read failed: {e}", "path": relpath}
    truncated = len(content) > max_bytes
    return {
        "path": relpath,
        "content": content[:max_bytes],
        "truncated": truncated,
        "total_bytes": len(content.encode("utf-8", errors="replace")),
    }


def _tool_list_files(repo_root: Path, subdir: str = "", pattern: str = "*") -> Dict[str, Any]:
    """List files matching a glob pattern under repo_root/subdir."""
    base = (repo_root / subdir).resolve() if subdir else repo_root.resolve()
    try:
        base.relative_to(repo_root.resolve())
    except ValueError:
        return {"error": "path traversal blocked", "subdir": subdir}
    if not base.is_dir():
        return {"error": "not a directory", "subdir": subdir}
    matches: List[str] = []
    skip = {"node_modules", ".git", "venv", ".venv", "__pycache__", "target",
            "build", "dist", "vendor", ".gradle", ".idea", ".vscode"}
    try:
        for p in base.rglob(pattern):
            rel_parts = p.relative_to(repo_root).parts
            if any(seg in skip for seg in rel_parts):
                continue
            matches.append(str(p.relative_to(repo_root)))
            if len(matches) >= 100:
                break
    except Exception as e:
        return {"error": f"list failed: {e}", "subdir": subdir}
    return {"subdir": subdir or ".", "pattern": pattern, "files": matches}


def _tool_grep(repo_root: Path, pattern: str, file_glob: str = "*",
               max_hits: int = 40) -> Dict[str, Any]:
    """Grep for a regex across files matching file_glob. Returns matches with
    file path + line number + line content (truncated)."""
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return {"error": f"bad regex: {e}", "pattern": pattern}
    skip = {"node_modules", ".git", "venv", ".venv", "__pycache__", "target",
            "build", "dist", "vendor", ".gradle"}
    hits: List[Dict[str, Any]] = []
    try:
        for p in repo_root.rglob(file_glob):
            if not p.is_file():
                continue
            rel_parts = p.relative_to(repo_root).parts
            if any(seg in skip for seg in rel_parts):
                continue
            try:
                with p.open("rb") as f:
                    text = f.read(128 * 1024).decode("utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    hits.append({
                        "file": str(p.relative_to(repo_root)),
                        "line": i,
                        "content": line.strip()[:200],
                    })
                    if len(hits) >= max_hits:
                        return {"pattern": pattern, "hits": hits, "truncated": True}
    except Exception as e:
        return {"error": f"grep failed: {e}", "pattern": pattern}
    return {"pattern": pattern, "hits": hits, "truncated": False}


def _tool_get_subdirs(repo_root: Path, parent: str = "") -> Dict[str, Any]:
    """List immediate subdirectories under parent (relative to repo_root)."""
    base = (repo_root / parent).resolve() if parent else repo_root.resolve()
    try:
        base.relative_to(repo_root.resolve())
    except ValueError:
        return {"error": "path traversal blocked", "parent": parent}
    if not base.is_dir():
        return {"error": "not a directory", "parent": parent}
    skip = {"node_modules", ".git", "venv", ".venv", "__pycache__", "target",
            "build", "dist", "vendor", ".gradle", ".idea", ".vscode"}
    subdirs = []
    for p in sorted(base.iterdir()):
        if p.is_dir() and p.name not in skip and not p.name.startswith("."):
            subdirs.append(str(p.relative_to(repo_root)))
    return {"parent": parent or ".", "subdirs": subdirs[:60]}


# Maps tool names to handlers. The LLM picks from this set.
_TOOL_REGISTRY = {
    "read_file": _tool_read_file,
    "list_files": _tool_list_files,
    "grep": _tool_grep,
    "get_subdirs": _tool_get_subdirs,
}


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = """You are a code-archaeology agent. Your job: given a \
repository, figure out what kind of application it is and what it does.

A deterministic pattern-matcher already produced an initial classification. \
Your job is to either CONFIRM it (high confidence) or REFINE it by reading \
more code. You have these read-only tools:

  - read_file(path): Read a specific file. Returns content (truncated to 8KB).
  - list_files(subdir, pattern): Glob for files. e.g. pattern='*.py'.
  - grep(pattern, file_glob): Regex search across files.
  - get_subdirs(parent): List immediate subdirectories.

Strategy:
  1. If initial confidence >= 0.75 AND signals are consistent, just conclude.
  2. If confidence < 0.75, investigate. Look for:
     - Distinctive route/handler names (`/checkout`, `/admin/grant-role`)
     - Domain model names (`Order`, `Post`, `Appointment`)
     - README sections that explain the purpose
     - Config files that reveal deployment context (Heroku Procfile, k8s)
  3. If the repo has multiple sub-apps (monorepo), classify each one and \
     synthesize a top-level answer like "monorepo containing an e-commerce \
     storefront + an admin dashboard".

You MUST respond with ONE valid JSON object. No prose, no markdown, no \
backticks. Schema:

  {"action": "read_file" | "list_files" | "grep" | "get_subdirs" | "conclude",
   "arguments": {<tool-specific kwargs>},
   "reasoning": "1-2 sentences on WHY you're taking this step"}

When you have enough evidence, respond with:

  {"action": "conclude",
   "arguments": {
     "category": "e-commerce" | "blog / content platform" | "social network" |
                 "admin panel / dashboard" | "REST API service" |
                 "authentication / SSO" | "file / document management" |
                 "scheduling / booking" | "messaging / notification" |
                 "unknown",
     "confidence": 0.0-1.0,
     "features": ["online shopping", "search", ...],
     "description": "2-3 sentences in plain prose"
   },
   "reasoning": "summary of evidence"}

Hard rules:
  - Use AT MOST 8 tool calls.
  - Don't call read_file on the same path twice.
  - Don't dump irrelevant files. Be targeted.
  - If you can confirm in zero extra tool calls, do so.
"""


def _format_initial_state(description: AppDescription, monorepo_hint: Tuple[bool, List[str]]) -> str:
    """Render the starting context for the LLM in a compact form."""
    is_mono, subapps = monorepo_hint
    lines = [
        f"DETERMINISTIC INITIAL CLASSIFICATION:",
        f"  category: {description.app_category}",
        f"  confidence: {description.app_category_confidence:.0%}",
        f"  features: {', '.join(description.detected_features) or '(none)'}",
        f"  framework: {description.framework or '(unknown)'}",
        f"  routes: {len(description.routes)} found",
        f"  models: {len(description.data_models)} found",
        f"  databases: {', '.join(description.databases) or '(none)'}",
        f"  README excerpt: {description.purpose[:200] or '(no README)'}",
    ]
    if is_mono:
        lines.append(f"  MONOREPO SIGNALS DETECTED. Likely sub-apps: {subapps[:10]}")
    lines.append("")
    lines.append("ROUTES (first 10):")
    for r in description.routes[:10]:
        lines.append(f"  {r.method} {r.path} -> {r.handler}")
    lines.append("")
    lines.append("MODELS (first 10):")
    for m in description.data_models[:10]:
        lines.append(f"  {m.name} ({m.framework or '?'}): {', '.join(m.fields_hint[:6])}")
    return "\n".join(lines)


async def _llm_step(
    llm_provider: LLMProvider,
    system: str,
    user: str,
    history: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Single LLM call. Builds the message stack, parses JSON response.
    Returns parsed dict or None on failure (caller handles)."""
    # Compose a single prompt — most providers accept system+user; for the
    # simplest interface (a single `prompt` callable) we concat.
    history_block = ""
    for h in history:
        history_block += f"\n[observation from {h['action']}]\n{h['observation']}\n"
    prompt = system + "\n\n" + user
    if history_block:
        prompt += "\n\nOBSERVATIONS SO FAR:" + history_block
    prompt += "\n\nYour next JSON action:"

    try:
        raw = await llm_provider(prompt=prompt, max_tokens=600, temperature=0.0)
    except Exception as e:
        logger.warning(f"agent: LLM call failed: {e}")
        return None
    if not raw:
        return None

    # Extract JSON object. The model may wrap it in fence or add commentary.
    raw = raw.strip()
    if raw.startswith("```"):
        # strip code fence
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    # Find first { ... } block — most robust against pre/post commentary
    brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not brace_match:
        return None
    try:
        return json.loads(brace_match.group(0))
    except json.JSONDecodeError:
        return None


def _summarize_observation(action: str, result: Dict[str, Any]) -> str:
    """Compress a tool result into a short text block the LLM can re-read.
    Tool results can be big (file contents up to 8KB); we keep the LLM
    context manageable by summarizing past observations in later turns."""
    if "error" in result:
        return f"error: {result['error']}"
    if action == "read_file":
        return f"{result['path']} ({result.get('total_bytes', '?')} bytes):\n{result.get('content', '')[:3000]}"
    if action == "list_files":
        files = result.get("files", [])
        return f"{len(files)} file(s) under {result.get('subdir', '.')}: " + ", ".join(files[:30])
    if action == "grep":
        hits = result.get("hits", [])
        lines = [f"{len(hits)} hit(s) for {result.get('pattern', '')}:"]
        for h in hits[:25]:
            lines.append(f"  {h['file']}:{h['line']}  {h['content']}")
        return "\n".join(lines)
    if action == "get_subdirs":
        subdirs = result.get("subdirs", [])
        return f"{len(subdirs)} subdir(s) under {result.get('parent', '.')}: " + ", ".join(subdirs[:30])
    return json.dumps(result)[:500]


async def classify_agentic(
    repo_root: str,
    llm_provider: LLMProvider,
    max_iterations: int = 8,
    confidence_threshold: float = 0.75,
    monorepo_max_subapps: int = 6,
) -> AgentClassificationResult:
    """Classify a repo with full agentic investigation.

    Steps:
      1. Run the deterministic classifier as a baseline.
      2. Check for monorepo signals. If found, classify each sub-app
         independently (deterministic), then synthesize a top-level
         answer via the LLM.
      3. If single-app AND confidence < threshold, enter the agent loop:
         the LLM picks tools to investigate, observations feed back in,
         loop until conclude OR max_iterations.

    Returns an `AgentClassificationResult` that includes the final answer
    AND the full audit trail (every step the agent took + reasoning).

    `llm_provider` is YOUR async callable (same shape as
    `classify_async(llm_provider=...)`).

    Raises nothing — failures fall back to the deterministic baseline.
    """
    repo_path = Path(repo_root).resolve()
    if not repo_path.is_dir():
        # Degenerate case — wrap a stub
        from app_classifier.classifier import AppDescription as _AD
        empty = _AD(
            name=str(repo_path), purpose="", runtime={}, framework=None,
            deployment_target=None, routes=[], data_models=[],
            databases=[], caches_queues=[], notable_files=[],
            one_line_summary=f"path not found: {repo_root}",
            architecture_summary="",
        )
        return AgentClassificationResult(
            description=empty,
            change_reason="path not found",
        )

    # ── Step 1: deterministic baseline ──
    baseline = classify(str(repo_path))

    result = AgentClassificationResult(
        description=baseline,
        final_confidence=baseline.app_category_confidence,
    )

    # ── Step 2: monorepo handling ──
    is_mono, subapp_paths = _detect_monorepo(repo_path)
    if is_mono and subapp_paths:
        result.is_monorepo = True
        # Classify each sub-app deterministically (cheap, parallel-safe)
        for sub_rel in subapp_paths[:monorepo_max_subapps]:
            sub_full = repo_path / sub_rel
            try:
                sub_desc = classify(str(sub_full))
                result.subapps.append(SubappClassification(
                    path=sub_rel, description=sub_desc,
                ))
            except Exception as e:
                logger.debug(f"agent: subapp classify failed for {sub_rel}: {e}")

        # Ask LLM to synthesize a top-level answer covering all sub-apps
        if result.subapps:
            sub_summary = "\n".join(
                f"  - {s.path}: {s.description.app_category} "
                f"({s.description.app_category_confidence:.0%}, "
                f"features: {', '.join(s.description.detected_features) or 'none'})"
                for s in result.subapps
            )
            synth_prompt = (
                "You are summarizing a monorepo. Here are the sub-apps that "
                "were classified individually:\n\n"
                f"{sub_summary}\n\n"
                "Write a 2-3 sentence top-level description of what this "
                "monorepo contains. Use plain prose. No markdown.\n\n"
                "Output ONLY the description text, no JSON, no prefix."
            )
            try:
                synth = await llm_provider(
                    prompt=synth_prompt, max_tokens=300, temperature=0.2,
                )
                result.llm_calls += 1
                if synth and len(synth.strip()) > 40:
                    result.description.functional_description = synth.strip()
                    result.description.app_category = "monorepo"
                    result.description.app_category_confidence = 0.9
                    result.description.detected_features = sorted({
                        f for s in result.subapps for f in s.description.detected_features
                    })
                    result.changed_verdict = True
                    result.change_reason = (
                        f"monorepo with {len(result.subapps)} sub-app(s); "
                        f"synthesized top-level description from sub-classifications"
                    )
                    result.final_confidence = 0.9
            except Exception as e:
                logger.debug(f"agent: monorepo synth failed: {e}")
        result.steps.append(AgentStep(
            iteration=0, action="detect_monorepo",
            observation_summary=f"found {len(result.subapps)} sub-app(s)",
            reasoning="monorepo signals present at repo root",
        ))
        return result

    # ── Step 3: single-app agent loop (only if confidence below threshold) ──
    if baseline.app_category_confidence >= confidence_threshold:
        result.steps.append(AgentStep(
            iteration=0, action="conclude_baseline",
            observation_summary=(
                f"deterministic confidence {baseline.app_category_confidence:.0%} "
                f">= threshold {confidence_threshold:.0%}; no investigation needed"
            ),
            reasoning="initial heuristic was confident enough",
        ))
        return result

    # The agent loop. Feed initial state, LLM picks tool, execute, repeat.
    history: List[Dict[str, Any]] = []
    initial_state = _format_initial_state(baseline, (is_mono, subapp_paths))

    for iteration in range(1, max_iterations + 1):
        result.iterations_used = iteration
        action = await _llm_step(llm_provider, _SYSTEM_PROMPT, initial_state, history)
        result.llm_calls += 1

        if not action or "action" not in action:
            result.steps.append(AgentStep(
                iteration=iteration, action="error",
                observation_summary="LLM returned no valid JSON action",
                reasoning="(none)",
            ))
            break

        a_name = action.get("action")
        a_args = action.get("arguments", {}) or {}
        a_reasoning = action.get("reasoning", "")

        if a_name == "conclude":
            # Apply the agent's conclusion to the description
            cat = a_args.get("category") or baseline.app_category
            conf = float(a_args.get("confidence", baseline.app_category_confidence) or 0.0)
            conf = max(0.0, min(1.0, conf))
            features = a_args.get("features") or baseline.detected_features
            desc = a_args.get("description") or baseline.functional_description

            if cat != baseline.app_category or conf != baseline.app_category_confidence:
                result.changed_verdict = True
                result.change_reason = (
                    f"agent revised verdict from "
                    f"{baseline.app_category} ({baseline.app_category_confidence:.0%}) "
                    f"to {cat} ({conf:.0%}) after {iteration} investigation step(s)"
                )

            result.description.app_category = cat
            result.description.app_category_confidence = conf
            result.description.detected_features = list(features)
            if desc and len(desc.strip()) > 40:
                result.description.functional_description = desc.strip()
            result.final_confidence = conf
            result.steps.append(AgentStep(
                iteration=iteration, action="conclude", arguments=a_args,
                observation_summary=f"category={cat} confidence={conf:.0%}",
                reasoning=a_reasoning,
            ))
            return result

        # Tool dispatch
        tool_fn = _TOOL_REGISTRY.get(a_name)
        if tool_fn is None:
            result.steps.append(AgentStep(
                iteration=iteration, action=a_name, arguments=a_args,
                observation_summary=f"unknown tool '{a_name}'",
                reasoning=a_reasoning,
            ))
            history.append({
                "action": a_name,
                "observation": f"unknown tool '{a_name}'; available: {list(_TOOL_REGISTRY.keys())}",
            })
            continue

        try:
            tool_result = tool_fn(repo_path, **a_args)
        except TypeError as e:
            tool_result = {"error": f"bad arguments: {e}"}
        except Exception as e:
            tool_result = {"error": f"tool crashed: {e}"}

        obs = _summarize_observation(a_name, tool_result)
        history.append({"action": a_name, "observation": obs})
        result.steps.append(AgentStep(
            iteration=iteration, action=a_name, arguments=a_args,
            observation_summary=obs[:300] + ("…" if len(obs) > 300 else ""),
            reasoning=a_reasoning,
        ))

    # Loop exited without explicit conclude — keep baseline, note exhaustion
    result.steps.append(AgentStep(
        iteration=result.iterations_used + 1,
        action="exhausted",
        observation_summary=(
            f"hit max_iterations={max_iterations} without conclude; "
            f"keeping baseline verdict"
        ),
        reasoning="agent did not converge",
    ))
    return result
