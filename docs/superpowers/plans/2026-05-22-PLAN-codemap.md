# PLAN-codemap — Impact Analysis Implementation

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `map_code()` — a non-LLM impact-analysis surface producing a file-dependency graph across 6 languages (Python, JS/TS, Java, Go, Ruby, PHP) plus a Python-only function-call graph, exposed via `CodeMap.impact_of(target)`.

**Architecture:** Three modules. `types.py` defines `FileNode`, `FunctionNode`, `CodeMap`. `file_deps.py` walks the repo and extracts imports per language using per-language regex (no tree-sitter). `py_calls.py` uses stdlib `ast` for Python-only function-call graph. `CodeMap.impact_of()` does BFS over `imported_by` or `called_by` with a visited-set to handle cycles. New test fixtures for Go, Ruby, and Java.

**Tech Stack:** Python 3.10+, stdlib only (`ast`, `re`, `pathlib`, `dataclasses`, `typing`), pytest.

**Wave:** 1 (fully independent of PLAN-llm — PLAN-codemap and PLAN-llm run concurrently).

**Spec reference:** `docs/superpowers/specs/2026-05-22-v0.5.0-design.md` § Component 3 (`map_code()` impact analysis).

---

## File Structure

| Path | Purpose |
|---|---|
| `src/app_classifier/codemap/__init__.py` | Public re-exports |
| `src/app_classifier/codemap/types.py` | `FileNode`, `FunctionNode`, `CodeMap` dataclasses |
| `src/app_classifier/codemap/file_deps.py` | 6-language import extraction + entry-point detection |
| `src/app_classifier/codemap/py_calls.py` | Python AST-based function-call graph |
| `src/app_classifier/__init__.py` | MODIFY — re-export `map_code`, `CodeMap`, `FileNode`, `FunctionNode` |
| `tests/test_codemap_types.py` | NEW — `impact_of` algorithm coverage (cycle, transitive, one-hop) |
| `tests/test_codemap_file_deps.py` | NEW — per-language extraction |
| `tests/test_codemap_py_calls.py` | NEW — function-call graph |
| `tests/fixtures/go_service/{main.go,handler.go,go.mod}` | NEW |
| `tests/fixtures/ruby_sinatra/{app.rb,helpers.rb,Gemfile}` | NEW |
| `tests/fixtures/java_spring/{src/main/java/com/example/App.java,Controller.java,pom.xml}` | NEW |

---

## Chunk 1: Types + new fixtures

### Task 1: Dataclasses with `impact_of` BFS

**Files:**
- Create: `src/app_classifier/codemap/__init__.py` (empty for now)
- Create: `src/app_classifier/codemap/types.py`
- Create: `tests/test_codemap_types.py`

- [ ] **Step 1: Write failing tests for `impact_of` algorithm**

```python
# tests/test_codemap_types.py
import pytest

from app_classifier.codemap.types import CodeMap, FileNode, FunctionNode


def _make_simple_graph():
    # a.py imports b.py imports c.py
    return CodeMap(
        files={
            "a.py": FileNode(path="a.py", language="python",
                             imports=["b.py"], imported_by=[], is_entry_point=True),
            "b.py": FileNode(path="b.py", language="python",
                             imports=["c.py"], imported_by=["a.py"], is_entry_point=False),
            "c.py": FileNode(path="c.py", language="python",
                             imports=[], imported_by=["b.py"], is_entry_point=False),
        },
        functions={},
        entry_points=["a.py"],
    )


def test_impact_of_file_transitive():
    g = _make_simple_graph()
    # If I change c.py, both b.py (direct) and a.py (transitive) are affected.
    assert g.impact_of("c.py", transitive=True) == ["a.py", "b.py"]


def test_impact_of_file_one_hop():
    g = _make_simple_graph()
    assert g.impact_of("c.py", transitive=False) == ["b.py"]


def test_impact_of_returns_empty_for_unknown_target():
    g = _make_simple_graph()
    assert g.impact_of("nonexistent.py") == []


def test_impact_of_handles_cycle():
    """a → b → c → a cycle must not infinite-loop. Visited-set required."""
    cyclic = CodeMap(
        files={
            "a.py": FileNode(path="a.py", language="python",
                             imports=["b.py"], imported_by=["c.py"], is_entry_point=False),
            "b.py": FileNode(path="b.py", language="python",
                             imports=["c.py"], imported_by=["a.py"], is_entry_point=False),
            "c.py": FileNode(path="c.py", language="python",
                             imports=["a.py"], imported_by=["b.py"], is_entry_point=False),
        },
        functions={},
        entry_points=[],
    )
    # Each file is impacted by changing any other in the cycle, target excluded.
    assert sorted(cyclic.impact_of("a.py", transitive=True)) == ["b.py", "c.py"]


def test_impact_of_function_target():
    """`file:function` target walks the call-graph and folds up to file impact."""
    g = CodeMap(
        files={
            "a.py": FileNode(path="a.py", language="python",
                             imports=[], imported_by=[], is_entry_point=True),
            "b.py": FileNode(path="b.py", language="python",
                             imports=[], imported_by=[], is_entry_point=True),
        },
        functions={
            "a.py:helper": FunctionNode(file="a.py", name="helper", line=1,
                                         calls=[], called_by=["b.py:caller"]),
            "b.py:caller": FunctionNode(file="b.py", name="caller", line=1,
                                         calls=["a.py:helper"], called_by=[]),
        },
        entry_points=["a.py", "b.py"],
    )
    # Changing a.py:helper impacts b.py (where caller lives).
    assert g.impact_of("a.py:helper", transitive=True) == ["b.py"]
```

- [ ] **Step 2: Run test, expect failure**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_codemap_types.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `types.py`**

```python
# src/app_classifier/codemap/types.py
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
```

- [ ] **Step 4: Run tests, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_codemap_types.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/app_classifier/codemap/__init__.py src/app_classifier/codemap/types.py tests/test_codemap_types.py
git commit -m "codemap: dataclasses + impact_of BFS with cycle handling"
```

---

### Task 2: New test fixtures (Go / Ruby / Java)

**Files:**
- Create: `tests/fixtures/go_service/go.mod`
- Create: `tests/fixtures/go_service/main.go`
- Create: `tests/fixtures/go_service/handler.go`
- Create: `tests/fixtures/ruby_sinatra/Gemfile`
- Create: `tests/fixtures/ruby_sinatra/app.rb`
- Create: `tests/fixtures/ruby_sinatra/helpers.rb`
- Create: `tests/fixtures/java_spring/pom.xml`
- Create: `tests/fixtures/java_spring/src/main/java/com/example/App.java`
- Create: `tests/fixtures/java_spring/src/main/java/com/example/Controller.java`

- [ ] **Step 1: Write fixture files (data, not tests)**

```go
// tests/fixtures/go_service/go.mod
module github.com/example/svc

go 1.22
```

```go
// tests/fixtures/go_service/main.go
package main

import (
	"net/http"

	"github.com/example/svc/handler"
)

func main() {
	http.HandleFunc("/users", handler.Users)
	http.ListenAndServe(":8080", nil)
}
```

```go
// tests/fixtures/go_service/handler.go
package handler

import (
	"encoding/json"
	"net/http"
)

func Users(w http.ResponseWriter, r *http.Request) {
	json.NewEncoder(w).Encode([]string{"alice", "bob"})
}
```

```ruby
# tests/fixtures/ruby_sinatra/Gemfile
source 'https://rubygems.org'
gem 'sinatra'
```

```ruby
# tests/fixtures/ruby_sinatra/app.rb
require 'sinatra'
require_relative 'helpers'

get '/' do
  greeting('world')
end
```

```ruby
# tests/fixtures/ruby_sinatra/helpers.rb
def greeting(name)
  "hello, #{name}"
end
```

```xml
<!-- tests/fixtures/java_spring/pom.xml -->
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>spring-fixture</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
      <version>3.2.0</version>
    </dependency>
  </dependencies>
</project>
```

```java
// tests/fixtures/java_spring/src/main/java/com/example/App.java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class App {
    public static void main(String[] args) {
        SpringApplication.run(App.class, args);
    }
}
```

```java
// tests/fixtures/java_spring/src/main/java/com/example/Controller.java
package com.example;

import com.example.Util;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class Controller {
    @GetMapping("/hello")
    public String hello() {
        return Util.greeting("world");
    }
}
```

```java
// tests/fixtures/java_spring/src/main/java/com/example/Util.java
package com.example;

public class Util {
    public static String greeting(String name) {
        return "hello, " + name;
    }
}
```

- [ ] **Step 2: Commit fixtures**

```bash
git add tests/fixtures/go_service tests/fixtures/ruby_sinatra tests/fixtures/java_spring
git commit -m "tests: Go/Ruby/Java fixtures for v0.5.0 map_code"
```

---

## Chunk 2: File-dependency extraction

### Task 3: Per-language import extractors + graph builder

**Files:**
- Create: `src/app_classifier/codemap/file_deps.py`
- Create: `tests/test_codemap_file_deps.py`

- [ ] **Step 1: Write failing tests for each language**

```python
# tests/test_codemap_file_deps.py
from pathlib import Path

import pytest

from app_classifier.codemap.file_deps import (
    extract_imports, build_file_graph, detect_entry_points,
)

FIX = Path(__file__).parent / "fixtures"


# ── Per-language extraction ──

def test_python_extracts_relative_and_package_imports(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text(
        "from .b import x\nimport os\nfrom pkg.c import y\n"
    )
    (tmp_path / "pkg" / "b.py").write_text("")
    (tmp_path / "pkg" / "c.py").write_text("")
    imports = extract_imports(tmp_path / "pkg" / "a.py", tmp_path)
    assert "pkg/b.py" in imports
    assert "pkg/c.py" in imports
    assert "os" not in imports  # external dropped


def test_js_extracts_relative_imports(tmp_path):
    (tmp_path / "a.js").write_text(
        "import {x} from './b';\nconst y = require('./c.js');\nconst z = await import('./d');"
    )
    (tmp_path / "b.js").write_text("")
    (tmp_path / "c.js").write_text("")
    (tmp_path / "d.js").write_text("")
    imports = extract_imports(tmp_path / "a.js", tmp_path)
    assert "b.js" in imports
    assert "c.js" in imports
    assert "d.js" in imports


def test_go_extracts_module_internal_imports():
    root = FIX / "go_service"
    imports = extract_imports(root / "main.go", root)
    # main.go imports github.com/example/svc/handler — resolved to handler.go
    assert "handler.go" in imports


def test_ruby_extracts_require_relative():
    root = FIX / "ruby_sinatra"
    imports = extract_imports(root / "app.rb", root)
    assert "helpers.rb" in imports
    # `require 'sinatra'` is external — must not appear
    assert "sinatra.rb" not in imports


def test_java_extracts_package_imports():
    root = FIX / "java_spring"
    controller = root / "src/main/java/com/example/Controller.java"
    imports = extract_imports(controller, root)
    # Controller imports com.example.Util — must resolve to Util.java.
    assert any(path.endswith("Util.java") for path in imports)
    # External imports (org.springframework.*) must be dropped — no false positives.
    for path in imports:
        assert "annotation" not in path
        assert "springframework" not in path


def test_php_extracts_require_and_use(tmp_path):
    (tmp_path / "a.php").write_text(
        "<?php\nrequire_once 'b.php';\ninclude 'c.php';\nuse App\\Helpers;\n"
    )
    (tmp_path / "b.php").write_text("<?php ?>")
    (tmp_path / "c.php").write_text("<?php ?>")
    imports = extract_imports(tmp_path / "a.php", tmp_path)
    assert "b.php" in imports
    assert "c.php" in imports


# ── Graph builder ──

def test_build_file_graph_transposes_edges(tmp_path):
    (tmp_path / "a.py").write_text("from b import x")
    (tmp_path / "b.py").write_text("")
    graph = build_file_graph(tmp_path)
    assert graph["a.py"].imports == ["b.py"]
    assert graph["b.py"].imported_by == ["a.py"]
    assert graph["a.py"].imported_by == []


def test_build_file_graph_skips_excluded_dirs(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("export {}")
    (tmp_path / "app.js").write_text("import x from './node_modules/lib';")
    graph = build_file_graph(tmp_path)
    assert "node_modules/lib.js" not in graph
    assert "app.js" in graph


def test_detect_entry_points_zero_in_degree(tmp_path):
    (tmp_path / "a.py").write_text("from b import x")
    (tmp_path / "b.py").write_text("")
    graph = build_file_graph(tmp_path)
    eps = detect_entry_points(graph, tmp_path)
    assert "a.py" in eps  # 0 importers
    assert "b.py" not in eps


def test_detect_entry_points_framework_markers(tmp_path):
    (tmp_path / "shared.py").write_text("def x(): pass")
    (tmp_path / "main.py").write_text(
        "from shared import x\nif __name__ == '__main__':\n    x()"
    )
    (tmp_path / "imports_main.py").write_text("import main")
    graph = build_file_graph(tmp_path)
    eps = detect_entry_points(graph, tmp_path)
    # main.py is imported, but the if __name__ marker makes it an entry point too
    assert "main.py" in eps
```

- [ ] **Step 2: Implement `file_deps.py`**

```python
# src/app_classifier/codemap/file_deps.py
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
```

- [ ] **Step 3: Run tests, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_codemap_file_deps.py -v
```

Expected: 10 passed. If Java or Go tests fail, double-check the fixture paths.

- [ ] **Step 4: Commit**

```bash
git add src/app_classifier/codemap/file_deps.py tests/test_codemap_file_deps.py
git commit -m "codemap: 6-language file-dep extraction + entry-point detection"
```

---

## Chunk 3: Python function-call graph + public API

### Task 4: Python AST function-call extractor

**Files:**
- Create: `src/app_classifier/codemap/py_calls.py`
- Create: `tests/test_codemap_py_calls.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_codemap_py_calls.py
from pathlib import Path

from app_classifier.codemap.py_calls import build_python_function_graph


def test_function_calls_within_file(tmp_path):
    (tmp_path / "m.py").write_text(
        "def helper():\n    return 1\n\n"
        "def caller():\n    return helper()\n"
    )
    g = build_python_function_graph(tmp_path)
    assert "m.py:helper" in g
    assert "m.py:caller" in g
    assert "m.py:helper" in g["m.py:caller"].calls
    assert "m.py:caller" in g["m.py:helper"].called_by


def test_function_calls_across_files(tmp_path):
    (tmp_path / "a.py").write_text("def helper():\n    return 1\n")
    (tmp_path / "b.py").write_text(
        "from a import helper\n\n"
        "def caller():\n    return helper()\n"
    )
    g = build_python_function_graph(tmp_path)
    assert "a.py:helper" in g["b.py:caller"].calls
    assert "b.py:caller" in g["a.py:helper"].called_by


def test_async_function_def_detected(tmp_path):
    (tmp_path / "m.py").write_text(
        "async def fetch():\n    return await api()\n"
    )
    g = build_python_function_graph(tmp_path)
    assert "m.py:fetch" in g


def test_skips_files_with_syntax_errors(tmp_path):
    (tmp_path / "broken.py").write_text("def x(:\n    pass\n")
    (tmp_path / "ok.py").write_text("def y(): pass\n")
    g = build_python_function_graph(tmp_path)
    assert "ok.py:y" in g
    # broken.py simply contributes no functions; not an exception


def test_attribute_calls_unresolved_are_dropped(tmp_path):
    (tmp_path / "m.py").write_text(
        "import os\n\ndef x():\n    return os.path.join('a', 'b')\n"
    )
    g = build_python_function_graph(tmp_path)
    assert "m.py:x" in g
    # os.path.join is external — must not produce false edges
    assert all(":" in c for c in g["m.py:x"].calls)
    assert "os:join" not in g["m.py:x"].calls
```

- [ ] **Step 2: Implement `py_calls.py`**

```python
# src/app_classifier/codemap/py_calls.py
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
```

- [ ] **Step 3: Run tests, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_codemap_py_calls.py -v
```

Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add src/app_classifier/codemap/py_calls.py tests/test_codemap_py_calls.py
git commit -m "codemap: Python AST function-call graph"
```

---

### Task 5: `map_code()` public entry point + re-exports

**Files:**
- Modify: `src/app_classifier/codemap/__init__.py`
- Modify: `src/app_classifier/__init__.py`
- Modify: `tests/test_codemap_types.py` (append smoke test)

- [ ] **Step 1: Append integration test**

```python
# tests/test_codemap_types.py — append
from pathlib import Path
import pytest

FIX = Path(__file__).parent / "fixtures"


def test_map_code_on_ecommerce_django_returns_codemap():
    from app_classifier import map_code, CodeMap
    cm = map_code(FIX / "ecommerce_django")
    assert isinstance(cm, CodeMap)
    assert len(cm.files) >= 1
    assert len(cm.entry_points) >= 1


def test_map_code_python_function_call_optional():
    """include_function_calls=False skips py_calls — should produce empty functions dict."""
    from app_classifier import map_code
    cm = map_code(FIX / "blog_flask", include_function_calls=False)
    assert cm.functions == {}


def test_map_code_top_level_public_imports():
    from app_classifier import map_code, CodeMap, FileNode, FunctionNode
    assert callable(map_code)
    assert CodeMap and FileNode and FunctionNode
```

- [ ] **Step 2: Implement public entry point**

```python
# src/app_classifier/codemap/__init__.py
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
```

Modify `src/app_classifier/__init__.py` — add to imports and `__all__`:

```python
# Append near other imports
from app_classifier.codemap import map_code, CodeMap, FileNode, FunctionNode
```

And append to `__all__`:

```python
    # Code mapping (v0.5.0)
    "map_code", "CodeMap", "FileNode", "FunctionNode",
```

- [ ] **Step 3: Run all codemap tests + full suite**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v
```

Expected: 42 existing + 5 types + 10 file_deps + 5 py_calls + 3 integration = ~65 passed.

- [ ] **Step 4: Commit**

```bash
git add src/app_classifier/codemap/__init__.py src/app_classifier/__init__.py tests/test_codemap_types.py
git commit -m "codemap: map_code() public entry + re-exports"
```

---

## Final verification

- [ ] **Step 1: Full suite + smoke import**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v
PYTHONPATH=src .venv/bin/python -c "
from app_classifier import map_code
cm = map_code('tests/fixtures/ecommerce_django')
print('entry_points:', cm.entry_points)
print('files:', list(cm.files.keys())[:3])
"
```

Expected: All tests pass; smoke output shows at least one entry point and at least one file.
