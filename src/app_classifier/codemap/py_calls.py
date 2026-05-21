"""Python AST-based function-call graph. Best-effort — drops unresolved edges."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app_classifier.codemap.types import FunctionNode


def _iter_py_files(repo_root: Path):
    _EXCLUDED = {"node_modules", ".venv", "venv", ".git", "vendor", "target",
                  "dist", "build", "__pycache__", ".tox", ".mypy_cache",
                  ".pytest_cache", "site-packages"}
    for path in repo_root.rglob("*.py"):
        if not path.is_file():
            continue
        if any(seg in _EXCLUDED for seg in path.relative_to(repo_root).parts):
            continue
        yield path


def _parse_imports(tree: ast.AST) -> Dict[str, str]:
    """Map local-name → module-path so we can resolve cross-file `Call(func=Name)`."""
    bindings: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                for alias in node.names:
                    local = alias.asname or alias.name
                    bindings[local] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name
                bindings[local] = alias.name
    return bindings


def _resolve_module_to_file(module: str, repo_root: Path) -> Optional[str]:
    """`a.b` → `a/b.py` if present in repo, else None."""
    parts = module.split(".")
    candidates = [
        repo_root.joinpath(*parts).with_suffix(".py"),
        repo_root.joinpath(*parts, "__init__.py"),
    ]
    for c in candidates:
        if c.is_file():
            try:
                return str(c.relative_to(repo_root))
            except ValueError:
                pass
    return None


def build_python_function_graph(repo_root: Path) -> Dict[str, FunctionNode]:
    """Walk all .py files, return dict of "rel/path.py:funcname" → FunctionNode."""
    # Pass 1: collect all (file, funcname) → AST node so cross-file resolution works
    file_funcs: Dict[str, Dict[str, ast.AST]] = {}     # rel-path → {name: def}
    file_imports: Dict[str, Dict[str, str]] = {}       # rel-path → {local: module.symbol}
    file_trees: Dict[str, ast.AST] = {}

    for p in _iter_py_files(repo_root):
        rel = str(p.relative_to(repo_root))
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except SyntaxError:
            file_funcs[rel] = {}
            file_imports[rel] = {}
            continue
        file_trees[rel] = tree
        file_imports[rel] = _parse_imports(tree)
        defs: Dict[str, ast.AST] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs[node.name] = node
        file_funcs[rel] = defs

    # Build initial FunctionNode set
    out: Dict[str, FunctionNode] = {}
    for rel, defs in file_funcs.items():
        for name, node in defs.items():
            out[f"{rel}:{name}"] = FunctionNode(
                file=rel, name=name, line=getattr(node, "lineno", 0),
                calls=[], called_by=[],
            )

    # Pass 2: walk Call nodes inside each FunctionDef body, resolve targets
    for rel, defs in file_funcs.items():
        bindings = file_imports.get(rel, {})
        local_defs = set(defs.keys())
        for name, node in defs.items():
            caller_key = f"{rel}:{name}"
            calls: Set[str] = set()
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                target_key: Optional[str] = None
                func = sub.func
                if isinstance(func, ast.Name) and func.id in local_defs:
                    target_key = f"{rel}:{func.id}"
                elif isinstance(func, ast.Name) and func.id in bindings:
                    # Direct name imported via `from m import x`
                    full = bindings[func.id]
                    module, _, sym = full.rpartition(".")
                    if module:
                        target_file = _resolve_module_to_file(module, repo_root)
                        if target_file:
                            cand_key = f"{target_file}:{sym}"
                            if cand_key in out:
                                target_key = cand_key
                if target_key and target_key != caller_key:
                    calls.add(target_key)
            for tk in sorted(calls):
                out[caller_key].calls.append(tk)
                out[tk].called_by.append(caller_key)
    return out
