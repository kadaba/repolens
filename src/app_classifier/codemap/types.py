"""CodeMap dataclasses + BFS impact_of algorithm."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Set


@dataclass
class FileNode:
    path: str  # repo-relative
    language: str
    imports: List[str] = field(default_factory=list)        # repo-internal files this imports
    imported_by: List[str] = field(default_factory=list)
    is_entry_point: bool = False


@dataclass
class FunctionNode:
    file: str
    name: str
    line: int
    calls: List[str] = field(default_factory=list)          # "file:function" of callees
    called_by: List[str] = field(default_factory=list)


@dataclass
class CodeMap:
    files: Dict[str, FileNode] = field(default_factory=dict)
    functions: Dict[str, FunctionNode] = field(default_factory=dict)
    entry_points: List[str] = field(default_factory=list)

    def impact_of(self, target: str, *, transitive: bool = True) -> List[str]:
        """Files (or function keys) affected by changing `target`.

        - Target can be a file path (e.g., "a.py") or "file:function" key.
        - transitive=True: BFS across the entire reverse graph.
        - transitive=False: one hop only.
        - Cycles are handled via a visited-set.
        - Output is sorted; target excluded.
        """
        if ":" in target and target in self.functions:
            return self._impact_of_function(target, transitive=transitive)
        if target in self.files:
            return self._impact_of_file(target, transitive=transitive)
        return []

    def _impact_of_file(self, target: str, *, transitive: bool) -> List[str]:
        visited: Set[str] = {target}
        result: Set[str] = set()
        queue: deque[str] = deque([target])
        depth = 0
        while queue:
            level_size = len(queue)
            for _ in range(level_size):
                node = queue.popleft()
                file_node = self.files.get(node)
                if not file_node:
                    continue
                for importer in file_node.imported_by:
                    if importer in visited:
                        continue
                    visited.add(importer)
                    result.add(importer)
                    if transitive:
                        queue.append(importer)
            depth += 1
            if not transitive:
                break
        return sorted(result)

    def _impact_of_function(self, target: str, *, transitive: bool) -> List[str]:
        """Walk called_by; fold function-level impact up to file-level for the output."""
        visited: Set[str] = {target}
        result_files: Set[str] = set()
        queue: deque[str] = deque([target])
        while queue:
            level_size = len(queue)
            for _ in range(level_size):
                node = queue.popleft()
                fn = self.functions.get(node)
                if not fn:
                    continue
                for caller in fn.called_by:
                    if caller in visited:
                        continue
                    visited.add(caller)
                    # Fold to owning file (caller is "file:function")
                    caller_file = caller.split(":", 1)[0]
                    if caller_file != target.split(":", 1)[0]:
                        result_files.add(caller_file)
                    if transitive:
                        queue.append(caller)
            if not transitive:
                break
        return sorted(result_files)
