"""Per-language import extraction + repo-internal resolution + entry-point detection."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from app_classifier.codemap.types import FileNode


_EXCLUDED_DIRS = {
    "node_modules", ".venv", "venv", ".git", "vendor", "target", "dist",
    "build", "__pycache__", ".tox", ".mypy_cache", ".pytest_cache",
    "site-packages",
}

_LANG_BY_EXT = {
    ".py": "python", ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js",
    ".ts": "ts", ".tsx": "ts",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
}


# ── Per-language regex patterns (intra-repo intent only) ──

_RE_PY_FROM = re.compile(r"^\s*from\s+(\.+)?([\w\.]+)?\s+import\b", re.MULTILINE)
# Captures the full `import X, Y, Z` clause so multi-imports are handled.
_RE_PY_IMPORT = re.compile(r"^\s*import\s+([\w\.,\s]+?)(?:\s+as\s+\w+)?\s*$", re.MULTILINE)
_RE_JS_IMPORT = re.compile(r"""(?:import\s+(?:[\w*${}\s,]+\s+from\s+)?|require\s*\(|\bimport\s*\()\s*['"](\.\S+?)['"]""")
_RE_JAVA_IMPORT = re.compile(r"^\s*import\s+(static\s+)?([\w\.]+)\s*;", re.MULTILINE)
_RE_GO_IMPORT_BLOCK = re.compile(r"import\s*\(([\s\S]*?)\)|import\s+\"([^\"]+)\"")
_RE_GO_IMPORT_LINE = re.compile(r"\"([^\"]+)\"")
_RE_RUBY_REL = re.compile(r"require_relative\s+['\"](\S+?)['\"]")
_RE_RUBY_REL_DOT = re.compile(r"require\s+['\"]\.\/(\S+?)['\"]")
_RE_PHP_REQUIRE = re.compile(r"(?:require|require_once|include|include_once)\s*\(?\s*['\"](\S+?)['\"]")
_RE_PHP_USE = re.compile(r"use\s+([\w\\]+);")


def _strip_line_comments(text: str, lang: str) -> str:
    """Strip line comments so commented imports don't produce false edges."""
    if lang in ("python", "ruby"):
        return re.sub(r"#.*$", "", text, flags=re.MULTILINE)
    if lang in ("js", "ts", "java", "go", "php"):
        return re.sub(r"//.*$", "", text, flags=re.MULTILINE)
    return text


def _language_of(path: Path) -> Optional[str]:
    return _LANG_BY_EXT.get(path.suffix.lower())


def _resolve_python(import_path: str, current_file: Path, repo_root: Path,
                    is_relative: bool, dot_count: int) -> List[Path]:
    """Best-effort: resolve `from .b import x` or `import pkg.c`.
    Returns at most one resolved path — first-match wins to avoid emitting
    both `b.py` and `b/__init__.py` when both happen to exist.
    """
    candidates: List[Path] = []
    if is_relative:
        base = current_file.parent
        for _ in range(max(dot_count - 1, 0)):
            base = base.parent
        if import_path:
            parts = import_path.split(".")
            candidates.append(base.joinpath(*parts).with_suffix(".py"))
            candidates.append(base.joinpath(*parts, "__init__.py"))
        else:
            candidates.append(base / "__init__.py")
    else:
        parts = import_path.split(".")
        candidates.append(repo_root.joinpath(*parts).with_suffix(".py"))
        candidates.append(repo_root.joinpath(*parts, "__init__.py"))
        candidates.append(current_file.parent.joinpath(*parts).with_suffix(".py"))
    for c in candidates:
        if c.is_file() and c != current_file:
            return [c]
    return []


def _resolve_js(import_path: str, current_file: Path, repo_root: Path) -> List[Path]:
    base = current_file.parent
    target = (base / import_path).resolve()
    candidates = [target]
    if not target.suffix:
        for ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
            candidates.append(target.with_suffix(ext))
        candidates.append(target / "index.js")
        candidates.append(target / "index.ts")
    return [c for c in candidates if c.is_file() and c != current_file]


def _resolve_go(import_path: str, current_file: Path, repo_root: Path,
                module_path: Optional[str]) -> List[Path]:
    """Resolve `import "github.com/x/svc/handler"` to repo files in handler/ dir."""
    if not module_path:
        return []
    if not import_path.startswith(module_path):
        return []  # external
    rel = import_path[len(module_path):].lstrip("/")
    pkg_dir = (repo_root / rel) if rel else repo_root
    if not pkg_dir.is_dir():
        # Maybe a single file
        target = (repo_root / f"{rel}.go")
        return [target] if target.is_file() else []
    return [p for p in pkg_dir.glob("*.go") if p != current_file]


def _resolve_simple(rel_path: str, current_file: Path, repo_root: Path,
                    default_ext: str = "") -> List[Path]:
    candidates = [(current_file.parent / rel_path)]
    if default_ext and not rel_path.endswith(default_ext):
        candidates.append(current_file.parent / f"{rel_path}{default_ext}")
    return [c for c in candidates if c.is_file() and c != current_file]


def _go_module_path(repo_root: Path) -> Optional[str]:
    gomod = repo_root / "go.mod"
    if not gomod.exists():
        return None
    for line in gomod.read_text(errors="replace").splitlines():
        if line.startswith("module "):
            return line.split(None, 1)[1].strip()
    return None


def extract_imports(file_path: Path, repo_root: Path) -> List[str]:
    """Return repo-relative paths of files imported by `file_path`."""
    lang = _language_of(file_path)
    if not lang:
        return []
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    text = _strip_line_comments(text, lang)

    targets: List[Path] = []

    if lang == "python":
        for m in _RE_PY_FROM.finditer(text):
            dots, mod = m.group(1) or "", m.group(2) or ""
            targets.extend(_resolve_python(
                mod, file_path, repo_root,
                is_relative=bool(dots), dot_count=len(dots),
            ))
        for m in _RE_PY_IMPORT.finditer(text):
            mod = m.group(1)
            for name in mod.split(","):
                targets.extend(_resolve_python(
                    name.strip(), file_path, repo_root,
                    is_relative=False, dot_count=0,
                ))
    elif lang in ("js", "ts"):
        for m in _RE_JS_IMPORT.finditer(text):
            targets.extend(_resolve_js(m.group(1), file_path, repo_root))
    elif lang == "java":
        # Java imports use fully-qualified names; map to file paths if they
        # resolve against repo source roots (any path under repo containing
        # the package segments).
        for m in _RE_JAVA_IMPORT.finditer(text):
            fqn = m.group(2)
            # Skip obvious external roots
            if fqn.startswith(("java.", "javax.", "org.springframework.",
                               "com.fasterxml.", "lombok.", "org.junit.")):
                continue
            parts = fqn.split(".")
            for src_root in (repo_root / "src/main/java", repo_root / "src", repo_root):
                if not src_root.exists():
                    continue
                candidate = src_root.joinpath(*parts).with_suffix(".java")
                if candidate.is_file():
                    targets.append(candidate)
                    break
    elif lang == "go":
        module = _go_module_path(repo_root)
        for m in _RE_GO_IMPORT_BLOCK.finditer(text):
            block, single = m.group(1), m.group(2)
            if block:
                for sm in _RE_GO_IMPORT_LINE.finditer(block):
                    targets.extend(_resolve_go(sm.group(1), file_path, repo_root, module))
            elif single:
                targets.extend(_resolve_go(single, file_path, repo_root, module))
    elif lang == "ruby":
        for m in _RE_RUBY_REL.finditer(text):
            rel = m.group(1)
            targets.extend(_resolve_simple(rel, file_path, repo_root, default_ext=".rb"))
        for m in _RE_RUBY_REL_DOT.finditer(text):
            rel = m.group(1)
            targets.extend(_resolve_simple(rel, file_path, repo_root, default_ext=".rb"))
    elif lang == "php":
        for m in _RE_PHP_REQUIRE.finditer(text):
            rel = m.group(1)
            targets.extend(_resolve_simple(rel, file_path, repo_root, default_ext=".php"))
        # PHP `use` namespace resolution is best-effort — skipped to avoid noise

    seen = set()
    out: List[str] = []
    for t in targets:
        try:
            rel = str(t.relative_to(repo_root))
        except ValueError:
            continue
        if rel not in seen:
            seen.add(rel)
            out.append(rel)
    return out


def _iter_source_files(repo_root: Path):
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(seg in _EXCLUDED_DIRS for seg in path.relative_to(repo_root).parts):
            continue
        if _language_of(path):
            yield path


def build_file_graph(repo_root: Path) -> Dict[str, FileNode]:
    """Walk repo, extract imports, transpose to build imported_by."""
    nodes: Dict[str, FileNode] = {}
    for path in _iter_source_files(repo_root):
        rel = str(path.relative_to(repo_root))
        nodes[rel] = FileNode(
            path=rel, language=_language_of(path) or "unknown",
            imports=[], imported_by=[], is_entry_point=False,
        )

    for path in _iter_source_files(repo_root):
        rel = str(path.relative_to(repo_root))
        imports = extract_imports(path, repo_root)
        nodes[rel].imports = imports
        for imp in imports:
            if imp in nodes and rel not in nodes[imp].imported_by:
                nodes[imp].imported_by.append(rel)
    return nodes


# ── Entry-point detection ──

_FRAMEWORK_MARKERS = [
    re.compile(r"if\s+__name__\s*==\s*['\"]__main__['\"]"),
    re.compile(r"@(?:app|router|blueprint|bp)\.(?:route|get|post|put|delete|patch)\b"),
    re.compile(r"@(?:RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping)\b"),
    re.compile(r"\bapp\.(?:get|post|put|delete|patch|use)\s*\("),
    re.compile(r"\brouter\.(?:get|post|put|delete|patch)\s*\("),
    re.compile(r"^\s*func\s+main\s*\(\s*\)\s*\{", re.MULTILINE),
    re.compile(r"class\s+\w+\s+extends\s+(?:HttpServlet|ApplicationServlet)"),
]


def detect_entry_points(graph: Dict[str, FileNode], repo_root: Path) -> List[str]:
    """Files with 0 importers OR containing a framework marker."""
    eps: List[str] = []
    for rel, node in graph.items():
        is_ep = False
        if not node.imported_by:
            is_ep = True
        else:
            try:
                text = (repo_root / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            for marker in _FRAMEWORK_MARKERS:
                if marker.search(text):
                    is_ep = True
                    break
        if is_ep:
            node.is_entry_point = True
            eps.append(rel)
    return sorted(eps)
