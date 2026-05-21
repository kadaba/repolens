"""Public surface for the codemap subsystem.

Usage:
    from app_classifier import map_code
    cm = map_code("./my-repo")
    print(cm.entry_points)
    print(cm.impact_of("src/auth.py"))
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

from app_classifier.codemap.types import CodeMap, FileNode, FunctionNode
from app_classifier.codemap.file_deps import build_file_graph, detect_entry_points
from app_classifier.codemap.py_calls import build_python_function_graph


def map_code(
    repo: Union[str, Path],
    *,
    include_function_calls: bool = True,
) -> CodeMap:
    """Build a static code-mapping for impact analysis.

    Args:
        repo: Path to the repository root.
        include_function_calls: If True (default), also build the Python
            function-call graph via stdlib `ast`. Set to False to skip
            the AST pass when only file-level mapping is needed.

    Returns:
        CodeMap with .files, .functions, .entry_points, and .impact_of().
    """
    root = Path(repo).resolve()
    files = build_file_graph(root)
    entry_points = detect_entry_points(files, root)
    functions = build_python_function_graph(root) if include_function_calls else {}
    return CodeMap(files=files, functions=functions, entry_points=entry_points)


__all__ = ["map_code", "CodeMap", "FileNode", "FunctionNode"]
